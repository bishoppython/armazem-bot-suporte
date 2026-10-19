"""Divide documentos Markdown e itens do catálogo em trechos indexáveis."""

from typing import Any

from bot_suporte.domain.modelos import Trecho

TAMANHO_MAX = 700


def dividir_markdown(doc: str, conteudo: str) -> list[Trecho]:
    linhas = conteudo.strip().splitlines()
    titulo = doc
    if linhas and linhas[0].startswith("# "):
        titulo = linhas[0][2:].strip()
        linhas = linhas[1:]

    paragrafos = [p.strip() for p in "\n".join(linhas).split("\n\n") if p.strip()]
    blocos: list[str] = []
    atual = ""
    for p in paragrafos:
        if atual and len(atual) + len(p) > TAMANHO_MAX:
            blocos.append(atual)
            atual = p
        else:
            atual = f"{atual}\n\n{p}" if atual else p
    if atual:
        blocos.append(atual)

    return [
        Trecho(id=f"{doc}#{i}", doc=doc, titulo=titulo, texto=f"{titulo}\n\n{b}")
        for i, b in enumerate(blocos)
    ]


def _reais(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def trecho_do_produto(item: dict[str, Any]) -> Trecho:
    estoque = int(item["estoque"])
    disponibilidade = (
        f"Em estoque: {estoque} unidades." if estoque > 0 else "Esgotado no momento, sem previsão."
    )
    texto = (
        f"Produto {item['nome']} (código {item['sku']}, categoria {item['categoria']}).\n"
        f"{item['descricao']}\n"
        f"Preço no varejo: {_reais(item['preco_varejo'])}. "
        f"Preço no atacado (a partir de 12 peças): {_reais(item['preco_atacado'])}.\n"
        f"Tamanhos: {', '.join(item['tamanhos'])}. Cores: {', '.join(item['cores'])}.\n"
        f"{disponibilidade}"
    )
    return Trecho(id=f"catalogo#{item['sku']}", doc="catalogo", titulo=item["nome"], texto=texto)
