"""Manager plus specialist workflow for contract questions."""

from __future__ import annotations

from time import monotonic
from typing import Any

from agent_loops import (
    AgentState,
    CONTRACT_VERSIONS,
    LoopBudget,
    draft_grounded_answer,
    get_definitions,
    question_defined_terms,
    retrieve_contract_evidence,
)
from hybrid_retrieval import get_filename


def agent_card() -> dict[str, Any]:
    return {
        "name": "contract-squad-orchestrator",
        "description": "Manager delegating contract retrieval and defined-term resolution.",
        "skills": [
            "contract_clause_retrieval",
            "defined_term_lookup",
            "grounded_contract_answer",
        ],
        "input_modes": ["text/plain", "application/json"],
        "output_modes": ["text/plain", "application/json"],
        "authentication": {"schemes": ["none"], "note": "local evaluation workflow"},
        "specialists": ["clause-worker", "defined-terms-worker"],
    }


def run_orchestrator(
    question: str,
    budget: LoopBudget | None = None,
    *,
    inject_defined_terms_failure: bool = False,
) -> dict[str, Any]:
    started = monotonic()
    state = AgentState(question=question, budget=budget or LoopBudget())
    handoffs: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    def handoff(
        sender: str,
        receiver: str,
        *,
        status: str = "ok",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        handoffs.append(
            {
                "sender": sender,
                "receiver": receiver,
                "status": status,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "tokens": prompt_tokens + completion_tokens,
            }
        )

    handoff("orchestrator", "clause-worker")
    retrieval = retrieve_contract_evidence(question, state)
    if retrieval.get("security_blocked"):
        return _result(state, events, handoffs, "security_blocked", started)

    top = state.results[0] if state.results else None
    source = get_filename(top["document"]["metadata"].get("source")) if top else ""
    version = source[:-4] if source.endswith(".pdf") else source
    handoff("clause-worker", "orchestrator")
    failed = False
    for term in question_defined_terms(question)[:2]:
        payload = {"term": term, "contract_version": version}
        if inject_defined_terms_failure and not failed:
            failed = True
            handoff(
                "orchestrator",
                "defined-terms-worker",
                status="500 injected",
            )
            state.memory.append(f"defined-terms-worker returned HTTP 500 for '{term}'")
            events.append(
                {
                    "phase": "failure",
                    "message": "defined-terms-worker returned HTTP 500",
                    "term": term,
                }
            )
            continue
        if version in CONTRACT_VERSIONS:
            handoff("orchestrator", "defined-terms-worker")
            observation = get_definitions(term, version, state)
            handoff("defined-terms-worker", "orchestrator")
            if observation.get("security_blocked"):
                return _result(state, events, handoffs, "security_blocked", started)

    handoff("orchestrator", "answer-worker")
    draft = draft_grounded_answer(question, state)
    handoff(
        "answer-worker",
        "orchestrator",
        prompt_tokens=draft.get("prompt_tokens", 0),
        completion_tokens=draft.get("completion_tokens", 0),
    )
    return _result(
        state,
        events,
        handoffs,
        "degraded_partial_answer" if failed else "answer_ready",
        started,
    )


def _result(
    state: AgentState,
    events: list[dict[str, Any]],
    handoffs: list[dict[str, Any]],
    reason: str,
    started: float,
) -> dict[str, Any]:
    total = state.total_tokens
    return {
        "answer": state.answer,
        "sources": state.sources,
        "events": events + state.events,
        "handoffs": handoffs,
        "steps": len(events),
        "tool_calls": state.tool_calls,
        "total_tokens": total,
        "estimated_cost": round(total / 1000 * state.budget.cost_per_1k_tokens, 6),
        "elapsed_seconds": round(monotonic() - started, 4),
        "stop_reason": reason,
    }
