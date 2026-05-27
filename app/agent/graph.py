"""StateGraph — define nodos, edges, checkpointer e interrupt_before."""

from typing import Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

# LLM vía app.agent.providers (LLM_PROVIDER)
from app.agent.providers import get_llm  # noqa: F401

from app.agent.nodes import (
    evaluator,
    human_review,
    planner,
    researcher,
    writer,
)
from app.agent.state import AgentState

_compiled_graph = None


def _all_subtopics_approved(state: AgentState) -> bool:
    subtopics = state.get("subtopics") or []
    results = state.get("research_results") or []
    if not subtopics:
        return False
    for subtopic in subtopics:
        if not any(
            r.get("subtopic") == subtopic and r.get("approved") for r in results
        ):
            return False
    return True


def route_after_evaluator(state: AgentState) -> Literal["researcher", "writer"]:
    """
    Edge condicional — decide si re-investigar o pasar al reporte final.
    Demuestra add_conditional_edges: el destino depende del estado, no es fijo.
    """
    if _all_subtopics_approved(state):
        return "writer"

    results = state.get("research_results") or []
    if results and not results[-1].get("approved"):
        if state.get("iteration_count", 0) < 3:
            return "researcher"

    return "researcher"


def build_graph():
    """Construye y compila el StateGraph con MemorySaver e interrupt humano."""
    builder = StateGraph(AgentState)

    # Nodos: cada uno es una función (state) -> dict parcial
    builder.add_node("planner", planner)
    builder.add_node("researcher", researcher)
    builder.add_node("evaluator", evaluator)
    builder.add_node("writer", writer)
    builder.add_node("human_review", human_review)

    # Edges normales: flujo fijo entre nodos
    builder.add_edge(START, "planner")
    builder.add_edge("planner", "researcher")
    builder.add_edge("researcher", "evaluator")

    # Edge condicional: loop researcher <-> evaluator hasta cubrir subtemas
    builder.add_conditional_edges(
        "evaluator",
        route_after_evaluator,
        {"researcher": "researcher", "writer": "writer"},
    )

    builder.add_edge("writer", "human_review")
    builder.add_edge("human_review", END)

    # MemorySaver: persiste checkpoints en RAM keyed por thread_id
    checkpointer = MemorySaver()

    # interrupt_before: pausa ANTES de human_review (human-in-the-loop)
    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_review"],
    )


def get_graph():
    """Singleton del grafo compilado para FastAPI."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph
