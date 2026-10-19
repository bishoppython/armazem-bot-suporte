import json
from typing import Any

import httpx
from fastapi.testclient import TestClient

from bot_suporte import api
from bot_suporte.adapters.whatsapp import EvolutionAPI, extrair_mensagem
from bot_suporte.servico import Atendente


def _evento(
    texto: str, *, from_me: bool = False, jid: str = "5581900000000@s.whatsapp.net"
) -> dict[str, Any]:
    return {
        "event": "messages.upsert",
        "instance": "armazem-agreste",
        "data": {"key": {"remoteJid": jid, "fromMe": from_me, "id": "X"}, "message": {"conversation": texto}},
    }


def test_extrai_texto_e_numero() -> None:
    assert extrair_mensagem(_evento("oi")) == ("5581900000000", "oi")
    estendida = _evento("")
    estendida["data"]["message"] = {"extendedTextMessage": {"text": "tem G?"}}
    assert extrair_mensagem(estendida) == ("5581900000000", "tem G?")


def test_ignora_proprio_numero_grupo_e_outros_eventos() -> None:
    assert extrair_mensagem(_evento("oi", from_me=True)) is None
    assert extrair_mensagem(_evento("oi", jid="1203630@g.us")) is None
    assert extrair_mensagem({"event": "connection.update"}) is None


def test_webhook_responde_no_whatsapp_com_foto_do_produto(atendente: Atendente) -> None:
    enviados: list[tuple[str, dict[str, Any]]] = []

    def registrar(req: httpx.Request) -> httpx.Response:
        enviados.append((req.url.path, json.loads(req.content)))
        return httpx.Response(201, json={})

    whats = EvolutionAPI("http://evo", "chave", "armazem-agreste", transport=httpx.MockTransport(registrar))
    app = api.criar_app()
    app.dependency_overrides[api.atendente] = lambda: atendente
    app.dependency_overrides[api.evolution] = lambda: whats
    r = TestClient(app).post("/webhook/whatsapp", json=_evento("Quanto custa a camiseta branca?"))

    assert r.json() == {"status": "recebido"}
    caminhos = [c for c, _ in enviados]
    assert caminhos == ["/message/sendText/armazem-agreste", "/message/sendMedia/armazem-agreste"]
    assert "59,90" in enviados[0][1]["text"]
    assert enviados[1][1]["mediatype"] == "image"
    # A conversa fica ligada ao número: a próxima mensagem cai na mesma conversa.
    assert atendente.repo.obter_ou_criar_conversa(None, "whatsapp", "5581900000000")
