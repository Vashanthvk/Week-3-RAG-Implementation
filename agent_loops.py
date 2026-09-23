"""Hand-built legal-contract agent loop with security boundary checks.

The loop intentionally exposes each decision and tool call. Security checks
are applied to input, tool usage, retrieved contract data, and final output.
"""

from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Callable

from security_controls import (
    REFUSAL_MESSAGE,
    security_gate,
    validate_retrieval_results,
    wrap_untrusted_context,
)

from rag import (
    bm25,
    build_context,
    documents,
    generate_answer,
    retrieve_with_retry,
    should_refuse_answer,
    vector_store,
)


TOOL_DESCRIPTIONS = {
    "retrieve_contract_evidence": "Retrieve and rank contract chunks for a legal question.",
    "draft_grounded_answer": "Draft an answer using only the retrieved contract evidence.",
}


@dataclass
class LoopBudget:
    max_steps: int = 6
    max_seconds: float = 30.0
    max_cost: float = 0.01
    cost_per_tool_call: float = 0.001


@dataclass
class AgentState:
    question: str
    budget: LoopBudget
    step: int = 0
    tool_calls: int = 0
    estimated_cost: float = 0.0
    started_at: float = field(default_factory=monotonic)
    events: list[dict[str, Any]] = field(default_factory=list)
    memory: list[str] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
    answer: str = ""
    sources: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str = ""


def _record(state: AgentState, phase: str, message: str, **data: Any) -> None:
    event = {"step": state.step, "phase": phase, "message": message}
    event.update(data)
    state.events.append(event)
    print(f"[agent step {state.step}] {phase}: {message}")


def _budget_exceeded(state: AgentState, budget: LoopBudget) -> str | None:
    if state.step >= budget.max_steps:
        return "max_steps"
    if monotonic() - state.started_at >= budget.max_seconds:
        return "max_seconds"
    if state.estimated_cost + budget.cost_per_tool_call > budget.max_cost:
        return "max_cost"
    return None


def retrieve_contract_evidence(question: str, state: AgentState) -> dict[str, Any]:
    """Tool 1: retrieve evidence and expose relevance for the next decision."""

    state.tool_calls += 1
    state.estimated_cost += state.budget.cost_per_tool_call
    retrieval = retrieve_with_retry(vector_store, documents, bm25, question)
    results = retrieval["results"]

    # Security boundary: retrieval output is untrusted contract data.
    security = security_gate(
        tool_name="retrieve_contract_evidence",
        retrieval_results=results,
    )
    if not security.allowed:
        state.answer = REFUSAL_MESSAGE
        state.stop_reason = "security_blocked"
        state.memory.append(f"security block: {security.reason}")
        _record(
            state,
            "SECURITY",
            f"Blocked retrieval output: {security.reason}.",
            reason=security.reason,
        )
        return {
            "results": results,
            "best_score": 0.0,
            "attempt": retrieval["attempt"],
            "security_blocked": True,
            "security_reason": security.reason,
        }

    retrieved_text = "\n\n".join(
        item["document"]["content"]
        for item in results
        if isinstance(item, dict)
        and isinstance(item.get("document"), dict)
        and isinstance(item["document"].get("content"), str)
    )
    content_security = security_gate(retrieved_text=retrieved_text)
    if not content_security.allowed:
        state.answer = REFUSAL_MESSAGE
        state.stop_reason = "security_blocked"
        state.memory.append(f"security block: {content_security.reason}")
        _record(
            state,
            "SECURITY",
            f"Blocked untrusted contract content: {content_security.reason}.",
            reason=content_security.reason,
        )
        return {
            "results": results,
            "best_score": 0.0,
            "attempt": retrieval["attempt"],
            "security_blocked": True,
            "security_reason": content_security.reason,
        }

    best_score = max((item.get("keyword_score", 0.0) for item in results), default=0.0)
    state.results = results
    state.memory.append(f"retrieval attempt={retrieval['attempt']} best_score={best_score:.2f}")
    return {
        "results": results,
        "best_score": best_score,
        "attempt": retrieval["attempt"],
        "security_blocked": False,
    }


