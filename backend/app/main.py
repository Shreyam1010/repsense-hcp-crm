"""FastAPI app. Lifespan wires the Postgres checkpointer and the agent; CORS is on from
day one. The agent + checkpointer are optional at boot so the app still serves health,
model-info, and the REST form path even before a GROQ_API_KEY is set."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .model_preflight import preflight_model

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
log = logging.getLogger("repsense")

@asynccontextmanager
async def lifespan(app: FastAPI):
    preflight_model()
    app.state.agent = None
    app.state._cm = None
    if settings.groq_key_looks_real:
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            from .agent.graph import build_agent
            cm = AsyncPostgresSaver.from_conn_string(settings.checkpointer_dsn)
            saver = await cm.__aenter__()
            await saver.setup()
            app.state.agent = build_agent(saver)
            app.state._cm = cm
            log.info("Agent ready (model=%s).", settings.groq_agent_model)
        except Exception as e:
            log.warning("Agent init failed (%s). Chat disabled; REST + form path still work.", str(e)[:200])
    else:
        log.warning("GROQ_API_KEY not set — chat disabled; REST + form path still work.")
    try:
        yield
    finally:
        if app.state._cm is not None:
            await app.state._cm.__aexit__(None, None, None)

app = FastAPI(title="RepSense — HCP Log Interaction", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from .api import chat, interactions, ops, refdata

app.include_router(ops.router)
app.include_router(refdata.router)
app.include_router(interactions.router)
app.include_router(chat.router)

@app.get("/")
async def root():
    return {"app": "RepSense", "docs": "/docs", "model_info": "/api/model-info"}
