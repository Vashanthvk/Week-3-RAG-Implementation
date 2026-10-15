"""Hand-built legal-contract agent loop with security boundary checks.

The loop intentionally exposes each decision and tool call. Unlike the
Week 6 version, the *choice* of which tool to call next is made by the
model itself (a hand-rolled ReAct loop: Thought / Action / Action Input),
not hard-coded in Python -- that hard-coding is what run_fixed_workflow()
is for, and the two are deliberately different in that one respect only.

Security checks are applied to input, tool usage, retrieved contract data,
and final output.
"""

from __future__ import annotations

import calendar
import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from time import monotonic
from typing import Any

import ollama

from security_controls import (
    REFUSAL_MESSAGE,
    security_gate,
    wrap_untrusted_context,
)

from rag import (
    MODEL_NAME,
    bm25,
    build_context,
    documents,
    generate_answer_with_usage,
    retrieve_with_retry,
    should_refuse_answer,
    vector_store,
)

from hybrid_retrieval import get_filename


# ============================================================
# TOOLS
# ============================================================

CONTRACT_VERSIONS = [
    "Employment_Agreement",
    "Lease_Agreement",
    "Non_Disclosure_Agreement",
    "Master_Service_Agreement",
    "Software_License_Agreement",
]

# Used only to give get_definitions a corrective hint on a miss (e.g. the
# model invents a term that isn't in the contract) -- not a shortcut around
# the regex lookup itself, which is what actually resolves a term.
KNOWN_DEFINED_TERMS_BY_CONTRACT = {
    "Master_Service_Agreement": ["Cause", "Notice Period", "Renewal Term"],
    "Software_License_Agreement": ["Initial Term", "Termination Notice Period", "Renewal Date"],
    "Employment_Agreement": [],
    "Lease_Agreement": [],
    "Non_Disclosure_Agreement": [],
}

# Longer phrases first, so "Termination Notice Period" matches whole rather
# than also tripping the "Notice Period" check on the same span.
KNOWN_DEFINED_TERM_NAMES = [
    "Termination Notice Period",
    "Notice Period",
    "Initial Term",
    "Cause",
]


def question_defined_terms(question: str) -> list[str]:
    """Which known defined terms the question itself names, in order found.

    Deliberately reads the QUESTION, not whichever chunk retrieval happens
    to surface: MSA's Definitions chunk states both "Cause" (15 days) and
    "Notice Period" (30 days) side by side, so deciding what to resolve
    from chunk content alone is a coin flip between the two. The question
    itself is unambiguous about which one it means.
    """

    remaining = question or ""
    found = []
    for term in KNOWN_DEFINED_TERM_NAMES:
        if term in remaining:
            found.append(term)
            remaining = remaining.replace(term, "")
    return found


_WORD_RE = re.compile(r"[a-zA-Z]{4,}")


def _fuzzy_match_known_term(query_term: str, contract_version: str, full_text: str) -> str | None:
    """Deterministic "did you mean" lookup: word-overlap between the query
    and each of the contract's actual defined terms (name + definition
    text), used only when the exact quoted-term regex misses."""

    query_words = {w.lower() for w in _WORD_RE.findall(query_term or "")}
    if not query_words:
        return None

    best_term = None
    best_overlap = 0
    for known in KNOWN_DEFINED_TERMS_BY_CONTRACT.get(contract_version, []):
        pattern = re.compile(r'"' + re.escape(known) + r'"\s+means\s+([^.]+\.)', re.IGNORECASE)
        match = pattern.search(full_text)
        if not match:
            continue
        candidate_words = {w.lower() for w in _WORD_RE.findall(known + " " + match.group(1))}
        overlap = len(query_words & candidate_words)
        if overlap > best_overlap:
            best_overlap = overlap
            best_term = known
    return best_term


TOOL_DESCRIPTIONS = {
    "retrieve_contract_evidence": (
        "Search across all ingested contracts and return the top-ranked "
        "clause chunks relevant to a legal question. Does not look up a "
        "defined term's meaning and does not draft an answer."
    ),
    "get_definitions": (
        "Look up the literal meaning of ONE named defined term (for "
        "example 'Cause' or 'Notice Period') inside a single contract's "
        "Definitions section, chosen with the contract_version enum: "
        f"{CONTRACT_VERSIONS}. Does not search broadly across contracts "
        "and does not draft an answer. Do NOT call this for a fact that "
        "is already stated as a plain number, date, or amount in the "
        "most recent retrieve_contract_evidence observation -- only call "
        "it for a capitalized term that is referenced by name (e.g. "
        "'Cause') whose value is NOT already visible there."
    ),
    "draft_grounded_answer": (
        "Compose the final answer strictly from clause evidence and/or "
        "defined-term lookups already gathered earlier in this run. Does "
        "not search or look anything up itself; call it last."
    ),
}


