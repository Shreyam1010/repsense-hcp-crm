"""The mandated Edit Interaction tool.

Amends a filed record: append-only version N+1, never a destructive UPDATE. Resolves
anaphora ('it', 'that', 'the sentiment') against the current draft/record so the rep can
just say 'actually it went badly'."""
import json
from typing import Optional

from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.types import Command
from pydantic import BaseModel, Field

from ...services import interaction_service as isvc

class EditInteractionArgs(BaseModel):
    changed_fields: dict = Field(
        ..., description="Fields to change, as dotted paths, e.g. {'sentiment.label':'negative', "
                         "'sentiment.barrier_code':'formulary_not_listed'}.")
    reason_for_change: str = Field(..., min_length=10, description="Why the change is being made (Part 11).")
    reason_code: str = Field("rep_correction",
                             description="rep_correction | transcription_error | late_information | "
                                         "compliance_directed | data_entry_error")
    interaction_id: Optional[str] = Field(None, description="Omit to amend the current record on this thread.")
    expected_version: Optional[int] = Field(None, description="Optimistic lock; mismatch -> conflict.")

@tool(args_schema=EditInteractionArgs)
async def edit_interaction(*, runtime: ToolRuntime, **kw) -> Command:
    """Amend a previously logged call report. Use when the rep corrects an earlier statement.
    Creates an append-only new version with a reason — never destroys the original."""
    try:
        state = runtime.state or {}
        iid = kw.get("interaction_id") or state.get("interaction_id")
        if not iid:
            return Command(update={"messages": [ToolMessage(
                content=json.dumps({"error": "no filed interaction on this conversation yet — "
                                             "log_interaction with commit=true first"}),
                tool_call_id=runtime.tool_call_id)]})
        result = await isvc.amend(
            iid, kw["changed_fields"],
            reason_code=kw.get("reason_code", "rep_correction"),
            reason_for_change=kw["reason_for_change"],
            actor_id=state.get("rep_id", "REP-001"),
        )
        if runtime.stream_writer:
            runtime.stream_writer({"event": "tool_call", "data": {"name": "edit_interaction", "status": "ok"}})
            runtime.stream_writer({"event": "amended", "data": {
                "interaction_id": result.interaction_id, "version": result.new_version,
                "status": "AMENDED", "diff": result.diff}})

        form_patch = {}
        for d in result.diff:
            key, to = d["field"], d["to"]
            if "." in key:
                head, tail = key.split(".", 1)
                form_patch.setdefault(head, dict(state.get("form", {}).get(head, {})))
                form_patch[head][tail] = to
            else:
                form_patch[key] = to
        return Command(update={
            "form": form_patch,
            "messages": [ToolMessage(content=json.dumps({
                "interaction_id": result.interaction_id, "new_version": result.new_version,
                "diff": result.diff, "requires_approval": result.requires_approval,
                "audit_id": result.audit_id, "narration": result.narration,
            }), tool_call_id=runtime.tool_call_id)],
        })
    except isvc.ConflictError as e:
        return Command(update={"messages": [ToolMessage(
            content=json.dumps({"error": "version_conflict", "current_version": e.current_version}),
            tool_call_id=runtime.tool_call_id)]})
    except Exception as e:
        return Command(update={"messages": [ToolMessage(
            content=f"TOOL_ERROR edit_interaction: {e}", tool_call_id=runtime.tool_call_id)]})
