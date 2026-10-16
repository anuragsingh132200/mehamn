"""LLM-only semantic interpretation and tool planning. No runtime keyword parser."""
from .agent_schemas import AgentDecision
from .context import build_context
from .model_gateway import ModelGateway, ModelUnavailable, ModelOutputInvalid
from .prompts import PLANNER_PROMPT

def extract(message,state,history=(),gateway=None,tool_results=(),round_number=0):
    gateway=gateway or ModelGateway()
    context=build_context(message,state,history,tool_results,round_number)
    return gateway.parse(AgentDecision,context,PLANNER_PROMPT,"plan")
