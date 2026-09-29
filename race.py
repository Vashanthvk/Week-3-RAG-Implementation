"""Task Set F required deliverable: race the agent against the fixed
workflow over the same 10 contract questions and report four comparable
numbers per system -- pass rate, p50 latency, total tokens, cost/question.

Running this file directly regenerates ALL of Week 7's automatable
evidence in one command, the same way trajectory_eval.py does for
Week 8: race.csv/race_details.csv/race_report.md, budget_termination_log.md,
and third_tool_diff.md. week7_evidence/verdict.md is deliberately left
alone -- its conclusion has the actual numbers written into the prose,
not just a table, so blindly overwriting it risks shipping a verdict that
contradicts a future run's data. Instead this script prints a consistency
check against verdict.md's existing claim.

Usage: python race.py
Writes: week7_evidence/race.csv, race_details.csv, race_report.md,
        budget_termination_log.md, third_tool_diff.md
"""

from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path
from time import monotonic

from agent_loops import LoopBudget, run_agent, run_fixed_workflow

QUESTIONS_PATH = Path(__file__).with_name("race_questions.json")
EVIDENCE_DIR = Path(__file__).with_name("week7_evidence")

THIRD_TOOL_DIFF = '''# Third tool: description diff

Task Set F requirement #1: add a third tool (`get_definitions`) whose
description names exactly one job, uses an enum for the contract-version
parameter, and does not overlap the two existing tool descriptions.

## Before (Week 6, two tools)

```python
TOOL_DESCRIPTIONS = {
    "retrieve_contract_evidence": "Retrieve and rank contract chunks for a legal question.",
    "draft_grounded_answer": "Draft an answer using only the retrieved contract evidence.",
}
```

## After (Week 7 / Task Set F, three tools)

```python
CONTRACT_VERSIONS = [
    "Employment_Agreement",
    "Lease_Agreement",
    "Non_Disclosure_Agreement",
    "Master_Service_Agreement",
    "Software_License_Agreement",
]

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
        "and does not draft an answer."
    ),
    "draft_grounded_answer": (
        "Compose the final answer strictly from clause evidence and/or "
        "defined-term lookups already gathered earlier in this run. Does "
        "not search or look anything up itself; call it last."
    ),
}
```

## Why there is no overlap

Each description states one job and explicitly disclaims the other two:

| Tool | Job | Explicitly does NOT do |
|---|---|---|
| `retrieve_contract_evidence` | broad search across every contract for relevant clauses | look up a defined term's meaning; draft an answer |
| `get_definitions` | resolve ONE named defined term inside ONE named contract | search broadly; draft an answer |
| `draft_grounded_answer` | compose the final answer from evidence already gathered | search; look anything up |

`get_definitions(term: str, contract_version: str)` takes a real enum
parameter, `contract_version`, restricted at call time to the five values in
`CONTRACT_VERSIONS` (`agent_loops.get_definitions` rejects anything else with
`{"found": False, "error": "unknown_contract_version"}` rather than silently
guessing a contract). This is what makes it a targeted, single-job lookup
tool rather than a second, narrower version of `retrieve_contract_evidence`:
it never ranks or searches chunks, it does a direct regex resolution of one
term's defining sentence inside one named contract's text.

*(Note: `TOOL_DESCRIPTIONS["get_definitions"]` gained one more sentence in
Week 8 as a trajectory-eval mitigation -- see week8_evidence/mitigation_diff.md
for that later change. This file documents Week 7's diff in isolation.)*
'''


def load_questions() -> list[dict]:
    with QUESTIONS_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def passes(answer: str, expected_keywords: list) -> bool:
    """expected_keywords is a list where each item is either a required
    substring, or a list of acceptable alternative substrings (OR-group).
    All items must be satisfied (AND) for the answer to pass."""

    answer_lower = (answer or "").lower()
    for item in expected_keywords:
        alternatives = item if isinstance(item, list) else [item]
        if not any(alt.lower() in answer_lower for alt in alternatives):
            return False
    return True


