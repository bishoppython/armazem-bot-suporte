"""Linha de comando: bot perguntar | servir | avaliar."""

import json
import logging
from pathlib import Path

import typer

from bot_suporte.config import Config

app = typer.Typer(no_args_is_help=True, help="Bot de suporte com RAG do Armazém Agreste.")


def _log() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@app.command()
def perguntar(mensagem: str, demo: bool = typer.Option(False, help="Sem LLM, resposta extrativa.")) -> None:
    """Faz uma pergunta e mostra resposta, fontes e decisão de escalonamento."""
    from bot_suporte.servico import Atendente

    _log()
    config = Config(modo_demo=demo, banco_url="sqlite:///:memory:") if demo else Config()
    _, r = Atendente.a_partir_da_config(config).responder(mensagem, canal="cli")
    typer.echo(r.texto)
    typer.echo(f"\nfontes={r.fontes} confianca={r.confianca} escalou={r.motivo_escalonamento}")


@app.command()
def servir(host: str = "127.0.0.1", porta: int = 8000) -> None:
    """Sobe a API e a página de chat."""
    import uvicorn

    _log()
    uvicorn.run("bot_suporte.api:app", host=host, port=porta)


@app.command()
def avaliar(
    arquivo: Path = Path("avaliacao/perguntas.jsonl"),
    demo: bool = typer.Option(False, help="Só busca e escalonamento, sem LLM."),
    saida: Path | None = None,
    minimo: float = typer.Option(0.0, help="Falha (exit 1) se a nota geral ficar abaixo."),
) -> None:
    """Roda o conjunto de avaliação e imprime as métricas."""
    from bot_suporte.avaliacao import avaliar as rodar

    _log()
    config = Config(modo_demo=demo, banco_url="sqlite:///:memory:")
    relatorio = rodar(config, arquivo)
    typer.echo(json.dumps(relatorio["metricas"], indent=2, ensure_ascii=False))
    if saida:
        saida.write_text(json.dumps(relatorio, indent=2, ensure_ascii=False), encoding="utf-8")
    if relatorio["metricas"]["nota_geral"] < minimo:
        raise typer.Exit(1)
