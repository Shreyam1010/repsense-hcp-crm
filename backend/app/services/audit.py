"""Append-only audit trail. Every tool call, consent capture, and accepted AI
suggestion writes a row here. The table has a refuse_mutation() trigger, so this is
insert-only by construction."""
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

_INSERT = text("""
    INSERT INTO audit_log (actor_id, actor_type, action, entity_type, entity_id,
                           thread_id, tool_call_id, model_id, before, after, reason)
    VALUES (:actor_id, :actor_type, :action, :entity_type, :entity_id,
            :thread_id, :tool_call_id, :model_id,
            CAST(:before AS JSONB), CAST(:after AS JSONB), :reason)
    RETURNING audit_id
""")

async def write_audit(
    conn: AsyncConnection,
    *,
    actor_id: str,
    actor_type: str,
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    tool_call_id: Optional[str] = None,
    model_id: Optional[str] = None,
    before: Optional[str] = None,
    after: Optional[str] = None,
    reason: Optional[str] = None,
) -> int:
    row = await conn.execute(_INSERT, {
        "actor_id": actor_id, "actor_type": actor_type, "action": action,
        "entity_type": entity_type, "entity_id": entity_id, "thread_id": thread_id,
        "tool_call_id": tool_call_id, "model_id": model_id,
        "before": before, "after": after, "reason": reason,
    })
    return row.scalar_one()
