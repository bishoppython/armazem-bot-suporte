"""O atendente: busca, decide se escala, chama o LLM e registra tudo."""

import logging
import re
from dataclasses import dataclass

from bot_suporte.adapters.base_conhecimento import (
    carregar_trechos,
    nome_da_empresa,
    prefixo_consulta,
    vetores_com_cache,
)
from bot_suporte.adapters.llm import LLM, ClienteOpenAICompat, Embedder
from bot_suporte.adapters.repositorio import Repositorio
from bot_suporte.config import Config
from bot_suporte.domain import escalonamento, prompt, seguranca
from bot_suporte.domain.busca import Buscador
from bot_suporte.domain.modelos import Motivo, Resposta, Resultado, Uso
from bot_suporte.domain.texto import tokens

log = logging.getLogger(__name__)

MSG_HUMANO = (
    "Certo! Já chamei uma pessoa da nossa equipe para continuar com você. "
    "No horário da loja a resposta vem em até 30 minutos; fora dele, no próximo dia útil a partir das 8h."
)
MSG_SEM_RESPOSTA = (
    "Não encontrei essa informação nos materiais da loja e prefiro não chutar. "
    "Passei sua pergunta para uma pessoa da equipe, que vai te responder por aqui."
)
MSG_SENSIVEL = "Sinto muito pelo transtorno. Já abri um atendimento com a nossa equipe para resolver isso."
MSG_BOAS_VINDAS = (
    "Oi! Sou a assistente virtual do {empresa}. Posso te ajudar com:\n"
    "• produtos e preços (varejo e atacado)\n"
    "• pedido mínimo e compras no atacado\n"
    "• prazos de entrega e frete\n"
    "• trocas, devoluções e garantia\n"
    "• camisetas personalizadas com a sua logo\n"
    'É só perguntar. Se preferir falar com uma pessoa, escreva "atendente".'
)
MSG_FORA_DO_ESCOPO = (
    "Esse assunto foge do que eu consigo ajudar por aqui. "
    "Posso tirar dúvidas sobre produtos, preços, atacado, entregas, trocas e personalização."
)
_CITACAO = re.compile(r"\s*\[(\d+)\]")


class LLMExtrativo:
    """Sem modelo: devolve o melhor trecho. Serve ao CI e a demos sem GPU."""

    def conversar(self, mensagens: list[dict[str, str]]) -> tuple[str, Uso]:
        conteudo = mensagens[-1]["content"]
        inicio = conteudo.find(">\n", conteudo.find("<documento ")) + 2
        fim = conteudo.find("\n</documento>", inicio)
        corpo = conteudo[inicio:fim].split("\n\n", 1)[-1] if inicio > 1 else prompt.SEM_RESPOSTA
        return f"{corpo.strip()} [1]", Uso()


