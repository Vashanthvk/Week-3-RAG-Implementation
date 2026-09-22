"""
Fast security baseline/control evaluation.

This evaluates the security boundary controls independently of the LLM.
It deliberately does not alter the existing agent or contract corpus.
"""

from __future__ import annotations

import json
from pathlib import Path

from security_controls import (
    validate_tool_call,
    validate_untrusted_content,
)


ROOT = Path(__file__).parent
CASES = ROOT / "security_attack_cases.json"
REPORT = ROOT / "SECURITY_EVALUATION_REPORT.md"


def baseline_decision(case):
    """
    Baseline represents the absence of an explicit security gate:
    injection/tool payloads are not blocked by a dedicated security control.
    """
    if case["type"] in {
        "direct_prompt_injection",
        "indirect_prompt_injection",
        "unauthorized_tool",
    }:
        return "ALLOW"

    return "ALLOW"


def controlled_decision(case):
    if case["type"] in {
        "direct_prompt_injection",
        "indirect_prompt_injection",
    }:
        return (
            "ALLOW"
            if validate_untrusted_content(case["input"]).allowed
            else "BLOCK"
        )

    if case["type"] == "unauthorized_tool":
        return (
            "ALLOW"
            if validate_tool_call(case["input"]).allowed
            else "BLOCK"
        )

    return "ALLOW"


def main():
    cases = json.loads(CASES.read_text(encoding="utf-8"))

    baseline_blocked = 0
    controlled_blocked = 0
    attack_cases = []

    for case in cases:
        before = baseline_decision(case)
        after = controlled_decision(case)

        expected = case["expected"]

        if before == "BLOCK":
            baseline_blocked += 1

        if after == "BLOCK":
            controlled_blocked += 1

        attack_cases.append(
            {
                "id": case["id"],
                "type": case["type"],
                "expected": expected,
                "before": before,
                "after": after,
                "after_pass": after == expected,
            }
        )

    attacks = [
        case for case in attack_cases
        if case["type"] in {
            "direct_prompt_injection",
            "indirect_prompt_injection",
            "unauthorized_tool",
        }
    ]

    attack_count = len(attacks)
    before_rate = (
        baseline_blocked / attack_count
        if attack_count else 0.0
    )
    after_rate = (
        controlled_blocked / attack_count
        if attack_count else 0.0
    )

    report = [
        "# Security Evaluation Report",
        "",
        "## Scope",
        "",
        "Direct prompt injection, indirect prompt injection, "
        "and unauthorized-tool attacks.",
        "",
        "## Before vs After",
        "",
        f"- Security attack cases: {attack_count}",
        f"- Explicit blocks before controls: {baseline_blocked}",
        f"- Explicit blocks after controls: {controlled_blocked}",
        f"- Block rate before: {before_rate:.2%}",
        f"- Block rate after: {after_rate:.2%}",
        "",
        "## Case Results",
        "",
        "| ID | Type | Expected | Before | After | Pass |",
        "|---|---|---|---|---|---|",
    ]

    for case in attack_cases:
        report.append(
            f"| {case['id']} | {case['type']} | "
            f"{case['expected']} | {case['before']} | "
            f"{case['after']} | {case['after_pass']} |"
        )

    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")

    print("=" * 70)
    print("SECURITY BASELINE / CONTROL EVALUATION")
    print("=" * 70)
    print(f"Attack cases          : {attack_count}")
    print(f"Block rate before     : {before_rate:.2%}")
    print(f"Block rate after      : {after_rate:.2%}")
    print(
        "After-control passes  : "
        f"{sum(c['after_pass'] for c in attack_cases)}/{len(attack_cases)}"
    )
    print(f"Report                : {REPORT}")


if __name__ == "__main__":
    main()
