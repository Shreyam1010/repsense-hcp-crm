"""Seed (or re-seed) the demo dataset. Run after the schema exists:
    cd backend && .venv/bin/python scripts/seed.py
Idempotent (TRUNCATE + reload). Also exposed at runtime as POST /api/demo/reset."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import engine, run_seed

async def main() -> None:
    await run_seed()
    print("Seeded demo dataset (HCPs, products, materials, sample lots, prior interactions).")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
