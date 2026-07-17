"""ChatGroq factories. Two models, two token buckets:
  - agent model (gpt-oss-120b): the tool-calling ReAct loop
  - extract model (gpt-oss-20b): constrained decoding for structured outputs / fallback

Structured Outputs cannot be combined with tool use or streaming on Groq, so the
structured calls here are deliberately separate, non-tool-bound, non-streamed."""
from langchain_groq import ChatGroq

from ..config import settings

def agent_llm() -> ChatGroq:
    return ChatGroq(
        model=settings.groq_agent_model,
        api_key=settings.groq_api_key,
        temperature=0,
        max_retries=5,
        max_tokens=1024,

    )

def extract_llm() -> ChatGroq:
    return ChatGroq(
        model=settings.groq_extract_model,
        api_key=settings.groq_api_key,
        temperature=0,
        max_retries=5,
    )
