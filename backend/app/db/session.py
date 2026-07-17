"""Async SQLAlchemy engine + a thin helper to run the seed script.

We use SQLAlchemy's async engine with `text()` SQL in the service/repository layer
rather than the ORM: the domain is a thin header + an append-only JSONB version chain,
which reads far more clearly as explicit SQL than as mapped classes."""
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from ..config import settings

_DB_DIR = Path(__file__).resolve().parent

engine: AsyncEngine = create_async_engine(
    settings.sqlalchemy_dsn,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def ping() -> bool:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return True

def _split_sql(sql: str) -> list[str]:
    """Strip `--` comments, then split on `;`. Safe for seed.sql specifically: it has
    no `--` sequences and no semicolons inside any string literal."""
    stripped = []
    for line in sql.splitlines():
        idx = line.find("--")
        stripped.append(line if idx == -1 else line[:idx])
    return [s.strip() for s in "\n".join(stripped).split(";") if s.strip()]

async def run_seed() -> None:
    """Execute seed.sql (TRUNCATE + reload) in one transaction. Backs POST /api/demo/reset."""
    statements = _split_sql((_DB_DIR / "seed.sql").read_text())
    async with engine.begin() as conn:
        for stmt in statements:
            await conn.execute(text(stmt))