def run_system(name: str, runner, questions: list[dict]) -> tuple[dict, list[dict]]:
    rows = []
    for item in questions:
        started = monotonic()
        result = runner(item["question"])
        wall_clock = round(monotonic() - started, 4)
        ok = passes(result["answer"], item["expected_keywords"])
        rows.append({
            "system": name,
            "id": item["id"],
            "dependency": item["dependency"],
            "pass": ok,
            "latency_s": result.get("elapsed_seconds", wall_clock),
            "tokens": result.get("total_tokens", 0),
            "cost": result.get("estimated_cost", 0.0),
            "steps": result.get("steps", 0),
            "stop_reason": result.get("stop_reason", ""),
            "answer": result.get("answer", ""),
        })
        print(f"[{name}] Q{item['id']} pass={ok} steps={rows[-1]['steps']} "
              f"tokens={rows[-1]['tokens']} stop={rows[-1]['stop_reason']}")

    latencies = [row["latency_s"] for row in rows]
    summary = {
        "system": name,
        "pass_rate": round(sum(row["pass"] for row in rows) / len(rows), 4),
        "p50_latency_s": round(statistics.median(latencies), 4),
        "total_tokens": sum(row["tokens"] for row in rows),
        "cost_per_question": round(sum(row["cost"] for row in rows) / len(rows), 6),
    }
    return summary, rows


def generate_budget_termination_log(questions: list[dict]) -> None:
    # Q7 -- a dependency question, sourced from race_questions.json itself
    # (not a hardcoded duplicate) so this stays in sync if that file ever
    # changes.
    question = next(item["question"] for item in questions if item["id"] == 7)
    tight_budget = LoopBudget(max_steps=8, max_seconds=90.0, max_tokens=600, max_cost=0.045)
    result = run_agent(question, tight_budget)

    report = f"""# Budget-termination log

Task Set F requirement #4: all four budgets enforced in code
(`agent_loops.LoopBudget` / `_budget_exceeded`), plus a log of one run
that hits a budget and terminates cleanly instead of spinning.

## Which budget fired

`max_tokens`, deliberately set far below the loop's normal per-call
footprint (the ReAct prompt's tool descriptions + two worked few-shot
examples alone run ~850-900 tokens per call, before any transcript
history is added).

Question: {question}

Budget: max_steps={tight_budget.max_steps}, max_seconds={tight_budget.max_seconds}, max_tokens={tight_budget.max_tokens}, max_cost={tight_budget.max_cost}

## Result (clean termination, no exception, no further LLM calls)

```json
{{
  "answer": {result['answer']!r},
  "steps": {result['steps']},
  "tool_calls": {result['tool_calls']},
  "total_tokens": {result['total_tokens']},
  "estimated_cost": {result['estimated_cost']},
  "elapsed_seconds": {result['elapsed_seconds']},
  "stop_reason": {result['stop_reason']!r}
}}
```

No tool call happened (`tool_calls: {result['tool_calls']}`), the answer
is empty rather than fabricated, and the run returns a normal dict -- no
exception, no timeout, no infinite loop.

## All four budgets are checked on every iteration

`agent_loops._budget_exceeded(state, budget)` (called both before and
after every model call inside `run_agent`'s loop) checks, in order:

1. `max_steps` -- iteration count -> `stop_reason = "max_iterations"`
2. `max_seconds` -- wall-clock -> `stop_reason = "max_wall_clock"`
3. `max_tokens` -- cumulative real tokens -> `stop_reason = "max_tokens"` (demonstrated above)
4. `max_cost` -- cumulative notional cost derived from those same real tokens -> `stop_reason = "max_cost"`

`tests/test_agent_loops.py` (`AgentLoopBudgetTests`) covers all four
programmatically with a mocked model call, so each one is exercised
without depending on a live Ollama instance.
"""

    (EVIDENCE_DIR / "budget_termination_log.md").write_text(report, encoding="utf-8")
    print(f"Wrote budget_termination_log.md -- stop_reason={result['stop_reason']!r}, tool_calls={result['tool_calls']}")

    if result["stop_reason"] != "max_tokens" or result["tool_calls"] != 0:
        print(
            "WARNING: this run's stop_reason/tool_calls differ from the clean "
            "'stops before any tool call' demonstration this doc describes -- "
            "re-check the report text above before submitting."
        )