# ============================================================
# BUDGETS
# ============================================================

@dataclass
class LoopBudget:
    max_steps: int = 8
    max_seconds: float = 90.0
    max_tokens: int = 9000
    max_cost: float = 0.045
    # Notional local-model rate, applied identically to the agent and the
    # fixed workflow so the race compares tool-call counts, not pricing.
    cost_per_1k_tokens: float = 0.0005


@dataclass
class AgentState:
    question: str
    budget: LoopBudget
    step: int = 0
    tool_calls: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    started_at: float = field(default_factory=monotonic)
    events: list[dict[str, Any]] = field(default_factory=list)
    memory: list[str] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
    definitions: dict[str, str] = field(default_factory=dict)
    transcript: list[tuple[str, str]] = field(default_factory=list)
    seen_calls: set[tuple[str, str]] = field(default_factory=set)
    stuck_count: int = 0
    answer: str = ""
    sources: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str = ""


def _record(state: AgentState, phase: str, message: str, **data: Any) -> None:
    event = {"step": state.step, "phase": phase, "message": message}
    event.update(data)
    state.events.append(event)
    print(f"[agent step {state.step}] {phase}: {message}")


def _budget_exceeded(state: AgentState, budget: LoopBudget) -> str | None:
    """Check all four budgets. Order is significant only for the log message."""
    if state.step > budget.max_steps:
        return "max_iterations"
    if monotonic() - state.started_at >= budget.max_seconds:
        return "max_wall_clock"
    if state.total_tokens >= budget.max_tokens:
        return "max_tokens"
    if state.estimated_cost >= budget.max_cost:
        return "max_cost"
    return None


def _apply_usage(state: AgentState, budget: LoopBudget, prompt_tokens: int, completion_tokens: int) -> None:
    state.total_tokens += prompt_tokens + completion_tokens
    state.estimated_cost = round(state.total_tokens / 1000 * budget.cost_per_1k_tokens, 6)


def _call_llm(prompt: str) -> dict[str, Any]:
    """Single point of contact with the model; every call's real token usage
    is captured here so the loop's budgets and the race's token totals are
    both grounded in Ollama's own counts, not an assumed constant.

    Routing runs at a small non-zero temperature (unlike the temperature=0
    final-answer call in rag.generate_answer_with_usage): at temperature=0
    this 3B model would regenerate the exact same wrong tool call after a
    corrective Observation, since the surrounding context barely changed --
    a real, observed failure mode, not a hypothetical one.
    """

    response = ollama.generate(
        model=MODEL_NAME,
        prompt=prompt,
        options={"temperature": _REACT_TEMPERATURE, "seed": 42},
    )
    return {
        "text": (response.response or "").strip(),
        "prompt_tokens": response.prompt_eval_count or 0,
        "completion_tokens": response.eval_count or 0,
    }


def retrieve_contract_evidence(question: str, state: AgentState) -> dict[str, Any]:
    """Tool 1: retrieve evidence and expose relevance for the next decision."""

    state.tool_calls += 1
    retrieval = retrieve_with_retry(vector_store, documents, bm25, question)
    # Keep only the single top-ranked chunk. With FINAL_TOP_K=5 over this
    # small corpus a wider slice tends to pull in a contract's whole text
    # (both its Definitions and Termination chunks) regardless of query,
    # which would make get_definitions redundant rather than necessary.
    results = retrieval["results"][:1]

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


