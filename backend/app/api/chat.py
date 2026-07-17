"""The conversational path — one SSE endpoint the whole app hangs off.

SSE, not WebSocket: nothing flows client->server mid-stream (the rep's message IS the
POST body), so SSE is strictly simpler. EventSource can't send a POST body, which is why
the frontend uses fetch + ReadableStream + eventsource-parser."""
import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ..config import settings
from .deps import current_rep

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None

@router.post("/api/conversations")
async def new_conversation():
    return {"conversation_id": f"conv-{uuid.uuid4()}"}

@router.get("/api/threads/{tid}/state")
async def thread_state(tid: str, request: Request):
    """Hydrate the UI on refresh: form values + chat transcript from the checkpointer."""
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        return {"form": {}, "messages": [], "available": False}
    cfg = {"configurable": {"thread_id": tid}}
    snap = await agent.aget_state(cfg)
    vals = snap.values if snap else {}
    msgs = []
    for m in vals.get("messages", []):
        role = getattr(m, "type", "")
        content = getattr(m, "content", "")
        if role in ("human", "ai") and content:
            msgs.append({"role": "user" if role == "human" else "assistant", "content": content})
    return {"form": vals.get("form", {}), "messages": msgs,
            "interaction_id": vals.get("interaction_id"), "available": True}

@router.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, request: Request, rep=Depends(current_rep)):
    from langchain.messages import HumanMessage

    agent = getattr(request.app.state, "agent", None)
    conv_id = req.conversation_id or f"conv-{uuid.uuid4()}"
    cfg = {"configurable": {"thread_id": conv_id}, "recursion_limit": 20}
    inp = {"messages": [HumanMessage(req.message)], "rep_id": rep["id"], "territory_id": rep["territory_id"]}

    async def gen():
        if agent is None:
            yield {"event": "error", "data": json.dumps(
                {"code": "no_agent", "message": "Agent not initialized — set GROQ_API_KEY in .env and restart."})}
            yield {"event": "done", "data": json.dumps({"conversation_id": conv_id})}
            return
        try:
            from groq import BadRequestError, RateLimitError
            try:
                async for mode, chunk in agent.astream(
                        inp, config=cfg, stream_mode=["messages", "updates", "custom"]):
                    if mode == "messages":
                        msg, meta = chunk
                        if getattr(msg, "content", None) and meta.get("langgraph_node") == "model":
                            yield {"event": "token", "data": json.dumps(msg.content)}
                    elif mode == "updates":
                        for node, payload in chunk.items():
                            if not isinstance(payload, dict):
                                continue
                            if payload.get("form"):
                                yield {"event": "form_patch", "data": json.dumps(payload["form"])}
                            for f in payload.get("compliance_flags", []) or []:
                                yield {"event": "compliance_flag", "data": json.dumps(f)}
                            if node == "model":
                                for m in payload.get("messages", []) or []:
                                    for tc in getattr(m, "tool_calls", None) or []:
                                        yield {"event": "tool_call", "data": json.dumps(
                                            {"name": tc["name"], "status": "running"})}
                    elif mode == "custom":
                        yield {"event": chunk.get("event", "custom"), "data": json.dumps(chunk.get("data"))}
            except BadRequestError as e:
                if "tool_use_failed" not in str(e):
                    raise
                from ..agent.fallback import extract_fallback
                async for ev in extract_fallback(agent, req.message, cfg, rep):
                    yield ev
            except RateLimitError as e:
                yield {"event": "error", "data": json.dumps(
                    {"code": "rate_limited", "message": "Groq free-tier limit hit — wait a moment.",
                     "retry_after": getattr(e, "retry_after", 30)})}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"code": "agent_error", "message": str(e)[:300]})}
        yield {"event": "done", "data": json.dumps({"conversation_id": conv_id})}

    return EventSourceResponse(gen(), headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})
