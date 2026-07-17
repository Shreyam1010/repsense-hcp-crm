"""Registers the custom state schema with create_agent.

runtime.state fails SILENTLY otherwise: it returns only what the graph's declared schema
contains, and create_agent's default schema is messages-only — so without this the tools'
`form`/`rep_id`/`territory_id` come back absent, with no error. The bug that looks like a
model problem and costs an hour."""
from langchain.agents.middleware import AgentMiddleware

from .state import FormState

class FormMiddleware(AgentMiddleware):
    state_schema = FormState
