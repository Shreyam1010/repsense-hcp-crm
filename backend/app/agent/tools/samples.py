"""record_sample_distribution — the PDMA disbursement record with five hard-fails.
A REJECT does not lose the rep's work: the line is flagged and the parent report is
blocked from SUBMIT, so the rep gets a path forward instead of a dead end."""
import json
from typing import Optional

from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.types import Command
from pydantic import BaseModel, Field

from ...schemas import _coerce_int
from ...services import sample_service

class SampleArgs(BaseModel):
    hcp_id: str = Field(..., description="Resolved HCP id — the recipient (must be a prescriber).")
    product_id: str = Field(..., description="Product brand or id, e.g. 'OncoBoost' or 'PRD-ONC'.")
    lot_number: str = Field(..., description="The physical lot number, e.g. OB-2410-A.")
    quantity: str = Field(..., description="Number of sample units, e.g. '2'.")
    delivery_method: str = Field("hand_delivered", description="hand_delivered | mail_direct")
    signature_artifact_ref: Optional[str] = Field(None, description="Signature capture ref, if collected.")

@tool(args_schema=SampleArgs)
async def record_sample_distribution(*, runtime: ToolRuntime, **kw) -> Command:
    """Record a sample disbursement. Enforces lot validity, expiry, recipient eligibility,
    and annual limits. If it REJECTS, relay the reason and the suggested valid alternative;
    do not retry the same rejected input."""
    try:
        state = runtime.state or {}
        qty = _coerce_int(kw["quantity"])
        if not isinstance(qty, int) or qty <= 0:
            return Command(update={"messages": [ToolMessage(
                content=json.dumps({"error": f"invalid quantity: {kw['quantity']!r}"}),
                tool_call_id=runtime.tool_call_id)]})
        r = await sample_service.record_sample_distribution(
            hcp_id=kw["hcp_id"], product_id=kw["product_id"], lot_number=kw["lot_number"],
            quantity=qty, rep_id=state.get("rep_id", "REP-001"),
            interaction_id=state.get("interaction_id"),
            delivery_method=kw.get("delivery_method", "hand_delivered"),
            signature_artifact_ref=kw.get("signature_artifact_ref"))
        if runtime.stream_writer:
            runtime.stream_writer({"event": "tool_call", "data": {
                "name": "record_sample_distribution", "status": r["status"].lower()}})
            if r["status"] == "REJECTED":
                runtime.stream_writer({"event": "sample_rejected", "data": r})
        return Command(update={"messages": [ToolMessage(
            content=json.dumps(r), tool_call_id=runtime.tool_call_id)]})
    except Exception as e:
        return Command(update={"messages": [ToolMessage(
            content=f"TOOL_ERROR record_sample_distribution: {e}", tool_call_id=runtime.tool_call_id)]})