def get_definitions(term: str, contract_version: str, state: AgentState) -> dict[str, Any]:
    """Tool 3: resolve one defined term's meaning from one named contract."""

    state.tool_calls += 1

    tool_security = security_gate(tool_name="get_definitions")
    if not tool_security.allowed:
        state.memory.append(f"security block: {tool_security.reason}")
        _record(
            state,
            "SECURITY",
            f"Blocked get_definitions: {tool_security.reason}.",
            reason=tool_security.reason,
        )
        return {
            "term": term,
            "contract_version": contract_version,
            "found": False,
            "security_blocked": True,
            "security_reason": tool_security.reason,
        }

    normalized_version = str(contract_version or "").strip()
    if normalized_version.endswith(".pdf"):
        normalized_version = normalized_version[:-4]
    version_lookup = {version.lower(): version for version in CONTRACT_VERSIONS}
    normalized_version = version_lookup.get(normalized_version.lower(), normalized_version)

    if normalized_version not in CONTRACT_VERSIONS:
        state.memory.append(f"get_definitions: unknown contract_version '{contract_version}'")
        return {
            "term": term,
            "contract_version": contract_version,
            "found": False,
            "error": "unknown_contract_version",
        }

    source_name = f"{normalized_version}.pdf"
    matching_chunks = [
        doc["content"]
        for doc in documents
        if get_filename(doc.get("metadata", {}).get("source")) == source_name
    ]
    full_text = re.sub(r"\s+", " ", " ".join(matching_chunks))
    normalized_term = re.sub(r"\s+", " ", term or "").strip()

    pattern = re.compile(r'"' + re.escape(normalized_term) + r'"\s+means\s+([^.]+\.)', re.IGNORECASE)
    match = pattern.search(full_text)
    resolved_term = normalized_term

    if not match:
        # The model sometimes asks for a paraphrase (e.g. "cure period")
        # instead of the contract's own defined-term name ("Cause"). Before
        # giving up, deterministically check whether the query words appear
        # inside one of this contract's actual defined terms or their
        # definition text, and resolve to that term if so -- a "did you
        # mean" fallback, not a second free-text guess.
        fuzzy_term = _fuzzy_match_known_term(normalized_term, normalized_version, full_text)
        if fuzzy_term:
            pattern = re.compile(r'"' + re.escape(fuzzy_term) + r'"\s+means\s+([^.]+\.)', re.IGNORECASE)
            match = pattern.search(full_text)
            resolved_term = fuzzy_term

    if not match:
        known_terms = KNOWN_DEFINED_TERMS_BY_CONTRACT.get(normalized_version, [])
        state.memory.append(f"get_definitions: '{normalized_term}' not found in {normalized_version}")
        return {
            "term": normalized_term,
            "contract_version": normalized_version,
            "found": False,
            "known_terms": known_terms,
        }

    normalized_term = resolved_term

    definition_text = match.group(1).strip()

    content_security = security_gate(retrieved_text=definition_text)
    if not content_security.allowed:
        state.stop_reason = "security_blocked"
        state.memory.append(f"security block: {content_security.reason}")
        _record(
            state,
            "SECURITY",
            f"Blocked untrusted definition text: {content_security.reason}.",
            reason=content_security.reason,
        )
        return {
            "term": normalized_term,
            "contract_version": normalized_version,
            "found": False,
            "security_blocked": True,
            "security_reason": content_security.reason,
        }

    state.definitions[normalized_term] = definition_text
    state.memory.append(f"get_definitions: '{normalized_term}' -> {definition_text}")
    return {
        "term": normalized_term,
        "contract_version": normalized_version,
        "found": True,
        "definition": definition_text,
    }


# ============================================================
# DETERMINISTIC DATE MATH (shared by both systems, so the race
# compares tool-selection strategy, not who can do arithmetic)
# ============================================================

_MONTH_NAMES = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]


def _parse_date_token(text: str) -> date | None:
    pattern = r"(\d{1,2})\s+(" + "|".join(_MONTH_NAMES) + r")\s+(\d{4})"
    match = re.search(pattern, text or "", re.IGNORECASE)
    if not match:
        return None
    day = int(match.group(1))
    month = _MONTH_NAMES.index(match.group(2).lower()) + 1
    year = int(match.group(3))
    return date(year, month, day)


def _extract_count(definition_text: str) -> tuple[int, str] | None:
    match = re.search(r"\((\d{1,3})\)\s*(day|month)s?", definition_text or "", re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1)), match.group(2).lower()


def _add_period(base: date, n: int, unit: str) -> date:
    if unit == "day":
        return base + timedelta(days=n)
    month_index = base.month - 1 + n
    year = base.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _find_effective_date(state: AgentState) -> date | None:
    for result in state.results:
        content = result.get("document", {}).get("content", "")
        match = re.search(r"effective as of (\d{1,2}\s+\w+\s+\d{4})", content, re.IGNORECASE)
        if match:
            found = _parse_date_token(match.group(1))
            if found:
                return found
    return None


