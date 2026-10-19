"""Canal WhatsApp pela Evolution API v2: lê o webhook messages.upsert e envia as respostas."""

import base64
import logging
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger(__name__)


def extrair_mensagem(evento: dict[str, Any]) -> tuple[str, str] | None:
    """Devolve (número, texto) de uma mensagem de texto recebida, ou None se o evento não interessa."""
    if evento.get("event") != "messages.upsert":
        return None
    dados = evento.get("data") or {}
    chave = dados.get("key") or {}
    jid: str = chave.get("remoteJid", "")
    # Ignora o que o próprio número enviou, grupos e status.
    if chave.get("fromMe") or not jid.endswith("@s.whatsapp.net"):
        return None
    msg = dados.get("message") or {}
    texto = msg.get("conversation") or (msg.get("extendedTextMessage") or {}).get("text")
    if not texto:
        return None
    return jid.split("@")[0], str(texto)


class EvolutionAPI:
    def __init__(
        self, base_url: str, api_key: str, instancia: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.instancia = instancia
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"), headers={"apikey": api_key}, timeout=30, transport=transport
        )

    def enviar_texto(self, numero: str, texto: str) -> None:
        r = self._http.post(f"/message/sendText/{self.instancia}", json={"number": numero, "text": texto})
        r.raise_for_status()

    def enviar_imagem(self, numero: str, arquivo: Path, legenda: str = "") -> None:
        corpo = {
            "number": numero,
            "mediatype": "image",
            "mimetype": "image/jpeg",
            "media": base64.b64encode(arquivo.read_bytes()).decode(),
            "fileName": arquivo.name,
            "caption": legenda,
        }
        r = self._http.post(f"/message/sendMedia/{self.instancia}", json=corpo)
        r.raise_for_status()
