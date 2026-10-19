"""Carrega os documentos e o catálogo de uma empresa a partir de empresas/<slug>/."""

import hashlib
import json
from pathlib import Path

from bot_suporte.adapters.llm import Embedder
from bot_suporte.domain.chunking import dividir_markdown, trecho_do_produto
from bot_suporte.domain.modelos import Trecho


def carregar_trechos(empresa_dir: Path) -> list[Trecho]:
    trechos: list[Trecho] = []
    for arquivo in sorted((empresa_dir / "docs").glob("*.md")):
        trechos.extend(dividir_markdown(arquivo.stem, arquivo.read_text(encoding="utf-8")))
    catalogo = empresa_dir / "catalogo.json"
    if catalogo.exists():
        for item in json.loads(catalogo.read_text(encoding="utf-8")):
            trechos.append(trecho_do_produto(item))
    return trechos


def nome_da_empresa(empresa_dir: Path) -> str:
    sobre = empresa_dir / "docs" / "sobre-a-empresa.md"
    if sobre.exists():
        primeira = sobre.read_text(encoding="utf-8").splitlines()[0]
        return primeira.removeprefix("# Sobre o ").removeprefix("# Sobre a ").strip()
    return empresa_dir.name


def vetores_com_cache(
    trechos: list[Trecho], embedder: Embedder, modelo: str, cache_dir: Path
) -> list[list[float]]:
    """Embeddings dos trechos, recalculando só o que mudou (chave = hash do texto)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    arquivo = cache_dir / f"embeddings-{modelo.replace('/', '_').replace(':', '_')}.json"
    cache: dict[str, list[float]] = json.loads(arquivo.read_text()) if arquivo.exists() else {}
    chaves = [hashlib.sha256(t.texto.encode()).hexdigest()[:16] for t in trechos]
    faltando = [i for i, c in enumerate(chaves) if c not in cache]
    if faltando:
        novos = embedder.embutir([_prefixo_doc(trechos[i].texto) for i in faltando])
        for i, v in zip(faltando, novos, strict=True):
            cache[chaves[i]] = v
        arquivo.write_text(json.dumps({c: cache[c] for c in chaves}))
    return [cache[c] for c in chaves]


# O nomic-embed-text pede prefixos de tarefa diferentes para documento e consulta.
def _prefixo_doc(texto: str) -> str:
    return f"search_document: {texto}"


def prefixo_consulta(texto: str) -> str:
    return f"search_query: {texto}"