def compute_grounded_facts(question: str, state: AgentState) -> list[str]:
    """Turn resolved defined terms into computed dates deterministically.

    A 3B local model is not reliable at date arithmetic, so the loop does
    the math in code and hands the model an already-computed fact to
    restate -- the model's job stays "pick tools, then phrase the answer,"
    never "add 45 days to a date."
    """

    facts = []
    anchor = _parse_date_token(question)
    effective = _find_effective_date(state)
    for term, definition_text in state.definitions.items():
        extracted = _extract_count(definition_text)
        if not extracted:
            continue
        n, unit = extracted
        # Day-counted terms (notice/cure periods) only make sense anchored
        # to a date the question actually names -- falling back to the
        # contract's Effective Date would silently answer a question that
        # was never asked. Month-counted terms (e.g. a 12-month Initial
        # Term) anchor to the Effective Date since that's what they mean.
        base = anchor if unit == "day" else effective
        if not base:
            continue
        result_date = _add_period(base, n, unit)
        facts.append(
            f"Computed fact: '{term}' is {n} {unit}(s); applied to "
            f"{base.strftime('%d %B %Y')} this gives {result_date.strftime('%d %B %Y')}."
        )
    return facts


def draft_grounded_answer(question: str, state: AgentState) -> dict[str, Any]:
    """Tool 2: draft only after evidence (and, if needed, definitions) are in."""

    state.tool_calls += 1

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
        return {
            "answer": state.answer,
            "sources": [],
            "security_blocked": True,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }

    prompt_tokens = 0
    completion_tokens = 0
    if should_refuse_answer(question, state.results) and not state.definitions:
        state.answer = REFUSAL_MESSAGE
    else:
        context = wrap_untrusted_context(build_context(state.results))

        if state.definitions:
            definition_lines = "\n".join(
                f'"{term}" means: {text}' for term, text in state.definitions.items()
            )
            context += f"\n\nDEFINED TERMS RESOLVED THIS RUN:\n{definition_lines}"

        computed_facts = compute_grounded_facts(question, state)
        if computed_facts:
            context += (
                "\n\nCOMPUTED FACTS (already calculated, trustworthy -- restate plainly):\n"
                + "\n".join(computed_facts)
            )

        usage = generate_answer_with_usage(question, context)
        state.answer = usage["answer"]
        prompt_tokens = usage["prompt_tokens"]
        completion_tokens = usage["completion_tokens"]
        _apply_usage(state, state.budget, usage["prompt_tokens"], usage["completion_tokens"])

    state.sources = _format_sources(state.results)

    output_security = security_gate(answer=state.answer, sources=state.sources)
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
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }

    state.memory.append(
        f"drafted answer from {len(state.results)} chunks and {len(state.definitions)} definitions"
    )
    return {
        "answer": state.answer,
        "sources": state.sources,
        "security_blocked": False,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
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


# ============================================================
# REACT LOOP (the model chooses the next tool)
# ============================================================

_REACT_INSTRUCTIONS = """You are a legal-contract agent. Decide the next tool call yourself, one step \
at a time, using only the tools below. Never answer from general knowledge -- only from tool results. \
Never call the same tool with the same input twice. You have at most {max_steps} steps total.

Tools:
- retrieve_contract_evidence: {retrieve_desc}
  Action Input: {{"question": "<search text>"}}
- get_definitions: {get_definitions_desc}
  Action Input: {{"term": "<exact defined term>", "contract_version": "<one of {versions}>"}}
- draft_grounded_answer: {draft_desc}
  Action Input: {{}}

Respond with EXACTLY three lines, nothing else:
Thought: <one short sentence of reasoning>
Action: <retrieve_contract_evidence|get_definitions|draft_grounded_answer>
Action Input: <a single JSON object as shown above>

Here are two worked examples of the pattern to follow.

Example A -- the evidence already answers the question, so no lookup is needed:
Question: What is the monthly rent?
(no tools called yet)
Thought: I need the relevant clause first.
Action: retrieve_contract_evidence
Action Input: {{"question": "monthly rent"}}
Observation (retrieve_contract_evidence): Top result from Lease_Agreement.pdf: "Monthly Rent USD 1,500 payable before the 5th of each month." (best_score=1.00)
Thought: The amount is already a plain number in the observation; nothing else to resolve.
Action: draft_grounded_answer
Action Input: {{}}

Example B -- the clause names a defined term but never states its value, so it must be resolved before drafting:
Question: If a party terminates for Cause, how many days of written notice are required?
(no tools called yet)
Thought: I need the termination clause first.
Action: retrieve_contract_evidence
Action Input: {{"question": "termination for Cause notice"}}
Observation (retrieve_contract_evidence): Top result from Master_Service_Agreement.pdf: "...terminate this Agreement for Cause, effective immediately upon expiry of the cure period described in the definition of Cause if the breach remains uncured..." (best_score=0.80)
Thought: The clause names Cause but never gives a day count, so I must resolve that exact term.
Action: get_definitions
Action Input: {{"term": "Cause", "contract_version": "Master_Service_Agreement"}}
Observation (get_definitions): 'Cause' in Master_Service_Agreement means: a material breach of this Agreement that the breaching party fails to cure within fifteen (15) days after receiving written notice describing the breach.
Thought: Now I have the exact day count the question needs.
Action: draft_grounded_answer
Action Input: {{}}

Now do the same for the real question below. Only call get_definitions for a \
term whose exact number or date the question needs but the most recent \
retrieve_contract_evidence observation does not already spell out.
"""

_REACT_TEMPERATURE = 0.2

_ACTION_RE = re.compile(r"Action:\s*([A-Za-z_]+)", re.IGNORECASE)
_INPUT_RE = re.compile(r"Action Input:\s*(\{.*\})", re.IGNORECASE | re.DOTALL)
_THOUGHT_RE = re.compile(r"Thought:\s*(.+)", re.IGNORECASE)


def _build_react_prompt(question: str, state: AgentState) -> str:
    header = _REACT_INSTRUCTIONS.format(
        retrieve_desc=TOOL_DESCRIPTIONS["retrieve_contract_evidence"],
        get_definitions_desc=TOOL_DESCRIPTIONS["get_definitions"],
        draft_desc=TOOL_DESCRIPTIONS["draft_grounded_answer"],
        versions=", ".join(CONTRACT_VERSIONS),
        max_steps=state.budget.max_steps,
    )
    if state.transcript:
        history = "\n".join(
            f"Observation ({tool_name}): {observation}" for tool_name, observation in state.transcript
        )
        called_tools = ", ".join(sorted({tool_name for tool_name, _ in state.transcript}))
        history += f"\n\nTools already called this run: {called_tools}."
    else:
        history = "(no tools called yet)"

    hint_terms = question_defined_terms(question)
    hint_line = (
        f"Hint: the question's own wording names these possible defined terms: {hint_terms}.\n"
        if hint_terms
        else ""
    )
    return (
        f"{header}\nQuestion: {question}\n{hint_line}"
        f"Step {state.step} of {state.budget.max_steps}.\n{history}\nThought:"
    )


def _parse_react_response(text: str) -> tuple[str, dict[str, Any], str] | None:
    action_match = _ACTION_RE.search(text)
    if not action_match:
        return None
    tool_name = action_match.group(1).strip()

    tool_input: dict[str, Any] = {}
    input_match = _INPUT_RE.search(text)
    if input_match:
        try:
            tool_input = json.loads(input_match.group(1))
        except json.JSONDecodeError:
            tool_input = {}

    thought_match = _THOUGHT_RE.search(text)
    thought = thought_match.group(1).strip().splitlines()[0] if thought_match else ""

    return tool_name, tool_input, thought


def _dispatch_tool(tool_name: str, tool_input: dict[str, Any], question: str, state: AgentState) -> dict[str, Any]:
    if tool_name == "retrieve_contract_evidence":
        query = tool_input.get("question") or question
        return retrieve_contract_evidence(query, state)
    if tool_name == "get_definitions":
        return get_definitions(tool_input.get("term", ""), tool_input.get("contract_version", ""), state)
    if tool_name == "draft_grounded_answer":
        return draft_grounded_answer(question, state)
    return {"error": f"unknown_tool:{tool_name}"}


def _summarize_observation(tool_name: str, observation: dict[str, Any]) -> str:
    if observation.get("security_blocked"):
        return f"Blocked: {observation.get('security_reason', 'security_blocked')}."
    if tool_name == "retrieve_contract_evidence":
        results = observation.get("results", [])
        if not results:
            return "No relevant contract chunks found."
        top = results[0]["document"]
        source = get_filename(top["metadata"].get("source"))
        snippet = top["content"][:220].replace("\n", " ")
        return f'Top result from {source}: "{snippet}" (best_score={observation.get("best_score", 0.0):.2f})'
    if tool_name == "get_definitions":
        if observation.get("found"):
            return f"'{observation['term']}' in {observation['contract_version']} means: {observation['definition']}"
        known_terms = observation.get("known_terms") or []
        hint = f" This contract's defined terms are: {', '.join(known_terms)}." if known_terms else ""
        return f"'{observation.get('term')}' was not found as a defined term in {observation.get('contract_version')}.{hint}"
    if tool_name == "draft_grounded_answer":
        return f"Final answer drafted: {observation.get('answer', '')[:200]}"
    return str(observation)[:200]


def run_agent(question: str, budget: LoopBudget | None = None) -> dict[str, Any]:
    """Run the ReAct loop: the model itself picks retrieve / get_definitions /
    draft each turn, until it drafts an answer or a budget stops it."""

    budget = budget or LoopBudget()
    state = AgentState(question=question, budget=budget)

    question_security = security_gate(retrieved_text=question)
    if not question_security.allowed:
        state.answer = REFUSAL_MESSAGE
        state.stop_reason = "security_blocked"
        state.memory.append(f"security block: {question_security.reason}")
        _record(state, "SECURITY", f"Blocked question: {question_security.reason}.", reason=question_security.reason)
        return _finalize_agent(state)

    _record(state, "PLAN", "Let the model choose the next tool, one step at a time.")

    while not state.answer:
        state.step += 1

        reason = _budget_exceeded(state, budget)
        if reason:
            state.stop_reason = reason
            _record(state, "STOP", f"Budget reached before model call: {reason}.")
            break

        prompt = _build_react_prompt(question, state)
        llm_result = _call_llm(prompt)
        _apply_usage(state, budget, llm_result["prompt_tokens"], llm_result["completion_tokens"])

        reason = _budget_exceeded(state, budget)
        if reason:
            state.stop_reason = reason
            _record(state, "STOP", f"Budget reached after model call: {reason}.")
            break

        parsed = _parse_react_response(llm_result["text"])
        if parsed is None:
            state.transcript.append(
                ("format_error", "Could not parse your last response. Reply with exactly Thought/Action/Action Input.")
            )
            _record(state, "OBSERVE", "Model response did not match the required format; asked it to retry.")
            continue

        tool_name, tool_input, thought = parsed

        if tool_name not in TOOL_DESCRIPTIONS:
            state.transcript.append((tool_name, f"Unknown tool '{tool_name}'. Choose one of {list(TOOL_DESCRIPTIONS)}."))
            _record(state, "OBSERVE", f"Unknown tool requested: {tool_name}.")
            continue

        already_retrieved = tool_name == "retrieve_contract_evidence" and any(
            called == "retrieve_contract_evidence" for called, _ in state.transcript
        )
        call_signature = (tool_name, json.dumps(tool_input, sort_keys=True))
        repeat_call = call_signature in state.seen_calls and tool_name != "draft_grounded_answer"

        if already_retrieved or repeat_call:
            reason_text = (
                "retrieve_contract_evidence may only be called once per question and already ran"
                if already_retrieved
                else "you already called this tool with this exact input; the result would be unchanged"
            )
            have_enough = bool(state.results) and (bool(state.definitions) or state.step >= 3)
            next_step_hint = (
                "You already have retrieved evidence and at least one resolved definition (or enough "
                "attempts) -- call draft_grounded_answer now with Action Input {}."
                if have_enough
                else "Choose get_definitions for a specific defined term named in the evidence above."
            )
            state.transcript.append((tool_name, f"Skipped: {reason_text}. {next_step_hint}"))
            _record(state, "OBSERVE", f"Skipped call to {tool_name}: {reason_text}.")
            state.stuck_count += 1

            if state.stuck_count >= 2:
                # Stuck-loop guard: two invalid/repeated actions in a row means
                # further routing calls are unlikely to converge on their own.
                # Force the terminal tool with whatever evidence is already in
                # hand, rather than spinning out the token budget on retries.
                _record(state, "STOP", "Stuck-loop guard: forcing draft_grounded_answer after repeated invalid actions.")
                draft_grounded_answer(question, state)
                state.stop_reason = state.stop_reason or "stuck_loop_forced_draft"
                break
            continue
        state.seen_calls.add(call_signature)
        state.stuck_count = 0

        _record(state, "ACT", f"Call {tool_name}.", tool=tool_name, argument=tool_input, thought=thought)

        observation = _dispatch_tool(tool_name, tool_input, question, state)

        if observation.get("security_blocked"):
            state.stop_reason = "security_blocked"
            _record(state, "STOP", "Security boundary blocked this run.")
            break

        summary = _summarize_observation(tool_name, observation)
        state.transcript.append((tool_name, summary))
        _record(state, "OBSERVE", summary)

        if tool_name == "draft_grounded_answer":
            state.stop_reason = state.stop_reason or "answer_ready"
            break

    if not state.stop_reason:
        state.stop_reason = "budget_exhausted"

    return _finalize_agent(state)


def _finalize_agent(state: AgentState) -> dict[str, Any]:
    return {
        "answer": state.answer,
        "sources": state.sources,
        "events": state.events,
        "memory": state.memory,
        "steps": state.step,
        "tool_calls": state.tool_calls,
        "total_tokens": state.total_tokens,
        "estimated_cost": state.estimated_cost,
        "elapsed_seconds": round(monotonic() - state.started_at, 4),
        "stop_reason": state.stop_reason,
    }


# ============================================================
# FIXED WORKFLOW (hard-coded steps, same tools, no loop)
# ============================================================

def run_fixed_workflow(question: str, budget: LoopBudget | None = None) -> dict[str, Any]:
    """Run the known sequence: retrieve, then (only if a static keyword
    table finds a referenced defined term in the top clause) resolve it,
    then draft. Every branch is decided by Python code, never the model."""

    budget = budget or LoopBudget()
    state = AgentState(question=question, budget=budget)

    question_security = security_gate(retrieved_text=question)
    if not question_security.allowed:
        state.answer = REFUSAL_MESSAGE
        return _finalize_fixed(state, "security_blocked")

    state.step = 1
    _record(state, "STEP", "Fixed step 1: retrieve contract evidence.", tool="retrieve_contract_evidence")
    retrieval_observation = retrieve_contract_evidence(question, state)
    if retrieval_observation.get("security_blocked"):
        return _finalize_fixed(state, "security_blocked")

    top_result = state.results[0] if state.results else None
    # Static, deterministic: which of the fixed defined-term names appear
    # in the question's own wording (see question_defined_terms). Reading
    # the question rather than the retrieved chunk avoids a coin-flip when
    # a contract's Definitions section states more than one term together.
    referenced_terms = question_defined_terms(question)
    contract_version = None
    if top_result:
        source = get_filename(top_result["document"]["metadata"].get("source"))
        contract_version = source[:-4] if source.endswith(".pdf") else source

    if referenced_terms and contract_version in CONTRACT_VERSIONS:
        state.step = 2
        for term in referenced_terms[:2]:
            _record(state, "STEP", f"Fixed step 2: resolve defined term '{term}'.", tool="get_definitions")
            observation = get_definitions(term, contract_version, state)
            if observation.get("security_blocked"):
                return _finalize_fixed(state, "security_blocked")

    state.step += 1
    _record(state, "STEP", "Fixed step 3: draft the grounded answer.", tool="draft_grounded_answer")
    draft_observation = draft_grounded_answer(question, state)
    if draft_observation.get("security_blocked"):
        return _finalize_fixed(state, "security_blocked")

    return _finalize_fixed(state, "answer_ready")


def _finalize_fixed(state: AgentState, stop_reason: str) -> dict[str, Any]:
    return {
        "answer": state.answer,
        "sources": state.sources,
        "events": state.events,
        "memory": state.memory,
        "steps": state.step,
        "tool_calls": state.tool_calls,
        "total_tokens": state.total_tokens,
        "estimated_cost": state.estimated_cost,
        "elapsed_seconds": round(monotonic() - state.started_at, 4),
        "stop_reason": stop_reason,
    }


# ============================================================
# COMPARISON HELPER (kept for the existing Week-7 report pipeline)
# ============================================================

def compare_workflows(
    questions: list[dict[str, Any]],
    agent_runner=run_agent,
    fixed_runner=run_fixed_workflow,
) -> dict[str, Any]:
    """Compare both workflows using a question set and simple checks."""

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
