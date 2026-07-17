"""Startup model preflight — the gemma2 404 catch, live.

Pings the configured GROQ_AGENT_MODEL with a 1-token request. If Groq returns
model_decommissioned (e.g. someone set GROQ_AGENT_MODEL=gemma2-9b-it), we log a dated
warning, route to the fallback model, and expose a banner. This is what makes the
on-camera demo possible: set the dead model, restart, watch it degrade gracefully."""
import logging

from groq import Groq

from .config import settings

log = logging.getLogger("repsense.preflight")

FALLBACK_MODEL = "openai/gpt-oss-20b"

MODEL_STORY = {
    "spec_mandated_model": "gemma2-9b-it",
    "spec_model_status": "DECOMMISSIONED by Groq 2025-10-08 (announced 2025-08-08)",
    "spec_model_tool_support": "prompted shim only — no tool-use tokens in the Gemma 2 chat template",
    "spec_secondary_model": "llama-3.3-70b-versatile",
    "spec_secondary_status": "LIVE but deprecated — Groq shutdown 2026-08-16",
    "supports_tool_calling": True,
    "supports_strict_json_schema": True,
    "reason": "see README § Model mandate",
    "verified_against": "console.groq.com/docs/deprecations on 2026-07-15",
}

runtime_model_state: dict = {
    "requested_agent_model": settings.groq_agent_model,
    "active_agent_model": settings.groq_agent_model,
    "active_extract_model": settings.groq_extract_model,
    "banner": None,
    "preflight_ran": False,
    "preflight_ok": None,
}

def preflight_model() -> dict:
    runtime_model_state["requested_agent_model"] = settings.groq_agent_model
    runtime_model_state["active_agent_model"] = settings.groq_agent_model
    runtime_model_state["preflight_ran"] = True

    if not settings.groq_key_looks_real:
        runtime_model_state["banner"] = "No GROQ_API_KEY set — add one to .env to use the assistant."
        runtime_model_state["preflight_ok"] = False
        log.warning("GROQ_API_KEY not set; skipping model preflight.")
        return runtime_model_state

    try:
        Groq(api_key=settings.groq_api_key).chat.completions.create(
            model=settings.groq_agent_model,
            messages=[{"role": "user", "content": "ok"}],
            max_tokens=1,
        )
        runtime_model_state["preflight_ok"] = True
        log.info("Model preflight OK: %s", settings.groq_agent_model)
    except Exception as e:
        msg = str(e)
        if "model_decommissioned" in msg or "does not exist" in msg or "decommissioned" in msg:
            banner = (f"Requested {settings.groq_agent_model} — decommissioned/unavailable on Groq. "
                      f"Routed to {FALLBACK_MODEL}.")
            log.warning("%s (Groq: %s)", banner, msg[:200])
            settings.groq_agent_model = FALLBACK_MODEL
            runtime_model_state["active_agent_model"] = FALLBACK_MODEL
            runtime_model_state["banner"] = banner
            runtime_model_state["preflight_ok"] = False
        else:
            runtime_model_state["preflight_ok"] = False
            runtime_model_state["banner"] = f"Model preflight warning: {msg[:120]}"
            log.warning("Model preflight non-fatal error: %s", msg[:200])
    return runtime_model_state

def model_info() -> dict:
    return {**MODEL_STORY, **runtime_model_state}
