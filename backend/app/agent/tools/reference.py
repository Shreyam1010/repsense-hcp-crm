"""Read/reference tools: resolve_hcp, check_product_material, get_hcp_history.
These return data to the model (as ToolMessages) and emit UI events; they do not file
anything. resolve_hcp is what makes the agent DECIDE (ask on ambiguity) rather than route."""
import json
from typing import Optional

from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.types import Command
from pydantic import BaseModel, Field

from ...schemas import _coerce_bool, _coerce_int
from ...services import hcp_service, material_service

class ResolveHcpArgs(BaseModel):
    query_text: str = Field(..., description="The spoken or typed HCP name, e.g. 'Dr. Sharma'.")
    specialty_hint: Optional[str] = None

    include_out_of_territory: Optional[str] = Field(None, description="'true' or 'false'.")

@tool(args_schema=ResolveHcpArgs)
async def resolve_hcp(*, runtime: ToolRuntime, **kw) -> Command:
    """Resolve an HCP name to a canonical master record. If more than one candidate is
    returned, you MUST ask the rep which one — do not pick. Never invent an HCP."""
    try:
        state = runtime.state or {}
        r = await hcp_service.resolve_hcp(
            kw["query_text"], state.get("territory_id", "IN-South-02"),
            specialty_hint=kw.get("specialty_hint"),
            include_out_of_territory=_coerce_bool(kw.get("include_out_of_territory")) or False)
        update = {"messages": [ToolMessage(content=json.dumps(r), tool_call_id=runtime.tool_call_id)]}
        if r["action_required"] == "DISAMBIGUATE" and runtime.stream_writer:
            runtime.stream_writer({"event": "clarify", "data": {
                "field": "hcp_id", "question": "Which HCP did you mean?",
                "options": [{"value": c["hcp_id"], "label": f'{c["full_name"]} · {c["specialty"]} · {c["institution"]}'}
                            for c in r["candidates"]]}})
        elif r["action_required"] is None and len(r["candidates"]) == 1:

            update["form"] = {"hcp_id": r["candidates"][0]["hcp_id"]}
        return Command(update=update)
    except Exception as e:
        return Command(update={"messages": [ToolMessage(
            content=f"TOOL_ERROR resolve_hcp: {e}", tool_call_id=runtime.tool_call_id)]})

class CheckMaterialArgs(BaseModel):
    product_id: str = Field(..., description="e.g. PRD-ONC")
    channel: str = Field("in_person", description="in_person | email | remote")
    country: str = Field("IN")

@tool(args_schema=CheckMaterialArgs)
async def check_product_material(*, runtime: ToolRuntime, **kw) -> Command:
    """Return currently MLR-approved materials for a product. You may only share materials
    from this output. It also returns filtered_out assets (expired/withdrawn) with reasons."""
    try:
        r = await material_service.check_product_material(
            kw["product_id"], channel=kw.get("channel", "in_person"), country=kw.get("country", "IN"))
        if runtime.stream_writer and r["filtered_out"]:
            runtime.stream_writer({"event": "materials_filtered", "data": r["filtered_out"]})
        return Command(update={"messages": [ToolMessage(
            content=json.dumps(r), tool_call_id=runtime.tool_call_id)]})
    except Exception as e:
        return Command(update={"messages": [ToolMessage(
            content=f"TOOL_ERROR check_product_material: {e}", tool_call_id=runtime.tool_call_id)]})

class HistoryArgs(BaseModel):
    hcp_id: str = Field(..., description="Resolved HCP id (e.g. HCP-001) or the HCP name (e.g. 'Dr. Priya Sharma').")
    lookback_days: Optional[str] = Field("180", description="Days of history to look back, e.g. '180'.")

@tool(args_schema=HistoryArgs)
async def get_hcp_history(*, runtime: ToolRuntime, **kw) -> Command:
    """Prior interactions and YTD aggregates for an HCP, so follow-ups are contextual."""
    try:
        state = runtime.state or {}
        r = await hcp_service.get_hcp_history(
            kw["hcp_id"], state.get("territory_id", "IN-South-02"),
            lookback_days=_coerce_int(kw.get("lookback_days")) or 180)
        return Command(update={"messages": [ToolMessage(
            content=json.dumps(r), tool_call_id=runtime.tool_call_id)]})
    except Exception as e:
        return Command(update={"messages": [ToolMessage(
            content=f"TOOL_ERROR get_hcp_history: {e}", tool_call_id=runtime.tool_call_id)]})
