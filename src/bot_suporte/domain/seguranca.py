"""Defesa contra prompt injection vindo da mensagem do cliente.

A defesa principal é estrutural (prompt.py): a mensagem vai delimitada como dado e as regras
ficam no system prompt. Aqui só se detecta e registra a tentativa, e se limpa a entrada.
"""

import re

from bot_suporte.domain.texto import sem_acento

TAMANHO_MAX = 1000

_INJECAO = re.compile(
    r"(ignor\w* (as |todas as |suas )?(instruc|regras|orientac)|"
    r"esquec\w* (as |tudo|suas )|"
    r"(system|sistema) prompt|prompt (do sistema|inicial)|"
    r"voce agora e|a partir de agora voce|finja (ser|que)|aja como|"
    r"modo (desenvolvedor|dev|deus)|jailbreak|"
    r"ignore (all |the |previous |your )|disregard|you are now)"
)
_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TAGS = re.compile(r"</?\s*(documentos|documento|mensagem_cliente|system)[^>]*>", re.I)


def limpar(mensagem: str) -> str:
    texto = _CONTROLE.sub("", mensagem)
    texto = _TAGS.sub("", texto)
    return texto.strip()[:TAMANHO_MAX]


def parece_injecao(mensagem: str) -> bool:
    return bool(_INJECAO.search(sem_acento(mensagem.lower())))
