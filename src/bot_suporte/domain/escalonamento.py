"""Regras que decidem quando a conversa passa para uma pessoa da equipe."""

import re

from bot_suporte.domain.modelos import Motivo
from bot_suporte.domain.texto import sem_acento, tokens

_PEDIDO_HUMANO = re.compile(
    r"\b(atendente|humano|pessoa de verdade|alguem da (loja|equipe)|"
    r"falar com (um |uma |o |a )?(vendedor|vendedora|gerente|atendente|pessoa|alguem))\b"
)
_SENSIVEL = re.compile(
    r"\b(reclama|reclamacao|procon|cobranc|cobrad|reembols|estorn|process|advogad|"
    r"defeit|golpe|fraud|rasgad|furad|nao chegou|veio errad)\w*"
)


def motivo_por_mensagem(mensagem: str) -> Motivo | None:
    texto = sem_acento(mensagem.lower())
    if _PEDIDO_HUMANO.search(texto):
        return Motivo.PEDIDO_HUMANO
    if _SENSIVEL.search(texto):
        return Motivo.TEMA_SENSIVEL
    return None


_SAUDACAO = re.compile(r"^\W*(oi+|ola|opa|e ai|eai|bom dia|boa tarde|boa noite|tudo bem|hello|hi)\b")


def e_saudacao_ou_vaga(mensagem: str) -> bool:
    """Cumprimento ou mensagem sem nenhum termo de conteúdo: pede um menu, não um ticket."""
    termos = tokens(mensagem)
    return not termos or (bool(_SAUDACAO.search(sem_acento(mensagem.lower()))) and len(termos) <= 1)
