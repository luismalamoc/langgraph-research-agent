"""Nodos del StateGraph — cada función recibe state y retorna un dict parcial."""

import json
import re

from langchain_core.messages import HumanMessage

from app.agent.llm import LLMNodeError, get_llm as _get_llm, llm_invocation_error_message
from app.agent.prompts import (
    evaluator_prompt,
    planner_prompt,
    researcher_prompt,
    writer_prompt,
)
from app.agent.state import AgentState

MAX_ITERATIONS_PER_SUBTOPIC = 3


def _invoke_llm(prompt: str) -> str:
    try:
        llm = _get_llm()
        response = llm.invoke([HumanMessage(content=prompt)])
        return (response.content or "").strip()
    except Exception as exc:
        raise LLMNodeError(llm_invocation_error_message()) from exc


def _parse_subtopics(raw: str) -> list[str]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
            return parsed[:5]
    except json.JSONDecodeError:
        pass
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, list):
                return [str(x) for x in parsed[:5]]
        except json.JSONDecodeError:
            pass
    lines = [ln.strip("- *\"\t ") for ln in raw.splitlines() if ln.strip()]
    return [ln for ln in lines if ln][:5] or ["Overview", "Key concepts", "Applications"]


def planner(state: AgentState) -> dict:
    """Nodo planner — demuestra un nodo que transforma el estado global."""
    try:
        raw = _invoke_llm(planner_prompt(state["topic"]))
        subtopics = _parse_subtopics(raw)
        return {
            "subtopics": subtopics,
            "current_subtopic_idx": 0,
            "iteration_count": 0,
        }
    except LLMNodeError:
        raise
    except Exception as exc:
        raise LLMNodeError(f"Error en planner: {exc}") from exc


def researcher(state: AgentState) -> dict:
    """Nodo researcher — puede ejecutarse varias veces (loop vía edge condicional)."""
    try:
        subtopics = state.get("subtopics") or []
        if not subtopics:
            return {}

        idx = state["current_subtopic_idx"]
        subtopic = subtopics[idx]
        results = list(state.get("research_results") or [])

        is_retry = (
            results
            and results[-1].get("subtopic") == subtopic
            and not results[-1].get("approved", False)
        )

        content = _invoke_llm(researcher_prompt(state["topic"], subtopic))
        entry = {"subtopic": subtopic, "content": content, "approved": False}

        if is_retry:
            results[-1] = entry
            iteration = state.get("iteration_count", 0) + 1
        else:
            results.append(entry)
            iteration = 1

        return {"research_results": results, "iteration_count": iteration}
    except LLMNodeError:
        raise
    except Exception as exc:
        raise LLMNodeError(f"Error en researcher: {exc}") from exc


def evaluator(state: AgentState) -> dict:
    """Nodo evaluator — prepara la decisión del edge condicional siguiente."""
    try:
        subtopics = state.get("subtopics") or []
        results = list(state.get("research_results") or [])
        if not results or not subtopics:
            return {}

        idx = state["current_subtopic_idx"]
        last = dict(results[-1])
        verdict = _invoke_llm(
            evaluator_prompt(state["topic"], last["subtopic"], last["content"])
        ).upper()
        sufficient = "SUFFICIENT" in verdict and "INSUFFICIENT" not in verdict
        last["approved"] = sufficient
        results[-1] = last

        updates: dict = {"research_results": results}

        if sufficient:
            if idx < len(subtopics) - 1:
                updates["current_subtopic_idx"] = idx + 1
                updates["iteration_count"] = 0
        else:
            if state.get("iteration_count", 0) >= MAX_ITERATIONS_PER_SUBTOPIC:
                last["approved"] = True
                results[-1] = last
                updates["research_results"] = results
                if idx < len(subtopics) - 1:
                    updates["current_subtopic_idx"] = idx + 1
                    updates["iteration_count"] = 0

        return updates
    except LLMNodeError:
        raise
    except Exception as exc:
        raise LLMNodeError(f"Error en evaluator: {exc}") from exc


def writer(state: AgentState) -> dict:
    """Nodo writer — consolida resultados en markdown antes del interrupt humano."""
    try:
        results = state.get("research_results") or []
        if not results:
            return {"final_report": "# Report\n\nNo research results available."}

        report = _invoke_llm(writer_prompt(state["topic"], results))
        return {"final_report": report}
    except LLMNodeError:
        raise
    except Exception as exc:
        raise LLMNodeError(f"Error en writer: {exc}") from exc


def human_review(state: AgentState) -> dict:
    """
    Nodo human_review — se ejecuta tras resume.
    interrupt_before pausa el grafo ANTES de este nodo para revisión humana.
    """
    if not state.get("human_approved"):
        return {}
    return {}
