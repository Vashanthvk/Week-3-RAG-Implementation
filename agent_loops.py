# """
# Week 7 - Hand-built Agent Loop
# Legal Contract RAG

# This module sits on top of the existing Week 6 retrieval/RAG code.

# Actual project interfaces:
# - hybrid_retrieval.retrieve_with_retry(vector_store, documents, bm25, question)
# - retrieval result: {"results": [{"document": {...}, ...}], ...}
# - rag.build_context(results) in the local runtime expects objects exposing
#   .metadata and .page_content
# - rag.llm provides the initialized LLM instance
# - rag.generate_answer(question, context) generates the answer

# The agent exposes:
#     PLAN -> ACT -> OBSERVE -> PLAN/ACT -> OBSERVE
# with step, time, and cost budgets plus short-term memory.
# """

# from __future__ import annotations

# from dataclasses import dataclass, field
# from time import monotonic
# from typing import Any, Callable

# from hybrid_retrieval import (
#     create_bm25,
#     load_all_documents,
#     load_vector_store,
#     retrieve_with_retry,
# )

# from rag import (
#     build_context,
#     llm as _rag_llm,
#     generate_answer as _rag_generate_answer,
# )


# print("\n" + "=" * 70)
# print("LOADING WEEK 7 AGENT LOOP")
# print("=" * 70)

# print("\nLoading ChromaDB...")
# vector_store = load_vector_store()

# print("Loading document chunks...")
# documents = load_all_documents(vector_store)
# print(f"Loaded {len(documents)} chunks.")

# print("Creating BM25 index...")
# bm25 = create_bm25(documents)
# print("BM25 index ready.")


# TOOL_DESCRIPTIONS = {
#     "retrieve_contract_evidence": (
#         "Retrieve and rank contract evidence using the existing hybrid "
#         "semantic + BM25 + RRF retrieval pipeline."
#     ),
#     "draft_grounded_answer": (
#         "Build context from retrieved documents and generate a grounded "
#         "contract answer."
#     ),
# }

# REFUSAL_MESSAGE = "I don't know based on the provided contracts."
# RELEVANCE_THRESHOLD = 0.25


# # ---------------------------------------------------------------------------
# # LLM compatibility wrapper
# # ---------------------------------------------------------------------------

# def generate_answer(
#     question: str,
#     context: str,
# ) -> str:
#     """
#     Week 7-facing answer function.

#     Tests patch agent_loops.generate_answer(question, context), while the
#     actual Week 6 rag.py requires generate_answer(llm, context, question).
#     This wrapper keeps both interfaces compatible.
#     """

#     # The current Week 6 rag.py already owns the initialized module-level
#     # OllamaLLM instance as `rag.llm` and exposes generate_answer(question,
#     # context). Reuse that interface instead of requiring a nonexistent
#     # rag.create_llm() factory.
#     return _rag_generate_answer(
#         question,
#         context,
#     )


# # ---------------------------------------------------------------------------
# # Retrieval -> context adapter
# # ---------------------------------------------------------------------------

# def _get_context_documents(
#     results: list[Any],
# ) -> list[Any]:
#     """
#     Extract result["document"] and expose the attributes required by the
#     local rag.build_context():

#         document.metadata
#         document.page_content

#     The hybrid retrieval layer stores documents as dictionaries containing:
#         {"content": "...", "metadata": {...}}
#     """

#     class ContextDocument:
#         def __init__(self, data: dict[str, Any]):
#             self.metadata = data.get("metadata", {})
#             self.page_content = data.get(
#                 "page_content",
#                 data.get("content", data.get("text", "")),
#             )

#     context_documents = []

#     for item in results:
#         if hasattr(item, "metadata") and hasattr(
#             item,
#             "page_content",
#         ):
#             context_documents.append(item)
#             continue

#         if not isinstance(item, dict):
#             continue

#         document = item.get("document")

#         if document is None:
#             document = item

#         if hasattr(document, "metadata") and hasattr(
#             document,
#             "page_content",
#         ):
#             context_documents.append(document)
#         elif isinstance(document, dict):
#             context_documents.append(
#                 ContextDocument(document)
#             )

#     return context_documents


# # ---------------------------------------------------------------------------
# # Relevance / source helpers
# # ---------------------------------------------------------------------------

# def _result_score(result: dict[str, Any]) -> float:
#     """
#     Prefer the relevance score produced by hybrid_retrieval.py.

#     Tests use keyword_score. The real pipeline also populates keyword_score
#     during reranking.
#     """

#     for key in (
#         "keyword_score",
#         "relevance_score",
#         "score",
#     ):
#         value = result.get(key)

#         if isinstance(value, (int, float)):
#             return float(value)

#     return 0.0


# def _best_score(results: list[Any]) -> float:
#     scores = [
#         _result_score(item)
#         for item in results
#         if isinstance(item, dict)
#     ]

#     return max(scores, default=0.0)


# def should_refuse_answer(
#     question: str,
#     results: list[Any],
# ) -> bool:
#     """
#     Refuse when retrieval provides no sufficiently relevant evidence.

#     This function remains independently patchable by the Week 7 tests.
#     """

#     if not results:
#         return True

#     scores = [
#         _result_score(item)
#         for item in results
#         if isinstance(item, dict)
#         and any(
#             isinstance(item.get(key), (int, float))
#             for key in (
#                 "keyword_score",
#                 "relevance_score",
#                 "score",
#             )
#         )
#     ]

#     if not scores:
#         # Retrieval may return a usable document without a score in a mocked
#         # or alternate implementation. Let the existing retrieval layer's
#         # selection stand.
#         return False

#     return max(scores) < RELEVANCE_THRESHOLD


# def _format_sources(
#     results: list[Any],
# ) -> list[dict[str, Any]]:
#     """
#     Return the same normalized source representation used by the project:
#         [{"source": "...", "page": ...}, ...]
#     """

#     sources: list[dict[str, Any]] = []
#     seen: set[tuple[str, str]] = set()

#     for result in results:
#         if not isinstance(result, dict):
#             continue

#         document = result.get("document", result)

#         if isinstance(document, dict):
#             metadata = document.get("metadata", {})
#         else:
#             metadata = getattr(document, "metadata", {})

#         source = metadata.get(
#             "source",
#             "Unknown",
#         )

#         # Match the project's source representation closely.
#         source = str(source).replace("\\", "/").split("/")[-1]

#         page_label = metadata.get("page_label")

#         if page_label is not None:
#             page = page_label
#         else:
#             page = metadata.get("page")

#             if page is None:
#                 page = 1
#             else:
#                 try:
#                     page = int(page) + 1
#                 except (TypeError, ValueError):
#                     pass

#         key = (source, str(page))

#         if key in seen:
#             continue

#         seen.add(key)

#         sources.append(
#             {
#                 "source": source,
#                 "page": page,
#             }
#         )

#     return sources


# # ---------------------------------------------------------------------------
# # Budget / state
# # ---------------------------------------------------------------------------

# @dataclass
# class LoopBudget:
#     max_steps: int = 6
#     max_seconds: float = 30.0
#     max_cost: float = 0.01
#     cost_per_tool_call: float = 0.001


# @dataclass
# class AgentState:
#     question: str
#     budget: LoopBudget

#     step: int = 0
#     tool_calls: int = 0
#     estimated_cost: float = 0.0
#     started_at: float = field(default_factory=monotonic)

#     events: list[dict[str, Any]] = field(default_factory=list)
#     memory: list[str] = field(default_factory=list)

#     results: list[dict[str, Any]] = field(default_factory=list)
#     answer: str = ""
#     sources: list[dict[str, Any]] = field(default_factory=list)
#     stop_reason: str = ""


# def _record(
#     state: AgentState,
#     phase: str,
#     message: str,
#     **data: Any,
# ) -> None:
#     event = {
#         "step": state.step,
#         "phase": phase,
#         "message": message,
#     }

#     event.update(data)
#     state.events.append(event)

#     tool = data.get("tool")

#     if tool:
#         print(
#             f"[agent step {state.step}] "
#             f"{phase}: {message} [{tool}]"
#         )
#     else:
#         print(
#             f"[agent step {state.step}] "
#             f"{phase}: {message}"
#         )


# def _budget_exceeded(
#     state: AgentState,
#     budget: LoopBudget,
# ) -> str | None:
#     """
#     Check budget BEFORE starting the next tool call.

#     This is important: if max_cost is below one tool-call cost, the agent
#     must stop with zero tool calls.
#     """

#     if state.step >= budget.max_steps:
#         return "max_steps"

#     if monotonic() - state.started_at >= budget.max_seconds:
#         return "max_seconds"

#     if (
#         state.estimated_cost
#         + budget.cost_per_tool_call
#         > budget.max_cost
#     ):
#         return "max_cost"

#     return None


# # ---------------------------------------------------------------------------
# # Tool 1 - retrieval
# # ---------------------------------------------------------------------------

# def retrieve_contract_evidence(
#     question: str,
#     state: AgentState,
# ) -> dict[str, Any]:
#     """Retrieve evidence using the existing hybrid retrieval pipeline."""

#     state.tool_calls += 1
#     state.estimated_cost += state.budget.cost_per_tool_call

#     retrieval = retrieve_with_retry(
#         vector_store,
#         documents,
#         bm25,
#         question,
#     )

#     results = retrieval.get(
#         "results",
#         [],
#     )

#     state.results = results

#     best_score = _best_score(results)
#     attempt = retrieval.get(
#         "attempt",
#         1,
#     )

#     state.memory.append(
#         f"retrieval attempt={attempt} "
#         f"best_score={best_score:.2f}"
#     )

#     return {
#         "results": results,
#         "best_score": best_score,
#         "attempt": attempt,
#     }


# # ---------------------------------------------------------------------------
# # Tool 2 - grounded answer
# # ---------------------------------------------------------------------------

# def draft_grounded_answer(
#     question: str,
#     state: AgentState,
# ) -> dict[str, Any]:
#     """Draft only after retrieval has supplied evidence."""

#     state.tool_calls += 1
#     state.estimated_cost += state.budget.cost_per_tool_call

#     if should_refuse_answer(
#         question,
#         state.results,
#     ):
#         state.answer = REFUSAL_MESSAGE
#     else:
#         context_documents = _get_context_documents(
#             state.results
#         )

#         if not context_documents:
#             state.answer = REFUSAL_MESSAGE
#         else:
#             context = build_context(
#                 context_documents
#             )

#             # This wrapper is deliberately called with two arguments so the
#             # Week 7 unit tests can patch it. The wrapper then creates the
#             # actual LLM and calls rag.generate_answer() with its real
#             # three-argument signature.
#             state.answer = generate_answer(
#                 question,
#                 context,
#             )

#     state.sources = _format_sources(
#         state.results
#     )

#     state.memory.append(
#         f"drafted answer from "
#         f"{len(state.results)} chunks"
#     )

#     return {
#         "answer": state.answer,
#         "sources": state.sources,
#     }


# # ---------------------------------------------------------------------------
# # Agent loop
# # ---------------------------------------------------------------------------

# def run_agent(
#     question: str,
#     budget: LoopBudget | None = None,
# ) -> dict[str, Any]:
#     """
#     Run the hand-built PLAN -> ACT -> OBSERVE loop.

#     Decision policy:
#       1. PLAN to retrieve.
#       2. ACT: retrieve.
#       3. OBSERVE relevance.
#       4. Weak evidence -> PLAN retry.
#       5. Sufficient evidence -> ACT draft.
#       6. OBSERVE answer.
#       7. Stop with answer_ready.
#     """

#     budget = budget or LoopBudget()

#     state = AgentState(
#         question=question,
#         budget=budget,
#     )

#     _record(
#         state,
#         "PLAN",
#         "Choose retrieval before drafting.",
#     )

#     retrieval_round = 0

#     while not state.answer:
#         # Check budgets BEFORE incrementing the step and BEFORE calling a tool.
#         reason = _budget_exceeded(
#             state,
#             budget,
#         )

#         if reason:
#             state.stop_reason = reason

#             _record(
#                 state,
#                 "STOP",
#                 f"Budget reached: {reason}.",
#             )

#             break

#         state.step += 1
#         retrieval_round += 1

#         _record(
#             state,
#             "ACT",
#             "Call retrieve_contract_evidence.",
#             tool="retrieve_contract_evidence",
#         )

#         observation = retrieve_contract_evidence(
#             question,
#             state,
#         )

#         _record(
#             state,
#             "OBSERVE",
#             (
#                 "Retrieved evidence with "
#                 f"best score "
#                 f"{observation['best_score']:.2f}."
#             ),
#             attempt=observation["attempt"],
#         )

#         weak_evidence = (
#             observation["best_score"]
#             < RELEVANCE_THRESHOLD
#         )

