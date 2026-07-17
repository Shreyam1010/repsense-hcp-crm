"""Operational endpoints: health, model-info, demo/reset."""
from fastapi import APIRouter

from ..config import settings
from ..db.session import ping, run_seed
from ..model_preflight import model_info

router = APIRouter()

@router.get("/api/health")
async def health():
    db_ok = False
    try:
        db_ok = await ping()
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db": db_ok,
            "groq_key_configured": settings.groq_key_looks_real}

@router.get("/api/model-info")
async def model_info_endpoint():
    """The model-selection story as JSON."""
    return model_info()

@router.post("/api/demo/reset")
async def demo_reset():
    """Truncate + re-seed. Makes a fluffed video take cost two seconds."""
    await run_seed()
    return {"reset": True}
