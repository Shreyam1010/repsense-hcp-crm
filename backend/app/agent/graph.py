"""The LangGraph agent. create_agent (NOT langgraph.prebuilt.create_react_agent, which is
deprecated in v1). Compiles to a normal CompiledStateGraph with nodes 'model' and 'tools':

    START -> model -->|tool_calls?| tools -> model
                  -->|no tool_calls| END

Compliance lives in the tool contracts and DB constraints, not in the graph topology —
which is why create_agent suffices and a hand-rolled StateGraph is unnecessary."""
from langchain.agents import create_agent

from .llm import agent_llm
from .tools import ALL_TOOLS
from .middleware import FormMiddleware
from .prompt import SYSTEM_PROMPT
from .state import FormState

def build_agent(checkpointer=None):
    return create_agent(
        model=agent_llm(),
        tools=ALL_TOOLS,
        system_prompt=SYSTEM_PROMPT,
        middleware=[FormMiddleware()],
        state_schema=FormState,
        checkpointer=checkpointer,
    )
