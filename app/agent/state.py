"""Estado compartido del agente — TypedDict que define el schema del StateGraph."""

from typing import TypedDict


class AgentState(TypedDict):
    """Schema del grafo: cada nodo lee/escribe solo los campos que necesita."""

    topic: str
    subtopics: list[str]
    current_subtopic_idx: int
    research_results: list[dict]
    final_report: str
    human_approved: bool
    iteration_count: int


def initial_state(topic: str) -> AgentState:
    """Estado inicial para POST /run."""
    return {
        "topic": topic,
        "subtopics": [],
        "current_subtopic_idx": 0,
        "research_results": [],
        "final_report": "",
        "human_approved": False,
        "iteration_count": 0,
    }
