# ADR 0001 — LLM aberto via API compatível com OpenAI e busca híbrida sem framework

**Data:** 2026-10-19 · **Status:** aceito

## Contexto
O plano original pedia OpenAI API + LangChain + Flask + Chroma. O bot também vai ser a base de um produto vendido a pequenos negócios do Agreste, então custo por conversa e dependência de fornecedor importam tanto quanto a qualidade da resposta.

## Decisão
- **LLM:** qualquer servidor compatível com a API de chat da OpenAI (`BOT_LLM_BASE_URL`). No desenvolvimento, Ollama local (`qwen3.5:4b` numa RTX 4050 de 6 GB); em produção, um modelo aberto no Groq ou no OpenRouter. Trocar de provedor é trocar três variáveis de ambiente.
- **Sem LangChain:** o fluxo é curto (buscar → decidir → gerar → registrar) e fica legível em cerca de 150 linhas em `servico.py`. Um framework esconderia justamente as decisões que este projeto quer mostrar e testar.
- **Busca híbrida:** BM25 em Python puro + embeddings (`nomic-embed-text`), combinados por Reciprocal Rank Fusion. O BM25 roda sem infraestrutura nenhuma, é determinístico (o CI avalia busca e escalonamento sem GPU) e acerta nomes próprios e números; os embeddings cobrem sinônimos e paráfrases.
- **Índice em memória** com cache de embeddings em disco, chaveado pelo hash do trecho. Com dezenas de documentos por empresa, um banco vetorial seria custo operacional sem ganho. O caminho para escala é o pgvector no mesmo Postgres que guarda as conversas.

## Consequências
- Custo zero no desenvolvimento e nas demos; em produção, centavos por conversa num modelo aberto.
- O modo demo (`BOT_MODO_DEMO=true`) responde com o melhor trecho, sem LLM. Serve para o CI e para mostrar o projeto em máquinas sem GPU.
- O limiar de confiança que decide o escalonamento depende do sinal disponível (só lexical ou também semântico) e é calibrado no conjunto de avaliação, não chutado.
