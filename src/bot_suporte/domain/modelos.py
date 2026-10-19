from dataclasses import dataclass, field
from enum import StrEnum


@dataclass(frozen=True)
class Trecho:
    id: str
    doc: str
    titulo: str
    texto: str


@dataclass(frozen=True)
class Resultado:
    trecho: Trecho
    score: float


class Motivo(StrEnum):
    PEDIDO_HUMANO = "pedido_humano"
    TEMA_SENSIVEL = "tema_sensivel"
    BAIXA_CONFIANCA = "baixa_confianca"
    SEM_RESPOSTA = "sem_resposta"


@dataclass
class Uso:
    tokens_entrada: int = 0
    tokens_saida: int = 0


@dataclass
class Resposta:
    texto: str
    fontes: list[str] = field(default_factory=list)
    motivo_escalonamento: Motivo | None = None
    confianca: float = 0.0
    suspeita_injecao: bool = False
    fora_do_escopo: bool = False
    uso: Uso = field(default_factory=Uso)

    @property
    def escalou(self) -> bool:
        return self.motivo_escalonamento is not None
