"""suggest_follow_ups tool — emits the 'AI Suggested Follow-ups' chips."""
import json
from typing import Optional

from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.types import Command
from pydantic import BaseModel, Field

from ...services import followup_service, material_service

class SuggestArgs(BaseModel):
    hcp_id: str
    product_id: Optional[str] = Field(None, description="Product context, e.g. PRD-ONC, for material suggestions.")

@tool(args_schema=SuggestArgs)
async def suggest_follow_ups(*, runtime: ToolRuntime, **kw) -> Command:
    """Propose 1-3 next actions from the closed action set. For material sends, only
    approved materials are offered. Nothing auto-executes — the rep accepts each."""
    try:
        state = runtime.state or {}
        draft = state.get("form", {})
        approved_ids: list[str] = []
        if kw.get("product_id"):
            m = await material_service.check_product_material(kw["product_id"])
            approved_ids = [x["material_id"] for x in m["approved_materials"]]
        r = await followup_service.suggest_follow_ups(draft, kw["hcp_id"], approved_ids)
        if runtime.stream_writer and r["suggestions"]:
            runtime.stream_writer({"event": "suggestions", "data": r["suggestions"]})
        return Command(update={"messages": [ToolMessage(
            content=json.dumps(r), tool_call_id=runtime.tool_call_id)]})
    except Exception as e:
        return Command(update={"messages": [ToolMessage(
            content=f"TOOL_ERROR suggest_follow_ups: {e}", tool_call_id=runtime.tool_call_id)]})