#         # Unsupported / weak evidence should never be sent to the LLM.
#         if should_refuse_answer(
#             question,
#             state.results,
#         ):
#             if weak_evidence:
#                 # If this retrieval already consumed the final allowed step,
#                 # the explicit step budget takes precedence. This preserves
#                 # the contract tested by test_agent_stops_at_step_budget:
#                 # max_steps must be reported and no answer should be produced.
#                 if state.step >= budget.max_steps:
#                     state.stop_reason = "max_steps"

#                     _record(
#                         state,
#                         "STOP",
#                         "Budget reached: max_steps.",
#                     )

#                     break

#                 # Give the agent exactly one adaptive retry. Repeating the
#                 # same retrieval six times is not useful agent behavior.
#                 if retrieval_round == 1:
#                     state.memory.append(
#                         "weak evidence; one bounded retrieval retry allowed"
#                     )

#                     _record(
#                         state,
#                         "PLAN",
#                         "Evidence is weak; retry retrieval once.",
#                     )

#                     continue

#                 # After the bounded retry, fail closed rather than consuming
#                 # the entire step budget on identical evidence.
#                 state.answer = REFUSAL_MESSAGE
#                 state.sources = _format_sources(
#                     state.results
#                 )
#                 state.memory.append(
#                     "evidence remained weak after bounded retry; "
#                     "refusing unsupported answer"
#                 )
#                 state.stop_reason = "answer_ready"

#                 _record(
#                     state,
#                     "OBSERVE",
#                     "Evidence remains insufficient; refusing unsupported answer.",
#                 )

#                 break

#             # A mocked/refusal policy may explicitly reject an answer even
#             # when retrieval's numeric score is high. Finish safely.
#             state.answer = REFUSAL_MESSAGE
#             state.sources = _format_sources(
#                 state.results
#             )
#             state.memory.append(
#                 "grounding policy refused answer"
#             )
#             state.stop_reason = "answer_ready"

#             _record(
#                 state,
#                 "OBSERVE",
#                 "Grounding policy refused the answer.",
#             )

#             break

#         # Before the second tool call, check whether the budget permits it.
#         reason = _budget_exceeded(
#             state,
#             budget,
#         )

#         if reason:
#             state.stop_reason = reason

#             _record(
#                 state,
#                 "STOP",
#                 f"Budget reached: {reason}.",
#             )

#             break

#         _record(
#             state,
#             "ACT",
#             "Call draft_grounded_answer.",
#             tool="draft_grounded_answer",
#         )

#         draft_grounded_answer(
#             question,
#             state,
#         )

#         _record(
#             state,
#             "OBSERVE",
#             "Answer drafted from retrieved evidence.",
#         )

#         state.stop_reason = "answer_ready"

#     return {
#         "answer": state.answer,
#         "sources": state.sources,
#         "events": state.events,
#         "memory": state.memory,
#         "steps": state.step,
#         "tool_calls": state.tool_calls,
#         "estimated_cost": round(
#             state.estimated_cost,
#             4,
#         ),
#         "elapsed_seconds": round(
#             monotonic() - state.started_at,
#             4,
#         ),
#         "stop_reason": state.stop_reason,
#     }


# # ---------------------------------------------------------------------------
# # Fixed workflow baseline
# # ---------------------------------------------------------------------------

# def run_fixed_workflow(
#     question: str,
# ) -> dict[str, Any]:
#     """Run the deterministic retrieve-once -> context -> answer workflow."""

#     started_at = monotonic()

#     retrieval = retrieve_with_retry(
#         vector_store,
#         documents,
#         bm25,
#         question,
#     )

#     results = retrieval.get(
#         "results",
#         [],
#     )

#     if should_refuse_answer(
#         question,
#         results,
#     ):
#         answer = REFUSAL_MESSAGE
#     else:
#         context_documents = _get_context_documents(
#             results
#         )

#         if not context_documents:
#             answer = REFUSAL_MESSAGE
#         else:
#             context = build_context(
#                 context_documents
#             )

#             answer = generate_answer(
#                 question,
#                 context,
#             )

#     return {
#         "answer": answer,
#         "sources": _format_sources(results),
#         "steps": 2,
#         "tool_calls": 2,
#         "estimated_cost": 0.002,
#         "elapsed_seconds": round(
#             monotonic() - started_at,
#             4,
#         ),
#         "stop_reason": "answer_ready",
#     }


# # ---------------------------------------------------------------------------
# # Workflow comparison
# # ---------------------------------------------------------------------------

