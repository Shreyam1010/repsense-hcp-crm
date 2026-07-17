"""Proof, not assertion: the required model returns an error.

Run:
    cd backend && .venv/bin/python scripts/prove_gemma_dead.py

It calls Groq with `gemma2-9b-it` and prints the live error. Requires GROQ_API_KEY
in ../.env (any valid key — the point is Groq's response, not a successful call).

Captured output (2026-07-15), pasted verbatim into README § Model mandate:

    groq.NotFoundError: Error code: 404 - {'error': {'message': 'The model
      `gemma2-9b-it` has been decommissioned and is no longer supported. Please refer
      to https://console.groq.com/docs/deprecations for a recommendation on which
      model to use instead.', 'type': 'invalid_request_error',
      'code': 'model_decommissioned'}}
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from groq import Groq

from app.config import settings

SPEC_MODEL = "gemma2-9b-it"

def main() -> int:
    if not settings.groq_key_looks_real:
        print("GROQ_API_KEY not set in .env — put a real key there first "
              "(the call needs to authenticate to reach the model check).")
        return 2

    client = Groq(api_key=settings.groq_api_key)
    print(f"Calling Groq with the required model: {SPEC_MODEL!r}\n")
    try:
        client.chat.completions.create(
            model=SPEC_MODEL,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
        )
        print("!! Unexpected: the call SUCCEEDED. Re-check Groq's deprecations page.")
        return 1
    except Exception as e:
        print(f"{type(e).__module__}.{type(e).__name__}: {e}")
        code = getattr(getattr(e, "body", None), "get", lambda *_: None)("code") \
            if hasattr(e, "body") else None
        if "model_decommissioned" in str(e) or code == "model_decommissioned":
            print("\n✓ Confirmed: the required model is decommissioned.")
            return 0
        print("\n(Model returned a different error — see above.)")
        return 0

if __name__ == "__main__":
    raise SystemExit(main())
