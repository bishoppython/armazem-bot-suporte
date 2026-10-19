"""Normalização de texto em português para a busca lexical."""

import re
import unicodedata

STOPWORDS = frozenset(
    """
    a o as os um uma uns umas de do da dos das em no na nos nas por pelo pela pelos pelas
    para pra com sem e ou que se ao aos à às é ser foi são está estão tem ter há eu voce vc
    vcs voces me te lhe nos vos meu minha seu sua qual quais quanto quanta como onde quando
    porque pq isso esse essa este esta aquilo mais menos muito pouco ja ainda tambem so sim
    nao oi ola bom boa dia tarde noite obrigado obrigada favor gostaria queria quero saber
    pode posso vocês vou ate entre veio vem funciona fica fazer faz tenho preciso precisa
    dar da existe alguma algum vcs
    """.split()
)

_SINONIMOS = {
    "custa": "preco",
    "custo": "preco",
    "valor": "preco",
    "preco": "preco",
    "precos": "preco",
    "devolver": "devoluc",
    "devolvo": "devoluc",
    "trocar": "troca",
    "abre": "horar",
    "fecha": "horar",
    "aberto": "horar",
    "chega": "entre",
    "chegar": "entre",
    "demora": "prazo",
    "pagar": "pagam",
    "parcelar": "parcel",
    "parcela": "parcel",
    "tamanho": "tamanh",
    "medida": "medid",
    "mínimo": "minim",
    "personalizar": "person",
    "logo": "logom",
    "logomarca": "logom",
}

_TOKEN = re.compile(r"[a-z0-9]+")


def sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def radical(palavra: str) -> str:
    """Radical grosseiro por prefixo: estável, sem dependência e suficiente para BM25 em pt-BR."""
    if palavra in _SINONIMOS:
        return _SINONIMOS[palavra]
    if palavra.isdigit():
        return palavra
    return palavra[:5]


def tokens(texto: str) -> list[str]:
    limpo = sem_acento(texto.lower())
    return [radical(p) for p in _TOKEN.findall(limpo) if p not in STOPWORDS and len(p) > 1]