def draft_grounded_answer(question: str, state: AgentState) -> dict[str, Any]:
    """Tool 2: draft only after evidence has been retrieved."""

    state.tool_calls += 1
    state.estimated_cost += state.budget.cost_per_tool_call

    tool_security = security_gate(tool_name="draft_grounded_answer")
    if not tool_security.allowed:
        state.answer = REFUSAL_MESSAGE
        state.stop_reason = "security_blocked"
        state.memory.append(f"security block: {tool_security.reason}")
        _record(
            state,
            "SECURITY",
            f"Blocked draft tool: {tool_security.reason}.",
            reason=tool_security.reason,
        )
        return {"answer": state.answer, "sources": [], "security_blocked": True}

    if should_refuse_answer(question, state.results):
        state.answer = REFUSAL_MESSAGE
    else:
        context = build_context(state.results)
        # Explicitly mark retrieved contract text as untrusted data.
        context = wrap_untrusted_context(context)
        state.answer = generate_answer(question, context)

    state.sources = _format_sources(state.results)

    output_security = security_gate(
        answer=state.answer,
        sources=state.sources,
    )
    if not output_security.allowed:
        state.answer = REFUSAL_MESSAGE
        state.stop_reason = "security_blocked"
        state.memory.append(f"security block: {output_security.reason}")
        _record(
            state,
            "SECURITY",
            f"Blocked generated output: {output_security.reason}.",
            reason=output_security.reason,
        )
        return {
            "answer": state.answer,
            "sources": state.sources,
            "security_blocked": True,
            "security_reason": output_security.reason,
        }

    state.memory.append(f"drafted answer from {len(state.results)} chunks")
    return {
        "answer": state.answer,
        "sources": state.sources,
        "security_blocked": False,
    }


