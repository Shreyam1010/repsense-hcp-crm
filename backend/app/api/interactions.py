"""The structured-form write path. The screen offers EITHER a form OR chat — both must be
complete, and both go through interaction_service. Note there is NO PUT and NO PATCH on
/interactions anywhere: amendment is the only write path to a filed record. That absence
is the architecture."""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..services import interaction_service as isvc
from .deps import current_rep

router = APIRouter()

class SubmitBody(BaseModel):
    form: dict[str, Any]
    hcp_id: Optional[str] = None
    thread_id: Optional[str] = None
    interaction_id: Optional[str] = None

class AmendBody(BaseModel):
    changed_fields: dict[str, Any]
    reason_code: str = "rep_correction"
    reason_for_change: str
    expected_version: Optional[int] = None

@router.post("/api/interactions/submit")
async def submit(body: SubmitBody, rep=Depends(current_rep)):
    """File the form as an immutable version 1 (the form-path equivalent of chat commit)."""
    hcp_id = body.hcp_id or body.form.get("hcp_id")
    if not hcp_id:
        raise HTTPException(422, "hcp_id is required to file a call report")
    iid, version = await isvc.file_snapshot(
        body.form, rep_id=rep["id"], territory_id=rep["territory_id"], hcp_id=hcp_id,
        thread_id=body.thread_id, actor_id=rep["id"], interaction_id=body.interaction_id)
    return {"interaction_id": iid, "version": version, "status": "SUBMITTED", "locked": True}

@router.post("/api/interactions/{interaction_id}/amend")
async def amend(interaction_id: str, body: AmendBody, rep=Depends(current_rep)):
    try:
        res = await isvc.amend(
            interaction_id, body.changed_fields, reason_code=body.reason_code,
            reason_for_change=body.reason_for_change, actor_id=rep["id"],
            expected_version=body.expected_version)
    except isvc.ConflictError as e:
        raise HTTPException(409, {"error": "version_conflict", "current_version": e.current_version})
    except ValueError as e:
        raise HTTPException(404, str(e))
    return res.model_dump()

@router.get("/api/interactions/{interaction_id}")
async def get_interaction(interaction_id: str):
    row = await isvc.get_current(interaction_id)
    if not row:
        raise HTTPException(404, "not found")
    return row

@router.get("/api/interactions/{interaction_id}/versions")
async def get_versions(interaction_id: str):
    """The amendment/version chain (append-only)."""
    return await isvc.get_versions(interaction_id)
