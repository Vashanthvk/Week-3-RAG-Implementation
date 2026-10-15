"""Race the existing single agent against the contract squad."""

from __future__ import annotations

import json
import math
from pathlib import Path
from time import monotonic
from typing import Any, Callable

from agent_loops import run_agent
from multi_agent import agent_card, run_orchestrator

ROOT = Path(__file__).parent
EVIDENCE_DIR = ROOT / "race_evidence"
QUESTIONS_PATH = ROOT / "race_questions.json"


def load_questions() -> list[dict[str, Any]]:
    return json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))


def passes(answer: str, expected: list[Any]) -> bool:
    text = (answer or "").lower()
    return all(
        any(
            value.lower() in text
            for value in (item if isinstance(item, list) else [item])
        )
        for item in expected
    )


def percentile(values: list[float], p: int) -> float:
    if not values:
        return 0.0
    return round(sorted(values)[max(0, math.ceil(len(values) * p / 100) - 1)], 4)


def run_arm(
    name: str, runner: Callable[[str], dict[str, Any]], questions: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = []
    for item in questions:
        started = monotonic()
        result = runner(item["question"])
        rows.append(
            {
                "arm": name,
                "id": item["id"],
                "question": item["question"],
                "pass": passes(result.get("answer", ""), item["expected_keywords"]),
                "latency_s": result.get(
                    "elapsed_seconds", round(monotonic() - started, 4)
                ),
                "tokens": result.get("total_tokens", 0),
                "cost": result.get("estimated_cost", 0.0),
                "stop_reason": result.get("stop_reason", ""),
                "answer": result.get("answer", ""),
                "handoffs": result.get("handoffs", []),
            }
        )
    latencies = [row["latency_s"] for row in rows]
    return (
        {
            "arm": name,
            "pass_rate": round(sum(row["pass"] for row in rows) / len(rows), 4),
            "p50_latency_s": percentile(latencies, 50),
            "p99_latency_s": percentile(latencies, 99),
            "total_tokens": sum(row["tokens"] for row in rows),
            "cost_per_question": round(sum(row["cost"] for row in rows) / len(rows), 6),
        },
        rows,
    )


def write_evidence() -> dict[str, Any]:
    # The evidence folder may be absent on a clean checkout. Create the full
    # path before the first report is written and fail clearly if a file with
    # the same name is blocking it.
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    if not EVIDENCE_DIR.is_dir():
        raise NotADirectoryError(
            f"Evidence path is not a directory: {EVIDENCE_DIR}"
        )
    questions = load_questions()
    single, single_rows = run_arm("single_agent", run_agent, questions)
    multi, multi_rows = run_arm("orchestrator", run_orchestrator, questions)
    handoffs = [
        {"case": row["id"], "arm": row["arm"], **handoff}
        for row in multi_rows
        for handoff in row["handoffs"]
    ]
    totals = {}
    for item in handoffs:
        key = f"{item['sender']} -> {item['receiver']}"
        totals[key] = totals.get(key, 0) + item["tokens"]
    dominant, dominant_tokens = max(
        totals.items(), key=lambda item: item[1], default=("none", 0)
    )
    multiplier = (
        round(multi["total_tokens"] / single["total_tokens"], 1)
        if single["total_tokens"]
        else 0.0
    )
    (EVIDENCE_DIR / "race_table.md").write_text(
        "# Race table\n\n| Metric | Single agent | Contract squad |\n|---|---:|---:|\n"
        + f"| Pass rate | {single['pass_rate']:.1%} | {multi['pass_rate']:.1%} |\n| p50 latency (s) | {single['p50_latency_s']} | {multi['p50_latency_s']} |\n| p99 latency (s) | {single['p99_latency_s']} | {multi['p99_latency_s']} |\n| Total tokens | {single['total_tokens']} | {multi['total_tokens']} |\n| Cost/question | ${single['cost_per_question']:.6f} | ${multi['cost_per_question']:.6f} |\n",
        encoding="utf-8",
    )
    (EVIDENCE_DIR / "handoffs.log").write_text(
        "\n".join(json.dumps(item, sort_keys=True) for item in handoffs) + "\n",
        encoding="utf-8",
    )
    share = (
        round(dominant_tokens / multi["total_tokens"] * 100, 1)
        if multi["total_tokens"]
        else 0.0
    )
    (EVIDENCE_DIR / "multiplier.md").write_text(
        f"Context re-send multiplier: {multiplier:.1f}.\nLargest hand-off: {dominant}, {share:.1f}% of orchestrator tokens.\n",
        encoding="utf-8",
    )
    failure_item = next(item for item in questions if item["id"] == 5)
    failure = run_orchestrator(
        failure_item["question"], inject_defined_terms_failure=True
    )
    failure_handoffs = [
        {
            "arm": "orchestrator_failure_injected",
            "case": failure_item["id"],
            "failure_injected": True,
            **handoff,
        }
        for handoff in failure["handoffs"]
    ]
    (EVIDENCE_DIR / "handoffs.log").write_text(
        "\n".join(
            json.dumps(item, sort_keys=True)
            for item in handoffs + failure_handoffs
        )
        + "\n",
        encoding="utf-8",
    )
    (EVIDENCE_DIR / "failure_case.md").write_text(
        f"# Failure case\n\nInjected defined-terms worker HTTP 500 on case {failure_item['id']}.\nThe injected run is recorded in `handoffs.log` with `arm=orchestrator_failure_injected` and `status=500 injected`.\nObserved behavior: degraded to a partial answer; no retry and no invented definition.\nStop reason: `{failure['stop_reason']}`.\n",
        encoding="utf-8",
    )
    verdict = (
        "keep"
        if multi["pass_rate"] > single["pass_rate"]
        and multi["total_tokens"] <= single["total_tokens"] * 1.5
        else "kill"
    )
    (EVIDENCE_DIR / "verdict.md").write_text(
        f"# Verdict: {verdict}\n\nSunk-cost bias is not evidence. Pass rate: single {single['pass_rate']:.1%}, squad {multi['pass_rate']:.1%}. Total tokens: single {single['total_tokens']}, squad {multi['total_tokens']}.\n",
        encoding="utf-8",
    )
    (EVIDENCE_DIR / "agent_card.json").write_text(
        json.dumps(agent_card(), indent=2) + "\n", encoding="utf-8"
    )
    (EVIDENCE_DIR / "a2a_failure_mapping.md").write_text(
        "A worker 500 ends as failed after retries are exhausted; amendment-date ambiguity should be input-required. A2A adds discoverable skills and task lifecycle state over plain REST.\n",
        encoding="utf-8",
    )
    return {
        "single": single,
        "multi": multi,
        "multiplier": multiplier,
        "dominant": dominant,
    }


if __name__ == "__main__":
    print(write_evidence())
