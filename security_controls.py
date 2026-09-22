"""
Security controls for the legal-contract agent.

These controls are intentionally independent of rag.py and agent_loops.py.
They can be integrated at the tool/context/output boundaries without changing
the existing retrieval implementation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable


REFUSAL_MESSAGE = "I don't know based on the provided contracts."

INJECTION_PATTERNS = [
    re.compile(r"\bignore\s+(all\s+)?previous\s+instructions\b", re.I),
    re.compile(r"\bignore\s+(the\s+)?system\s+prompt\b", re.I),
    re.compile(r"\breveal\s+(your\s+)?system\s+(prompt|instructions)\b", re.I),
    re.compile(r"\bdisclose\s+(hidden|secret|confidential)\s+instructions\b", re.I),
    re.compile(r"\bact\s+as\s+(an?\s+)?administrator\b", re.I),
    re.compile(r"\bcall\s+(the\s+)?[a-z_]+\s+tool\b", re.I),
    re.compile(r"\btool\s*:\s*[a-z_]+\b", re.I),
    re.compile(r"\bdo\s+not\s+answer\s+the\s+user\b", re.I),
]

REQUIRED_SOURCE_KEYS = {"source", "page"}

ALLOWED_TOOLS = {
    "retrieve_contract_evidence",
    "draft_grounded_answer",
}


@dataclass(frozen=True)
class SecurityDecision:
    allowed: bool
    reason: str


def detect_prompt_injection(text: str) -> list[str]:
    """Return matching indicator descriptions; this is a detector, not proof."""
    matches = []

    for pattern in INJECTION_PATTERNS:
        match = pattern.search(text or "")
        if match:
            matches.append(match.group(0))

    return matches


def validate_untrusted_content(text: str) -> SecurityDecision:
    """
    Retrieved contract text is data, not executable instructions.
    """
    matches = detect_prompt_injection(text)

    if matches:
        return SecurityDecision(
            allowed=False,
            reason="prompt_injection_indicator_detected",
        )

    return SecurityDecision(
        allowed=True,
        reason="no_injection_indicator_detected",
    )


def wrap_untrusted_context(text: str) -> str:
    """
    Clearly delimit retrieved material so the generation prompt can distinguish
    contract data from application instructions.
    """
    return (
        "BEGIN_UNTRUSTED_CONTRACT_DATA\n"
        f"{text}\n"
        "END_UNTRUSTED_CONTRACT_DATA"
    )


def validate_tool_call(tool_name: str) -> SecurityDecision:
    """Least-privilege tool allowlist."""
    if tool_name not in ALLOWED_TOOLS:
        return SecurityDecision(
            allowed=False,
            reason="tool_not_allowlisted",
        )

    return SecurityDecision(
        allowed=True,
        reason="tool_allowlisted",
    )


def validate_retrieval_results(results: Any) -> SecurityDecision:
    """
    Validate the minimal retrieval-result contract expected by this project.
    """
    if not isinstance(results, list):
        return SecurityDecision(False, "results_must_be_list")

    for item in results:
        if not isinstance(item, dict):
            return SecurityDecision(False, "result_must_be_dict")

        document = item.get("document")
        if not isinstance(document, dict):
            return SecurityDecision(False, "missing_document")

        content = document.get("content")
        metadata = document.get("metadata")

        if not isinstance(content, str):
            return SecurityDecision(False, "invalid_content")

        if not isinstance(metadata, dict):
            return SecurityDecision(False, "invalid_metadata")

        if not REQUIRED_SOURCE_KEYS.issubset(metadata.keys()):
            return SecurityDecision(False, "missing_source_metadata")

    return SecurityDecision(True, "retrieval_schema_valid")


def validate_answer_output(
    answer: str,
    sources: Iterable[dict[str, Any]] | None = None,
) -> SecurityDecision:
    """
    Lightweight final-output validation.

    The validator blocks obvious instruction leakage and malformed source
    metadata. It does not claim semantic correctness; the existing grounding
    evaluator remains responsible for answer correctness.
    """
    if not isinstance(answer, str) or not answer.strip():
        return SecurityDecision(False, "empty_answer")

    leakage_patterns = [
        re.compile(r"\bsystem\s+prompt\b", re.I),
        re.compile(r"\bhidden\s+instructions\b", re.I),
        re.compile(r"\bdeveloper\s+instructions\b", re.I),
    ]

    for pattern in leakage_patterns:
        if pattern.search(answer):
            return SecurityDecision(False, "instruction_leakage_detected")

    if sources is not None:
        for source in sources:
            if not isinstance(source, dict):
                return SecurityDecision(False, "invalid_source")

            if not REQUIRED_SOURCE_KEYS.issubset(source.keys()):
                return SecurityDecision(False, "invalid_source_metadata")

    return SecurityDecision(True, "answer_output_valid")


def security_gate(
    *,
    tool_name: str | None = None,
    retrieved_text: str | None = None,
    retrieval_results: Any = None,
    answer: str | None = None,
    sources: Iterable[dict[str, Any]] | None = None,
) -> SecurityDecision:
    """
    Combined boundary gate. The first failed control blocks the operation.
    """
    if tool_name is not None:
        decision = validate_tool_call(tool_name)
        if not decision.allowed:
            return decision

    if retrieval_results is not None:
        decision = validate_retrieval_results(retrieval_results)
        if not decision.allowed:
            return decision

    if retrieved_text is not None:
        decision = validate_untrusted_content(retrieved_text)
        if not decision.allowed:
            return decision

    if answer is not None:
        decision = validate_answer_output(answer, sources)
        if not decision.allowed:
            return decision

    return SecurityDecision(True, "security_checks_passed")