# def compare_workflows(
#     questions: list[dict[str, Any]],
#     agent_runner: Callable[
#         [str],
#         dict[str, Any],
#     ] = run_agent,
#     fixed_runner: Callable[
#         [str],
#         dict[str, Any],
#     ] = run_fixed_workflow,
# ) -> dict[str, Any]:
#     """
#     Compare agent and fixed workflows.

#     The return shape intentionally matches test_agent_loops.py:
#         question_count
#         agent.answered
#         agent.correct
#         agent.reliability
#         agent.average_steps
#         agent.estimated_cost
#         fixed_workflow.answered
#         ...
#         rows
#     """

#     try:
#         from eval import evaluate_question
#     except ImportError:
#         evaluate_question = None

#     rows = []

#     for index, item in enumerate(
#         questions,
#         start=1,
#     ):
#         question = item["question"]

#         print("\n" + "=" * 70)
#         print(f"QUESTION {index}")
#         print("=" * 70)
#         print(question)

#         print("\nAGENT LOOP")
#         agent = agent_runner(question)

#         print("\nFIXED WORKFLOW")
#         fixed = fixed_runner(question)

#         if evaluate_question is not None:
#             try:
#                 agent_correct = evaluate_question(
#                     question,
#                     agent.get("answer", ""),
#                     agent.get("sources", []),
#                 )
#             except Exception:
#                 agent_correct = bool(
#                     agent.get("answer", "").strip()
#                 )

#             try:
#                 fixed_correct = evaluate_question(
#                     question,
#                     fixed.get("answer", ""),
#                     fixed.get("sources", []),
#                 )
#             except Exception:
#                 fixed_correct = bool(
#                     fixed.get("answer", "").strip()
#                 )
#         else:
#             agent_correct = bool(
#                 agent.get("answer", "").strip()
#             )
#             fixed_correct = bool(
#                 fixed.get("answer", "").strip()
#             )

#         rows.append(
#             {
#                 "id": item.get("id"),
#                 "question": question,
#                 "agent": agent,
#                 "fixed": fixed,
#                 "agent_answered": bool(
#                     agent.get("answer", "").strip()
#                 ),
#                 "fixed_answered": bool(
#                     fixed.get("answer", "").strip()
#                 ),
#                 "agent_correct": bool(agent_correct),
#                 "fixed_correct": bool(fixed_correct),
#             }
#         )

#     total = len(rows)

#     agent_answered = sum(
#         row["agent_answered"]
#         for row in rows
#     )
#     fixed_answered = sum(
#         row["fixed_answered"]
#         for row in rows
#     )

#     agent_correct = sum(
#         row["agent_correct"]
#         for row in rows
#     )
#     fixed_correct = sum(
#         row["fixed_correct"]
#         for row in rows
#     )

#     agent_steps = (
#         sum(
#             row["agent"].get("steps", 0)
#             for row in rows
#         )
#         / total
#         if total
#         else 0
#     )

#     fixed_steps = (
#         sum(
#             row["fixed"].get("steps", 0)
#             for row in rows
#         )
#         / total
#         if total
#         else 0
#     )

#     agent_cost = sum(
#         row["agent"].get(
#             "estimated_cost",
#             0,
#         )
#         for row in rows
#     )

#     fixed_cost = sum(
#         row["fixed"].get(
#             "estimated_cost",
#             0,
#         )
#         for row in rows
#     )

#     return {
#         "question_count": total,
#         "agent": {
#             "answered": agent_answered,
#             "correct": agent_correct,
#             "reliability": round(
#                 agent_correct / total,
#                 4,
#             )
#             if total
#             else 0,
#             "average_steps": round(
#                 agent_steps,
#                 2,
#             ),
#             "estimated_cost": round(
#                 agent_cost,
#                 4,
#             ),
#         },
#         "fixed_workflow": {
#             "answered": fixed_answered,
#             "correct": fixed_correct,
#             "reliability": round(
#                 fixed_correct / total,
#                 4,
#             )
#             if total
#             else 0,
#             "average_steps": round(
#                 fixed_steps,
#                 2,
#             ),
#             "estimated_cost": round(
#                 fixed_cost,
#                 4,
#             ),
#         },
#         "rows": rows,
#     }


# if __name__ == "__main__":
#     result = run_agent("What is the rent?")

#     print("\n" + "=" * 70)
#     print("SAMPLE RESULT")
#     print("=" * 70)
#     print(result)




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
