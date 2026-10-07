import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger, Column, DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, Table, Text, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .config import config
from .util import utcnow

engine = create_async_engine(config.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

TS = DateTime(timezone=True)


class Base(DeclarativeBase):
    pass


# Séries temporelles : hypertables TimescaleDB, donc sans clé primaire (tables Core, pas ORM).
measurements = Table(
    "measurements", Base.metadata,
    Column("time", TS, nullable=False),
    Column("device", String(32), nullable=False),
    Column("sensor", String(32), nullable=False),
    Column("value", Float, nullable=False),
)
Index("ix_measurements_sensor_time", measurements.c.device, measurements.c.sensor, measurements.c.time.desc())

events = Table(
    "events", Base.metadata,
    Column("time", TS, nullable=False),
    Column("device", String(32), nullable=False),
    Column("type", String(32), nullable=False),
    Column("data", JSONB, nullable=False),
)
Index("ix_events_type_time", events.c.device, events.c.type, events.c.time.desc())

HYPERTABLES = ("measurements", "events")


class UserRow(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(default=True)
    must_change_password: Mapped[bool] = mapped_column(default=True)
    last_login: Mapped[datetime | None] = mapped_column(TS)


class SessionRow(Base):
    """Sessions côté serveur : le cookie ne contient qu'un jeton aléatoire, stocké ici haché."""
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(TS)
    ip: Mapped[str] = mapped_column(String(45))


class BadgeRow(Base):
    __tablename__ = "badges"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    uid: Mapped[str] = mapped_column(String(32), unique=True)
    owner: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(default=True)
    last_used: Mapped[datetime | None] = mapped_column(TS)


class TeamMemberRow(Base):
    """Membre de l'équipe reconnu par la caméra : prénom, empreinte du visage (SFace) et miniature."""
    __tablename__ = "team_members"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(32))
    embedding: Mapped[list[float]] = mapped_column(JSONB)
    photo: Mapped[bytes] = mapped_column(LargeBinary)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    last_seen: Mapped[datetime | None] = mapped_column(TS)


class AlertRow(Base):
    __tablename__ = "alerts"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ts: Mapped[datetime] = mapped_column(TS, default=utcnow, index=True)
    level: Mapped[str] = mapped_column(String(16))
    score: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(64))
    reasons: Mapped[list[str]] = mapped_column(JSONB, default=list)
    snapshot_path: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="ouverte")
    ack_by: Mapped[str | None] = mapped_column(String(32))
    ack_at: Mapped[datetime | None] = mapped_column(TS)
    comment: Mapped[str | None] = mapped_column(Text)


class AuditRow(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(TS, default=utcnow, index=True)
    # "user" est un mot réservé en SQL : la colonne s'appelle username.
    username: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(Text)
    ip: Mapped[str] = mapped_column(String(45))
    success: Mapped[bool]


class LogRow(Base):
    """Journal applicatif affiché par la page Journaux (LogEntry)."""
    __tablename__ = "logs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(TS, default=utcnow, index=True)
    level: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text)


class SettingsRow(Base):
    """Une seule ligne (id = 1) : paramètres de détection modifiables depuis le dashboard."""
    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)


async def init_db() -> None:
    """Crée les tables manquantes. À remplacer par des migrations Alembic quand le schéma bougera."""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
        await conn.run_sync(Base.metadata.create_all)
        for table in HYPERTABLES:
            await conn.execute(
                text("SELECT create_hypertable(CAST(:t AS regclass), 'time', if_not_exists => TRUE)"), {"t": table}
            )


async def apply_retention(days: int) -> None:
    async with engine.begin() as conn:
        for table in HYPERTABLES:
            await conn.execute(text("SELECT remove_retention_policy(CAST(:t AS regclass), if_exists => TRUE)"), {"t": table})
            await conn.execute(
                text("SELECT add_retention_policy(CAST(:t AS regclass), make_interval(days => :d))"),
                {"t": table, "d": days},
            )


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
