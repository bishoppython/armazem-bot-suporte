from pathlib import Path

import pytest

from bot_suporte.config import Config
from bot_suporte.servico import Atendente

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        empresa_dir=RAIZ / "empresas" / "armazem-agreste",
        banco_url="sqlite:///:memory:",
        cache_dir=tmp_path / "cache",
        modo_demo=True,
    )


@pytest.fixture
def atendente(config: Config) -> Atendente:
    return Atendente.a_partir_da_config(config)
