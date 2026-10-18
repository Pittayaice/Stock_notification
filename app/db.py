import re
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    line_user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    active: Mapped[bool] = mapped_column(default=True)
    daily_summary: Mapped[bool] = mapped_column(default=False)
    alerts_on: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Holding(Base):
    __tablename__ = "holdings"
    __table_args__ = (UniqueConstraint("user_id", "symbol", "market"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.line_user_id"), index=True)
    symbol: Mapped[str] = mapped_column(String(16))
    market: Mapped[str] = mapped_column(String(8))
    qty: Mapped[float] = mapped_column(Float)
    avg_price: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Realized(Base):
    """One row per sell, so realized P/L can be reported per day, month or year later."""

    __tablename__ = "realized"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.line_user_id"), index=True)
    symbol: Mapped[str] = mapped_column(String(16))
    market: Mapped[str] = mapped_column(String(8))
    qty: Mapped[float] = mapped_column(Float)
    sell_price: Mapped[float] = mapped_column(Float)
    avg_price: Mapped[float] = mapped_column(Float)
    pnl: Mapped[float] = mapped_column(Float)
    sold_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MarketDay(Base):
    """Latest trading day per market that a daily summary has already covered."""

    __tablename__ = "market_days"

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    last_reported: Mapped[date] = mapped_column(Date)


def make_session_factory(database_url: str) -> sessionmaker:
    kwargs: dict = {}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if database_url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool  # share one in-memory DB across threads
    else:
        # Neon/Supabase hand out postgres:// or postgresql:// URLs; use the psycopg 3 driver
        database_url = re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", database_url)
        kwargs["pool_pre_ping"] = True  # serverless Postgres closes idle connections
        kwargs["connect_args"] = {"prepare_threshold": None}  # also works through connection poolers
    engine = create_engine(database_url, **kwargs)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)
