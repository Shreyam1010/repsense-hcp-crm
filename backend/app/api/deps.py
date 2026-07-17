"""Request dependencies. Auth is stubbed: one hardcoded rep. The point is that actor_id
and territory_id are SERVER-INJECTED here and never model-supplied — the seam for real
auth is visible, and the governance story is intact."""
from ..config import settings

def current_rep() -> dict:
    return {"id": settings.rep_id, "territory_id": settings.territory_id, "full_name": "Aarav Menon"}
