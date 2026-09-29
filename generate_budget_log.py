"""Generate a budget-termination log report across the full race question
set (race_questions.json), under a deliberately tight LoopBudget, so every
question's stop_reason and event trail can be inspected at once.

Usage:
    python generate_budget_log.py
    python generate_budget_log.py --max-tokens 600 --max-steps 8 --out week7_evidence/budget_termination_log_race_questions.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_loops import LoopBudget, run_agent

QUESTIONS_PATH = Path(__file__).with_name("race_questions.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--max-seconds", type=float, default=90.0)
    parser.add_argument("--max-tokens", type=int, default=600)
    parser.add_argument("--max-cost", type=float, default=0.045)
    parser.add_argument("--out", type=Path, default=Path("week7_evidence/budget_termination_log_race_questions.md"))
    parser.add_argument("--raw-out", type=Path, default=Path("week7_evidence/budget_termination_log_race_questions_raw.json"))
    args = parser.parse_args()

    budget = LoopBudget(
        max_steps=args.max_steps,
        max_seconds=args.max_seconds,
        max_tokens=args.max_tokens,
        max_cost=args.max_cost,
    )

    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    rows = []

    for item in questions:
        print(f"\n{'=' * 70}\nQ{item['id']}: {item['question']}\n{'=' * 70}")
        result = run_agent(item["question"], budget)
        rows.append({
            "id": item["id"],
            "dependency": item.get("dependency", False),
            "question": item["question"],
            "stop_reason": result["stop_reason"],
            "steps": result["steps"],
            "tool_calls": result["tool_calls"],
            "total_tokens": result["total_tokens"],
            "estimated_cost": result["estimated_cost"],
            "elapsed_seconds": result["elapsed_seconds"],
            "answer": result["answer"],
            "events": result["events"],
        })
        print(f"stop_reason={result['stop_reason']} steps={result['steps']} tokens={result['total_tokens']}")

    args.raw_out.parent.mkdir(exist_ok=True)
    args.raw_out.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    lines = [
        "# Budget-termination log across the race question set",
        "",
        f"Budget used for every question: max_steps={budget.max_steps}, "
        f"max_seconds={budget.max_seconds}, max_tokens={budget.max_tokens}, "
        f"max_cost={budget.max_cost}",
        "",
        "| ID | Dep? | Stop reason | Steps | Tool calls | Tokens | Cost | Answer |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        answer_preview = (row["answer"][:60] + "...") if len(row["answer"]) > 60 else (row["answer"] or "(empty)")
        lines.append(
            f"| {row['id']} | {'Y' if row['dependency'] else ''} | {row['stop_reason']} | "
            f"{row['steps']} | {row['tool_calls']} | {row['total_tokens']} | "
            f"${row['estimated_cost']:.6f} | {answer_preview} |"
        )

    stop_reason_counts: dict[str, int] = {}
    for row in rows:
        stop_reason_counts[row["stop_reason"]] = stop_reason_counts.get(row["stop_reason"], 0) + 1

    lines += ["", "## Stop reason counts", "", "| Stop reason | Count |", "|---|---:|"]
    for reason, count in sorted(stop_reason_counts.items()):
        lines.append(f"| {reason} | {count} |")

    args.out.parent.mkdir(exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nWrote {args.out}")
    print(f"Wrote {args.raw_out}")
    print(json.dumps(stop_reason_counts, indent=2))


if __name__ == "__main__":
    main()
