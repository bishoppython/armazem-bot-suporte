"""API HTTP: chat web, tickets e custo."""

import json
from functools import lru_cache
from importlib.resources import files
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from bot_suporte.adapters.whatsapp import EvolutionAPI, extrair_mensagem
from bot_suporte.config import Config
from bot_suporte.servico import Atendente


class PedidoChat(BaseModel):
    mensagem: str = Field(min_length=1, max_length=2000)
    conversa_id: str | None = None


class RespostaChat(BaseModel):
    conversa_id: str
    resposta: str
    fontes: list[str]
    escalou: bool
    motivo: str | None
    confianca: float
    fora_do_escopo: bool = False
    imagens: list[str] = []


@lru_cache
def atendente() -> Atendente:
    return Atendente.a_partir_da_config(Config())


Dep = Annotated[Atendente, Depends(atendente)]


@lru_cache
def evolution() -> EvolutionAPI | None:
    c = Config()
    if not c.evolution_url:
        return None
    return EvolutionAPI(c.evolution_url, c.evolution_api_key, c.evolution_instancia)


DepWhats = Annotated[EvolutionAPI | None, Depends(evolution)]


def criar_app() -> FastAPI:
    app = FastAPI(title="Bot de Suporte — Armazém Agreste", version="0.1.0")
    config = Config()
    catalogo = config.empresa_dir / "catalogo"
    if catalogo.is_dir():
        app.mount("/catalogo", StaticFiles(directory=catalogo), name="catalogo")
    arquivo = config.empresa_dir / "catalogo.json"
    imagens = (
        {i["sku"]: f"/{i['imagem']}" for i in json.loads(arquivo.read_text(encoding="utf-8"))}
        if arquivo.exists()
        else {}
    )

    @app.get("/", response_class=HTMLResponse)
    def pagina() -> str:
        return (files("bot_suporte") / "web" / "index.html").read_text(encoding="utf-8")

    @app.get("/saude")
    def saude() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/chat", response_model=RespostaChat)
    def chat(pedido: PedidoChat, at: Dep) -> RespostaChat:
        conversa_id, r = at.responder(pedido.mensagem, pedido.conversa_id)
        return RespostaChat(
            conversa_id=conversa_id,
            resposta=r.texto,
            fontes=r.fontes,
            escalou=r.escalou,
            motivo=r.motivo_escalonamento,
            confianca=r.confianca,
            fora_do_escopo=r.fora_do_escopo,
            imagens=[
                imagens[f.removeprefix("catalogo#")]
                for f in r.fontes
                if f.removeprefix("catalogo#") in imagens
            ],
        )

    @app.post("/webhook/whatsapp")
    async def webhook_whatsapp(
        request: Request, tarefas: BackgroundTasks, at: Dep, whats: DepWhats
    ) -> dict[str, str]:
        recebida = extrair_mensagem(await request.json())
        if recebida is None or whats is None:
            return {"status": "ignorado"}
        # Responde ao webhook na hora; o LLM roda em segundo plano para a Evolution não reenviar.
        tarefas.add_task(responder_whatsapp, at, whats, *recebida)
        return {"status": "recebido"}

    def responder_whatsapp(at: Atendente, whats: EvolutionAPI, numero: str, texto: str) -> None:
        _, r = at.responder(texto, canal="whatsapp", contato=numero)
        whats.enviar_texto(numero, r.texto)
        for fonte in r.fontes:
            caminho = imagens.get(fonte.removeprefix("catalogo#"))
            if caminho:
                whats.enviar_imagem(numero, config.empresa_dir / caminho.lstrip("/"))

    @app.get("/api/tickets")
    def tickets(at: Dep) -> list[dict[str, object]]:
        return at.repo.tickets()

    @app.get("/api/custo")
    def custo(at: Dep) -> dict[str, int]:
        return at.repo.custo()

    return app


app = criar_app()
