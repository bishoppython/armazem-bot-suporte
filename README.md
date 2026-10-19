# Bot de Suporte com IA — Armazém Agreste

[![ci](https://github.com/bishoppython/armazem-bot-suporte/actions/workflows/ci.yml/badge.svg)](https://github.com/bishoppython/armazem-bot-suporte/actions/workflows/ci.yml)

Assistente de atendimento que responde a partir dos documentos da loja, cita a fonte e passa a conversa para uma pessoa quando não tem confiança, quando o cliente pede ou quando o assunto é sensível.

**Problema de negócio:** loja pequena perde venda porque demora a responder no WhatsApp, e as perguntas se repetem ("qual o mínimo do atacado?", "tem G?", "quanto é o frete?"). O bot responde 24 horas sem inventar preço nem política, e entrega para a equipe só o que precisa de gente.

Projeto 7 do portfólio **Armazém Agreste**, o ecossistema de dados de uma empresa fictícia de confecções de Caruaru-PE. Todos os dados são sintéticos.

<!-- GIF da demo: docs/img/demo.gif -->

## Arquitetura

```
mensagem ──► limpeza + detecção de injection
               │
               ├─ pediu atendente? ───────────────────────────────► ticket + aviso
               │
               ▼
          busca híbrida (BM25 + embeddings, RRF) ──► confiança
               │
               ├─ tema sensível? ──► responde a política (se houver) + ticket
               ├─ confiança < limiar? ────────────────────────────► ticket + aviso
               ▼
          LLM (só com os trechos recuperados) ──► SEM_RESPOSTA? ──► ticket
               │
               ▼
          resposta + fontes + tokens registrados
```

| Camada | Arquivo | O que faz |
|---|---|---|
| Domínio | `domain/busca.py` | BM25, cosseno, fusão RRF e confiança 0–1 |
| Domínio | `domain/escalonamento.py` | Regras de passagem para humano |
| Domínio | `domain/seguranca.py` + `prompt.py` | Defesa contra prompt injection: mensagem delimitada como dado, regras no system prompt |
| Adaptadores | `adapters/llm.py` | Cliente para qualquer API compatível com OpenAI (Ollama, Groq, OpenRouter) |
| Adaptadores | `adapters/repositorio.py` | Conversas, tickets e tokens (SQLAlchemy; retenção de 90 dias pela LGPD) |
| Serviço | `servico.py` | Orquestra busca → decisão → geração → registro |
| Entrada | `api.py`, `cli.py`, `web/` | API FastAPI, CLI e chat web |

A empresa atendida é só uma pasta: `empresas/<slug>/docs/*.md` + `catalogo.json` + fotos. Trocar de cliente é trocar `BOT_EMPRESA_DIR`.

## Como rodar

```bash
# sem GPU nem LLM (modo demo, resposta extrativa)
docker compose up --build              # http://localhost:8000

# com LLM local
ollama pull qwen3.5:4b && ollama pull nomic-embed-text
uv sync && make run                    # http://localhost:8000

# pergunta pela CLI
uv run bot perguntar "Qual o pedido mínimo no atacado?"
```

Para usar Groq ou OpenRouter, copie `.env.example` para `.env` e troque `BOT_LLM_BASE_URL`, `BOT_LLM_API_KEY` e `BOT_LLM_MODELO`.

### WhatsApp (Evolution API v2)

Defina `BOT_EVOLUTION_URL`, `BOT_EVOLUTION_API_KEY` e `BOT_EVOLUTION_INSTANCIA` e aponte o webhook `messages.upsert` da instância para `POST /webhook/whatsapp`. O bot responde em segundo plano (o webhook devolve na hora para a Evolution não reenviar) e, quando a resposta vem de um produto, manda a foto do catálogo. Mensagens de grupos, status e do próprio número são ignoradas.

## Avaliação

`avaliacao/perguntas.jsonl` tem 46 casos: 33 perguntas com documento esperado e termos que a resposta precisa conter, 4 que devem escalar (pedido de atendente, defeito, cobrança) e 9 fora do assunto que devem ser recusadas, incluindo uma tentativa de prompt injection.

| Métrica | Modo demo (sem LLM, CI) | qwen3.5:4b local + nomic-embed-text |
|---|---|---|
| Recuperação top-4 | 100% | 100% |
| Recuperação top-1 | 87,9% | 87,9% |
| Decisão correta (responder, escalar ou recusar) | 93,5% | 100% |
| Fidelidade às fontes | 93,9% | 100% |
| Tempo médio por resposta | — | 1,95 s (RTX 4050, 6 GB) |
| Tokens por resposta gerada pelo LLM | — | ~880 |

Resultados completos, pergunta a pergunta: `avaliacao/resultados/`.

**Ressalva:** o limiar de confiança e as rubricas foram calibrados neste mesmo conjunto, então os números são otimistas. Um conjunto separado, nunca usado na calibração, é o próximo passo.

O que a avaliação ensinou, e mudou no código:
- O cosseno do `nomic-embed-text` não separa sozinho pergunta da loja de pergunta fora do assunto (0,60–0,67 contra 0,62–0,81). O piso foi recalibrado e a recusa ficou com o LLM (`FORA_DO_ESCOPO`), sem abrir ticket, para não encher a fila humana.
- A confiança lexical era medida no primeiro trecho da fusão RRF, que podia vir só da busca semântica. "Vocês abrem domingo?" escalava com confiança 0,075; agora cada sinal é medido no seu próprio melhor trecho (com teste de regressão).

- **Recuperação top-k:** o documento esperado está entre os 4 trechos enviados ao LLM.
- **Escalonamento correto:** escalou quando devia e respondeu quando devia.
- **Fidelidade:** a resposta contém os fatos esperados (prazo, valor, quantidade) do documento.

O CI roda a avaliação no modo demo a cada push e falha se a nota cair abaixo de 0,9.

## Decisões técnicas

- **Sem LangChain e sem banco vetorial:** o fluxo cabe em cerca de 150 linhas legíveis, e dezenas de documentos por empresa cabem em memória. Ver [ADR 0001](docs/adr/0001-llm-aberto-e-busca-hibrida-sem-framework.md).
- **BM25 + embeddings:** o BM25 acerta números e nomes e roda no CI sem GPU; os embeddings cobrem paráfrases. A confiança usa o maior dos dois sinais.
- **Escalar não é ficar calado:** num tema sensível, o bot abre o ticket e ainda informa a política aplicável, se ela estiver nos documentos.
- **Um ticket por conversa:** insistir ("cadê o atendente?") não duplica a fila.
- **Custo visível:** tokens de entrada e saída por resposta ficam no banco (`GET /api/custo`).

## Próximos passos

- Conjunto de avaliação separado (held-out) e LLM como juiz para respostas abertas.
- Ferramentas: status do pedido (API do Projeto 4) e estoque em tempo real (Projeto 1).
- pgvector no Postgres para bases maiores; avaliação com LLM como juiz.

## Créditos

Fotos-base dos mockups do catálogo: mockupbee, Stephanie Ho, Artem Podrez e MART PRODUCTION (Pexels, licença Pexels). Marca, empresa, endereço e políticas são fictícios.