@dataclass
class Atendente:
    empresa: str
    buscador: Buscador
    llm: LLM
    repo: Repositorio
    config: Config
    embedder: Embedder | None = None

    @classmethod
    def a_partir_da_config(cls, config: Config) -> "Atendente":
        trechos = carregar_trechos(config.empresa_dir)
        embedder: ClienteOpenAICompat | None = None
        vetores = None
        if config.embed_modelo and not config.modo_demo:
            embedder = ClienteOpenAICompat(config.llm_base_url, config.llm_api_key, config.embed_modelo)
            try:
                vetores = vetores_com_cache(trechos, embedder, config.embed_modelo, config.cache_dir)
            except Exception:
                log.warning("embeddings indisponíveis; busca só com BM25", exc_info=True)
                embedder = None
        llm: LLM = (
            LLMExtrativo()
            if config.modo_demo
            else ClienteOpenAICompat(config.llm_base_url, config.llm_api_key, config.llm_modelo)
        )
        log.info("base carregada: %d trechos, embeddings=%s", len(trechos), vetores is not None)
        return cls(
            empresa=nome_da_empresa(config.empresa_dir),
            buscador=Buscador(trechos, vetores),
            llm=llm,
            repo=Repositorio(config.banco_url),
            config=config,
            embedder=embedder,
        )

    def buscar(self, consulta: str) -> tuple[list[Resultado], float]:
        vetor = None
        if self.embedder is not None:
            try:
                vetor = self.embedder.embutir([prefixo_consulta(consulta)])[0]
            except Exception:
                log.warning("falha no embedding da consulta; usando só BM25", exc_info=True)
        return self.buscador.buscar(consulta, self.config.top_k, vetor)

    def responder(
        self, mensagem: str, conversa_id: str | None = None, canal: str = "web", contato: str | None = None
    ) -> tuple[str, Resposta]:
        conversa_id = self.repo.obter_ou_criar_conversa(conversa_id, canal, contato)
        texto = seguranca.limpar(mensagem)
        injecao = seguranca.parece_injecao(texto)
        historico = self.repo.historico(conversa_id, self.config.historico_max)
        self.repo.registrar(conversa_id, "user", texto, suspeita_injecao=injecao)
        if injecao:
            log.warning("possível prompt injection na conversa %s", conversa_id)

        resposta = self._decidir(texto, historico)
        resposta.suspeita_injecao = injecao
        if resposta.motivo_escalonamento:
            ticket = self.repo.abrir_ticket(conversa_id, resposta.motivo_escalonamento, texto)
            log.info(
                "escalou conversa %s (ticket %d, %s)", conversa_id, ticket, resposta.motivo_escalonamento
            )
        self.repo.registrar(
            conversa_id,
            "assistant",
            resposta.texto,
            fontes=resposta.fontes,
            confianca=resposta.confianca,
            tokens_entrada=resposta.uso.tokens_entrada,
            tokens_saida=resposta.uso.tokens_saida,
        )
        return conversa_id, resposta

    def _decidir(self, texto: str, historico: list[tuple[str, str]]) -> Resposta:
        motivo = escalonamento.motivo_por_mensagem(texto)
        if motivo is Motivo.PEDIDO_HUMANO:
            return Resposta(MSG_HUMANO, motivo_escalonamento=motivo)
        if motivo is None and escalonamento.e_saudacao_ou_vaga(texto):
            return Resposta(MSG_BOAS_VINDAS.format(empresa=self.empresa))

        consulta = texto
        # Pergunta curta de continuação ("e no atacado?") herda o contexto da anterior.
        anteriores = [t for p, t in historico if p == "user"]
        if len(tokens(texto)) < 3 and anteriores:
            consulta = f"{anteriores[-1]} {texto}"
        resultados, confianca = self.buscar(consulta)

        if motivo is Motivo.TEMA_SENSIVEL:
            # Escala sempre, mas ainda informa a política se ela estiver nos documentos.
            if confianca >= self.config.limiar_confianca:
                r = self._gerar(texto, resultados, historico, confianca)
                if r.motivo_escalonamento is None:
                    r.texto = f"{MSG_SENSIVEL} Enquanto isso: {r.texto}"
                    r.motivo_escalonamento = motivo
                    return r
            return Resposta(MSG_SENSIVEL + " " + MSG_HUMANO, motivo_escalonamento=motivo, confianca=confianca)

        if confianca < self.config.limiar_confianca:
            return Resposta(
                MSG_SEM_RESPOSTA, motivo_escalonamento=Motivo.BAIXA_CONFIANCA, confianca=confianca
            )
        return self._gerar(texto, resultados, historico, confianca)

    def _gerar(
        self,
        texto: str,
        resultados: list[Resultado],
        historico: list[tuple[str, str]],
        confianca: float,
    ) -> Resposta:
        hist = [
            (p, f"<mensagem_cliente>\n{t}\n</mensagem_cliente>" if p == "user" else t) for p, t in historico
        ]
        mensagens = prompt.montar(self.empresa, texto, resultados, hist)
        saida, uso = self.llm.conversar(mensagens)
        if prompt.FORA_DO_ESCOPO in saida:
            return Resposta(MSG_FORA_DO_ESCOPO, fora_do_escopo=True, confianca=confianca, uso=uso)
        if prompt.SEM_RESPOSTA in saida or not saida:
            return Resposta(
                MSG_SEM_RESPOSTA, motivo_escalonamento=Motivo.SEM_RESPOSTA, confianca=confianca, uso=uso
            )
        citados = {int(n) for n in _CITACAO.findall(saida) if 0 < int(n) <= len(resultados)}
        fontes = [resultados[n - 1].trecho.id for n in sorted(citados)] or [resultados[0].trecho.id]
        limpo = _CITACAO.sub("", saida).strip()
        return Resposta(limpo, fontes=fontes, confianca=confianca, uso=uso)