def _format_sources(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources = []
    seen = set()
    for result in results:
        metadata = result["document"]["metadata"]
        source = metadata.get("source", "Unknown")
        page = metadata.get("page_label", metadata.get("page", 1))
        key = (source, str(page))
        if key not in seen:
            seen.add(key)
            sources.append({"source": source, "page": page})
    return sources


def run_agent(question: str, budget: LoopBudget | None = None) -> dict[str, Any]:
    """Run PLAN -> ACT -> OBSERVE until the evidence is adequate or budget ends."""

    budget = budget or LoopBudget()
    state = AgentState(question=question, budget=budget)

    # Security boundary: the user question is also untrusted input.
    question_security = security_gate(retrieved_text=question)
    if not question_security.allowed:
        state.answer = REFUSAL_MESSAGE
        state.stop_reason = "security_blocked"
        state.memory.append(f"security block: {question_security.reason}")
        _record(
            state,
            "SECURITY",
            f"Blocked question: {question_security.reason}.",
            reason=question_security.reason,
        )
        return {
            "answer": state.answer,
            "sources": [],
            "events": state.events,
            "memory": state.memory,
            "steps": state.step,
            "tool_calls": state.tool_calls,
            "estimated_cost": round(state.estimated_cost, 4),
            "elapsed_seconds": round(monotonic() - state.started_at, 4),
            "stop_reason": state.stop_reason,
        }

    _record(state, "PLAN", "Choose retrieval before drafting.")
    retrieval_retries = 0

    while not state.answer:
        state.step += 1
        reason = _budget_exceeded(state, budget)
        if reason:
            state.stop_reason = reason
            _record(state, "STOP", f"Budget reached: {reason}.")
            break

        _record(state, "ACT", "Call retrieve_contract_evidence.", tool="retrieve_contract_evidence",argument=question)
        observation = retrieve_contract_evidence(question, state)
        _record(
            state,
            "OBSERVE",
            f"Retrieved evidence with best score {observation['best_score']:.2f}.",
            attempt=observation["attempt"],
        )

        if observation.get("security_blocked"):
            break

        if (
            observation["best_score"] < 0.25
            and retrieval_retries < 1
            and state.step < budget.max_steps
        ):
            retrieval_retries += 1
            state.memory.append("weak evidence; retry retrieval before answering")
            _record(
                state,
                "PLAN",
                "Evidence is weak; retry retrieval.",
                retry=retrieval_retries,
            )
            continue

        if observation["best_score"] < 0.25:
            state.answer = REFUSAL_MESSAGE
            state.stop_reason = "answer_ready"
            state.sources = _format_sources(state.results)
            _record(
                state,
                "OBSERVE",
                "Evidence remained weak after the bounded retry; refusing.",
            )
            break

        reason = _budget_exceeded(state, budget)
        if reason:
            state.stop_reason = reason
            _record(state, "STOP", f"Budget reached: {reason}.")
            break

        _record(state, "ACT", "Call draft_grounded_answer.", tool="draft_grounded_answer")
        draft_grounded_answer(question, state)
        _record(state, "OBSERVE", "Answer drafted from retrieved evidence.")
        state.stop_reason = "answer_ready"

    return {
        "answer": state.answer,
        "sources": state.sources,
        "events": state.events,
        "memory": state.memory,
        "steps": state.step,
        "tool_calls": state.tool_calls,
        "estimated_cost": round(state.estimated_cost, 4),
        "elapsed_seconds": round(monotonic() - state.started_at, 4),
        "stop_reason": state.stop_reason or "budget_exhausted",
    }


def run_fixed_workflow(question: str) -> dict[str, Any]:
    """Run the known fixed sequence: retrieve once, then draft once."""

    started_at = monotonic()

    question_security = security_gate(retrieved_text=question)
    if not question_security.allowed:
        return {
            "answer": REFUSAL_MESSAGE,
            "sources": [],
            "steps": 0,
            "tool_calls": 0,
            "estimated_cost": 0.0,
            "elapsed_seconds": round(monotonic() - started_at, 4),
            "stop_reason": "security_blocked",
        }

    retrieval = retrieve_with_retry(vector_store, documents, bm25, question)
    results = retrieval["results"]

    retrieval_security = security_gate(
        tool_name="retrieve_contract_evidence",
        retrieval_results=results,
    )
    retrieved_text = "\n\n".join(
        item["document"]["content"]
        for item in results
        if isinstance(item, dict)
        and isinstance(item.get("document"), dict)
        and isinstance(item["document"].get("content"), str)
    )
    content_security = security_gate(retrieved_text=retrieved_text)

    if not retrieval_security.allowed or not content_security.allowed:
        answer = REFUSAL_MESSAGE
        stop_reason = "security_blocked"
    elif should_refuse_answer(question, results):
        answer = REFUSAL_MESSAGE
        stop_reason = "answer_ready"
    else:
        answer = generate_answer(
            question,
            wrap_untrusted_context(build_context(results)),
        )
        output_security = security_gate(
            answer=answer,
            sources=_format_sources(results),
        )
        if not output_security.allowed:
            answer = REFUSAL_MESSAGE
            stop_reason = "security_blocked"
        else:
            stop_reason = "answer_ready"

    return {
        "answer": answer,
        "sources": _format_sources(results),
        "steps": 2,
        "tool_calls": 2,
        "estimated_cost": 0.002,
        "elapsed_seconds": round(monotonic() - started_at, 4),
        "stop_reason": stop_reason,
    }


def compare_workflows(
    questions: list[dict[str, Any]],
    agent_runner: Callable[[str], dict[str, Any]] = run_agent,
    fixed_runner: Callable[[str], dict[str, Any]] = run_fixed_workflow,
) -> dict[str, Any]:
    """Compare both workflows using the Week 7 question set and simple checks."""

    from eval import evaluate_question

    rows = []
    for item in questions:
        question = item["question"]
        agent = agent_runner(question)
        fixed = fixed_runner(question)
        rows.append({
            "id": item["id"],
            "agent": agent,
            "fixed": fixed,
            "agent_answered": bool(agent["answer"].strip()),
            "fixed_answered": bool(fixed["answer"].strip()),
            "agent_correct": evaluate_question(question, agent["answer"], agent["sources"]),
            "fixed_correct": evaluate_question(question, fixed["answer"], fixed["sources"]),
        })

    return {
        "question_count": len(rows),
        "agent": {
            "answered": sum(row["agent_answered"] for row in rows),
            "correct": sum(row["agent_correct"] for row in rows),
            "reliability": round(sum(row["agent_correct"] for row in rows) / len(rows), 4) if rows else 0,
            "average_steps": round(sum(row["agent"]["steps"] for row in rows) / len(rows), 2) if rows else 0,
            "estimated_cost": round(sum(row["agent"]["estimated_cost"] for row in rows), 4),
        },
        "fixed_workflow": {
            "answered": sum(row["fixed_answered"] for row in rows),
            "correct": sum(row["fixed_correct"] for row in rows),
            "reliability": round(sum(row["fixed_correct"] for row in rows) / len(rows), 4) if rows else 0,
            "average_steps": round(sum(row["fixed"]["steps"] for row in rows) / len(rows), 2) if rows else 0,
            "estimated_cost": round(sum(row["fixed"]["estimated_cost"] for row in rows), 4),
        },
        "rows": rows,
    }
