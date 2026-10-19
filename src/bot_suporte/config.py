"""Configuração lida do ambiente (prefixo BOT_) ou de um arquivo .env."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BOT_", extra="ignore")

    empresa_dir: Path = Path("empresas/armazem-agreste")
    banco_url: str = "sqlite:///dados/bot.db"
    cache_dir: Path = Path("dados/cache")

    # Qualquer servidor compatível com a API da OpenAI: Ollama, Groq, OpenRouter, OmniRoute.
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_modelo: str = "qwen3.5:4b"
    # Vazio desliga os embeddings e a busca fica só com BM25.
    embed_modelo: str = "nomic-embed-text"

    # Modo demo: sem LLM, responde com o trecho mais relevante. Usado no CI e em demos sem GPU.
    modo_demo: bool = False

    # Canal WhatsApp (Evolution API v2). Vazio desliga o webhook.
    evolution_url: str = ""
    evolution_api_key: str = ""
    evolution_instancia: str = "armazem-agreste"

    top_k: int = 4
    limiar_confianca: float = 0.35
    historico_max: int = 6
