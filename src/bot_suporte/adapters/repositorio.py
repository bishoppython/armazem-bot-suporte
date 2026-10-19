"""Conversas, mensagens e tickets de escalonamento (SQLAlchemy; SQLite no dev, Postgres em produção)."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import ForeignKey, String, Text, create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


def _agora() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Conversa(Base):
    __tablename__ = "conversa"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    canal: Mapped[str] = mapped_column(String(20))
    contato: Mapped[str | None] = mapped_column(String(64))
    criada_em: Mapped[datetime] = mapped_column(default=_agora)


class Mensagem(Base):
    __tablename__ = "mensagem"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversa_id: Mapped[str] = mapped_column(ForeignKey("conversa.id", ondelete="CASCADE"))
    papel: Mapped[str] = mapped_column(String(10))
    texto: Mapped[str] = mapped_column(Text)
    fontes: Mapped[str] = mapped_column(Text, default="[]")
    confianca: Mapped[float | None]
    suspeita_injecao: Mapped[bool] = mapped_column(default=False)
    tokens_entrada: Mapped[int] = mapped_column(default=0)
    tokens_saida: Mapped[int] = mapped_column(default=0)
    criada_em: Mapped[datetime] = mapped_column(default=_agora)


class Ticket(Base):
    __tablename__ = "ticket"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversa_id: Mapped[str] = mapped_column(ForeignKey("conversa.id", ondelete="CASCADE"))
    motivo: Mapped[str] = mapped_column(String(30))
    ultima_mensagem: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="aberto")
    criado_em: Mapped[datetime] = mapped_column(default=_agora)


class Repositorio:
    def __init__(self, url: str) -> None:
        if url.startswith("sqlite:///") and not url.endswith(":memory:"):
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        if url == "sqlite:///:memory:":
            # Uma conexão só, compartilhada entre threads: senão cada sessão vê um banco vazio.
            self._engine = create_engine(url, poolclass=StaticPool, connect_args={"check_same_thread": False})
        else:
            self._engine = create_engine(url)
        Base.metadata.create_all(self._engine)
        self._sessao = sessionmaker(self._engine, expire_on_commit=False)

    def _s(self) -> Session:
        return self._sessao()

    def obter_ou_criar_conversa(self, conversa_id: str | None, canal: str, contato: str | None = None) -> str:
        with self._s() as s, s.begin():
            if conversa_id and s.get(Conversa, conversa_id):
                return conversa_id
            if contato:
                existente = s.scalars(
                    select(Conversa.id).where(Conversa.canal == canal, Conversa.contato == contato)
                ).first()
                if existente:
                    return existente
            novo = conversa_id or str(uuid.uuid4())
            s.add(Conversa(id=novo, canal=canal, contato=contato))
            return novo

    def historico(self, conversa_id: str, limite: int) -> list[tuple[str, str]]:
        with self._s() as s:
            linhas = s.scalars(
                select(Mensagem)
                .where(Mensagem.conversa_id == conversa_id)
                .order_by(Mensagem.id.desc())
                .limit(limite)
            ).all()
        return [(m.papel, m.texto) for m in reversed(linhas)]

    def registrar(
        self,
        conversa_id: str,
        papel: str,
        texto: str,
        *,
        fontes: list[str] | None = None,
        confianca: float | None = None,
        suspeita_injecao: bool = False,
        tokens_entrada: int = 0,
        tokens_saida: int = 0,
    ) -> None:
        with self._s() as s, s.begin():
            s.add(
                Mensagem(
                    conversa_id=conversa_id,
                    papel=papel,
                    texto=texto,
                    fontes=json.dumps(fontes or []),
                    confianca=confianca,
                    suspeita_injecao=suspeita_injecao,
                    tokens_entrada=tokens_entrada,
                    tokens_saida=tokens_saida,
                )
            )

    def abrir_ticket(self, conversa_id: str, motivo: str, ultima_mensagem: str) -> int:
        with self._s() as s, s.begin():
            aberto = s.scalars(
                select(Ticket).where(Ticket.conversa_id == conversa_id, Ticket.status == "aberto")
            ).first()
            if aberto:
                return aberto.id
            t = Ticket(conversa_id=conversa_id, motivo=motivo, ultima_mensagem=ultima_mensagem)
            s.add(t)
            s.flush()
            return t.id

    def tickets(self, status: str = "aberto") -> list[dict[str, object]]:
        with self._s() as s:
            linhas = s.scalars(select(Ticket).where(Ticket.status == status).order_by(Ticket.id.desc())).all()
        return [
            {
                "id": t.id,
                "conversa_id": t.conversa_id,
                "motivo": t.motivo,
                "ultima_mensagem": t.ultima_mensagem,
                "criado_em": t.criado_em.isoformat(),
            }
            for t in linhas
        ]

    def custo(self) -> dict[str, int]:
        with self._s() as s:
            ms = s.scalars(select(Mensagem).where(Mensagem.papel == "assistant")).all()
        return {
            "respostas": len(ms),
            "tokens_entrada": sum(m.tokens_entrada for m in ms),
            "tokens_saida": sum(m.tokens_saida for m in ms),
        }

    def apagar_antigas(self, dias: int = 90) -> int:
        """Retenção da LGPD: conversas mais velhas que `dias` saem do banco."""
        limite = _agora() - timedelta(days=dias)
        with self._s() as s, s.begin():
            ids = s.scalars(select(Conversa.id).where(Conversa.criada_em < limite)).all()
            for tabela in (Mensagem, Ticket):
                s.execute(delete(tabela).where(tabela.conversa_id.in_(ids)))
            s.execute(delete(Conversa).where(Conversa.id.in_(ids)))
            return len(ids)