def generate_third_tool_diff() -> None:
    (EVIDENCE_DIR / "third_tool_diff.md").write_text(THIRD_TOOL_DIFF, encoding="utf-8")
    print("Wrote third_tool_diff.md")


def check_verdict_still_consistent(agent_summary: dict, fixed_summary: dict) -> None:
    verdict_path = EVIDENCE_DIR / "verdict.md"
    if not verdict_path.exists():
        print("\n(no verdict.md yet -- nothing to check)")
        return

    verdict_text = verdict_path.read_text(encoding="utf-8")
    claims_fixed_wins = "fixed workflow wins on all four numbers" in verdict_text.lower()
    fixed_really_wins = (
        fixed_summary["pass_rate"] >= agent_summary["pass_rate"]
        and fixed_summary["p50_latency_s"] <= agent_summary["p50_latency_s"]
        and fixed_summary["total_tokens"] <= agent_summary["total_tokens"]
        and fixed_summary["cost_per_question"] <= agent_summary["cost_per_question"]
    )

    print("\n--- verdict.md consistency check (NOT auto-edited) ---")
    print(f"This run: agent={agent_summary}, fixed_workflow={fixed_summary}")
    if claims_fixed_wins and fixed_really_wins:
        print("OK: verdict.md's 'fixed workflow wins on all four numbers' claim still matches this run.")
    else:
        print(
            "WARNING: verdict.md's claim may now be STALE relative to this run's "
            "numbers. Re-read week7_evidence/verdict.md by hand and update its "
            "prose (not just a table) if the conclusion no longer holds -- a "
            "verdict contradicting the table scores 0 per the rubric."
        )


def main() -> None:
    EVIDENCE_DIR.mkdir(exist_ok=True)
    questions = load_questions()

    agent_summary, agent_rows = run_system("agent", run_agent, questions)
    fixed_summary, fixed_rows = run_system("fixed_workflow", run_fixed_workflow, questions)

    summary_path = EVIDENCE_DIR / "race.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["system", "pass_rate", "p50_latency_s", "total_tokens", "cost_per_question"])
        writer.writeheader()
        writer.writerow(agent_summary)
        writer.writerow(fixed_summary)

    details_path = EVIDENCE_DIR / "race_details.csv"
    all_rows = agent_rows + fixed_rows
    with details_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)

    report_path = EVIDENCE_DIR / "race_report.md"
    lines = [
        "# Task Set F Race Report",
        "",
        "| system | pass_rate | p50_latency_s | total_tokens | cost_per_question |",
        "|---|---|---|---|---|",
        f"| agent | {agent_summary['pass_rate']} | {agent_summary['p50_latency_s']} | {agent_summary['total_tokens']} | {agent_summary['cost_per_question']} |",
        f"| fixed_workflow | {fixed_summary['pass_rate']} | {fixed_summary['p50_latency_s']} | {fixed_summary['total_tokens']} | {fixed_summary['cost_per_question']} |",
        "",
        "## Per-question detail",
        "",
        "| system | id | dependency | pass | latency_s | tokens | cost | steps | stop_reason |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in all_rows:
        lines.append(
            f"| {row['system']} | {row['id']} | {row['dependency']} | {row['pass']} | "
            f"{row['latency_s']} | {row['tokens']} | {row['cost']} | {row['steps']} | {row['stop_reason']} |"
        )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n" + "=" * 70)
    print("RACE SUMMARY")
    print("=" * 70)
    print(json.dumps({"agent": agent_summary, "fixed_workflow": fixed_summary}, indent=2))
    print(f"\nWrote {summary_path}, {details_path}, {report_path}")

    print("\n" + "=" * 70)
    print("BUDGET-TERMINATION LOG")
    print("=" * 70)
    generate_budget_termination_log(questions)

    print("\n" + "=" * 70)
    print("THIRD-TOOL DESCRIPTION DIFF (static)")
    print("=" * 70)
    generate_third_tool_diff()

    check_verdict_still_consistent(agent_summary, fixed_summary)

    print(
        "\nDone. verdict.md was intentionally NOT modified -- it's an "
        "interpreted conclusion, not raw data; see the consistency check above."
    )


if __name__ == "__main__":
    main()
