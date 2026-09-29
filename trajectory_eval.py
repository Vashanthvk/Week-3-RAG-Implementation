"""Week 8 Task Set F: trajectory evaluation for the contract agent.

Evaluates run_agent() (the real ReAct loop), not the fixed workflow -- the
fixed workflow's tool sequence is deterministic Python branching and can't
exhibit the failure modes this week is about (looping, wrong tool, made-up
defined terms, quietly refusing when evidence existed). Those only happen
when a model is actually choosing the next tool.

Running this file directly (no args) regenerates ALL of Week 8's
automatable evidence in one command: a fresh run against the CURRENT
(mitigated) code, written to trajectory_eval_after_mitigation.md/_raw.json
-- NOT to the baseline filenames, since agent_loops.py's one mitigation
(see week8_evidence/mitigation_diff.md) is now permanently in the live
code, so a default run here is always an "after" run, never a "before"
one. trajectory_eval_baseline.md/_raw.json stay as the originally
captured historical pre-mitigation run and are only ever read, never
rewritten, by this file.

mitigation_diff.md and regression_check.md both have their numbers
written directly into prose ("10/10 -> 10/10... ineffective"), not just a
table, so this script does not silently overwrite them -- overwriting
just the numbers without re-checking the surrounding sentences risks
shipping a document that contradicts itself. Instead every run prints a
consistency check against what those two files currently claim.

Usage:
    python trajectory_eval.py [--budget-max-steps N] [--out PATH] [--skip-consistency-checks]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from statistics import mean

from agent_loops import LoopBudget, run_agent
from race import passes as outcome_passes


BASE_DIR = Path(__file__).resolve().parent
# Same dataset file as race.py (Week 7) -- race_questions.json now carries
# the trajectory-specific fields (expected_paths, needed_steps,
# short_path_grounding_phrases) alongside race.py's own fields
# (expected_keywords, expected_source), so both weeks read one file
# instead of two near-duplicates that could drift apart.
QUESTIONS_PATH = BASE_DIR / "race_questions.json"
EVIDENCE_DIR = BASE_DIR / "week8_evidence"
BASELINE_RAW_PATH = EVIDENCE_DIR / "trajectory_eval_baseline_raw.json"
DEFAULT_REPORT_PATH = EVIDENCE_DIR / "trajectory_eval_after_mitigation.md"
DEFAULT_RAW_PATH = EVIDENCE_DIR / "trajectory_eval_after_mitigation_raw.json"
DEFAULT_TITLE = "Week 8 Trajectory Evaluation -- After Mitigation"

ALL_FAILURE_MODES = ["loop", "wrong_tool", "made_up_input", "silent_giveup", "inefficient_steps", "outcome_failure", "pass"]

LOOP_STOP_REASONS = {
    "max_iterations",
    "max_wall_clock",
    "max_tokens",
    "max_cost",
    "stuck_loop_forced_draft",
}


# ============================================================
# DATA LOADING
# ============================================================

def load_questions() -> list[dict]:
    with QUESTIONS_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


# ============================================================
# TRAJECTORY HELPERS
# ============================================================

def build_tool_sequence(events: list[dict]) -> list[str]:
    return [event["tool"] for event in events if event.get("phase") == "ACT" and event.get("tool")]


def count_tool_steps(events: list[dict]) -> int:
    return len(build_tool_sequence(events))


def _retrieve_observation_text(events: list[dict]) -> str:
    """The OBSERVE message logged right after the retrieve ACT event."""

    for index, event in enumerate(events):
        if event.get("phase") == "ACT" and event.get("tool") == "retrieve_contract_evidence":
            for later in events[index + 1:]:
                if later.get("phase") == "OBSERVE":
                    return str(later.get("message", ""))
    return ""


def _observe_messages_for_tool(events: list[dict], tool_name: str) -> list[str]:
    """The OBSERVE message logged right after each ACT event for this tool."""

    messages = []
    for index, event in enumerate(events):
        if event.get("phase") == "ACT" and event.get("tool") == tool_name:
            for later in events[index + 1:]:
                if later.get("phase") == "OBSERVE":
                    messages.append(str(later.get("message", "")))
                    break
    return messages


# ============================================================
# TOOL-CHOICE VALIDITY (a set of legitimate paths, not one)
# ============================================================

def evaluate_tool_choice(case: dict, events: list[dict]) -> tuple[bool, list[str]]:
    """Sequence membership against expected_paths (a SET, so legitimate
    alternates are accepted). The one exception: a case's *shortest* path
    that skips a required lookup is only legitimate if the answer was
    actually grounded in the raw evidence -- checked via
    short_path_grounding_phrases -- otherwise it is exactly the "right
    answer, wrong path" failure this week hunts, not a valid alternate.
    """

    actual = build_tool_sequence(events)
    expected_paths = case.get("expected_paths", [])

    if actual not in expected_paths:
        return False, actual

    grounding_phrases = case.get("short_path_grounding_phrases")
    if grounding_phrases and len(expected_paths) > 1:
        shortest = min(expected_paths, key=len)
        if actual == shortest and actual != max(expected_paths, key=len):
            retrieve_text = _retrieve_observation_text(events).lower()
            grounded = all(phrase.lower() in retrieve_text for phrase in grounding_phrases)
            return grounded, actual

    return True, actual


# ============================================================
# ARGUMENT VALIDITY -- were defined-term lookups real or fiction?
# ============================================================

def evaluate_argument_validity(events: list[dict]) -> tuple[bool, list[str]]:
    """For every get_definitions call in the trajectory, did the term
    argument resolve to something that actually exists in the contract
    (real), or did it come back not-found (fluent fiction)? A trajectory
    with zero get_definitions calls is vacuously valid -- there is nothing
    to fabricate."""

    fictional_terms = []
    for message in _observe_messages_for_tool(events, "get_definitions"):
        if "was not found as a defined term" in message:
            match = re.search(r"^'([^']*)'", message)
            fictional_terms.append(match.group(1) if match else message[:40])

    return (not fictional_terms), fictional_terms


# ============================================================
# STEP EFFICIENCY
# ============================================================

def calculate_step_efficiency(actual_steps: int, needed_steps: int) -> float:
    if needed_steps <= 0:
        return 0.0
    return round(actual_steps / needed_steps, 4)


# ============================================================
# COST METRICS -- p50 AND max, never the mean alone
# ============================================================

def _percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = percentile_value * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def calculate_cost_metrics(costs: list[float]) -> dict:
    return {
        "p50": round(_percentile(costs, 0.50), 6),
        "max": round(max(costs, default=0.0), 6),
    }


# ============================================================
# OUTCOME EVALUATION -- real correctness, not just "answered something"
# ============================================================

def outcome_passed(answer: str, case: dict) -> bool:
    expected_keywords = case.get("expected_keywords", [])
    if not expected_keywords:
        return bool(answer.strip())
    return outcome_passes(answer, expected_keywords)


# ============================================================
# FAILURE MODE CLASSIFICATION -- the Week-8 zoo
# ============================================================

def classify_failure(
    stop_reason: str,
    tool_choice_ok: bool,
    argument_ok: bool,
    outcome_ok: bool,
    answer: str,
    sources: list,
    actual_steps: int,
    needed_steps: int,
) -> str:
    if stop_reason in LOOP_STOP_REASONS:
        return "loop"
    if not tool_choice_ok:
        return "wrong_tool"
    if not argument_ok:
        return "made_up_input"
    if not outcome_ok and "i don't know" in answer.lower() and sources:
        return "silent_giveup"
    if actual_steps > needed_steps:
        return "inefficient_steps"
    if not outcome_ok:
        return "outcome_failure"
    return "pass"


# ============================================================
# SINGLE CASE EVALUATION
# ============================================================

def evaluate_case(case: dict, budget: LoopBudget | None = None) -> dict:
    result = run_agent(case["question"], budget)
    events = result.get("events", [])

    tool_choice_ok, actual_path = evaluate_tool_choice(case, events)
    argument_ok, fictional_terms = evaluate_argument_validity(events)

    actual_steps = count_tool_steps(events)
    needed_steps = int(case.get("needed_steps", 1))
    step_efficiency = calculate_step_efficiency(actual_steps, needed_steps)

    answer = result.get("answer", "")
    sources = result.get("sources", [])
    outcome_ok = outcome_passed(answer, case)

    failure_mode = classify_failure(
        result.get("stop_reason", ""),
        tool_choice_ok,
        argument_ok,
        outcome_ok,
        answer,
        sources,
        actual_steps,
        needed_steps,
    )

    return {
        "id": case["id"],
        "question": case["question"],
        "dependency": case.get("dependency", False),
        "expected_paths": case.get("expected_paths", []),
        "actual_path": actual_path,
        "tool_choice_valid": tool_choice_ok,
        "argument_valid": argument_ok,
        "fictional_terms": fictional_terms,
        "outcome_valid": outcome_ok,
        "steps": actual_steps,
        "needed_steps": needed_steps,
        "step_efficiency": step_efficiency,
        "tool_calls": result.get("tool_calls", 0),
        "total_tokens": result.get("total_tokens", 0),
        "estimated_cost": float(result.get("estimated_cost", 0.0)),
        "elapsed_seconds": float(result.get("elapsed_seconds", 0.0)),
        "stop_reason": result.get("stop_reason", ""),
        "answer": answer,
        "sources": sources,
        "failure_mode": failure_mode,
        "events": events,
    }


# ============================================================
# AGGREGATE METRICS
# ============================================================

def calculate_metrics(results: list[dict]) -> dict:
    total = len(results)
    if total == 0:
        return {
            "total": 0, "tool_choice_accuracy": 0.0, "argument_validity_rate": 0.0,
            "trajectory_pass_rate": 0.0, "outcome_pass_rate": 0.0,
            "outcome_trajectory_gap": 0.0, "step_efficiency": 0.0,
            "cost_p50": 0.0, "cost_max": 0.0,
        }

    tool_choice_accuracy = sum(r["tool_choice_valid"] for r in results) / total
    argument_validity_rate = sum(r["argument_valid"] for r in results) / total
    trajectory_pass_rate = sum(r["tool_choice_valid"] and r["argument_valid"] for r in results) / total
    outcome_pass_rate = sum(r["outcome_valid"] for r in results) / total
    average_step_efficiency = mean(r["step_efficiency"] for r in results)
    cost_metrics = calculate_cost_metrics([r["estimated_cost"] for r in results])
    gap = outcome_pass_rate - trajectory_pass_rate

    return {
        "total": total,
        "tool_choice_accuracy": round(tool_choice_accuracy, 4),
        "argument_validity_rate": round(argument_validity_rate, 4),
        "trajectory_pass_rate": round(trajectory_pass_rate, 4),
        "outcome_pass_rate": round(outcome_pass_rate, 4),
        "outcome_trajectory_gap": round(gap, 4),
        "step_efficiency": round(average_step_efficiency, 4),
        "cost_p50": cost_metrics["p50"],
        "cost_max": cost_metrics["max"],
    }


def failure_mode_counts(results: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for result in results:
        mode = result["failure_mode"]
        counts[mode] = counts.get(mode, 0) + 1
    return counts


# ============================================================
# MARKDOWN REPORT
# ============================================================

def format_percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def build_markdown_report(results: list[dict], metrics: dict, title: str) -> str:
    lines = [f"# {title}", "", "## Summary", ""]
    lines.append(f"- Cases evaluated: {metrics['total']}")
    lines.append(f"- Tool-choice accuracy: {format_percent(metrics['tool_choice_accuracy'])}")
    lines.append(f"- Argument validity rate: {format_percent(metrics['argument_validity_rate'])}")
    lines.append(f"- Trajectory pass rate (tool-choice AND argument valid): {format_percent(metrics['trajectory_pass_rate'])}")
    lines.append(f"- Outcome pass rate: {format_percent(metrics['outcome_pass_rate'])}")
    lines.append(f"- **Outcome-vs-trajectory gap: {format_percent(metrics['outcome_trajectory_gap'])}**")
    lines.append(f"- Average step efficiency (steps taken / steps needed): {metrics['step_efficiency']:.2f}")
    lines.append(f"- Cost per question -- p50: ${metrics['cost_p50']:.6f}")
    lines.append(f"- Cost per question -- max: ${metrics['cost_max']:.6f}")
    lines.append("")

    lines.append("## Per-case results")
    lines.append("")
    lines.append("| ID | Dep? | Tool Path | Actual Path | Args | Outcome | Steps | Needed | Eff. | Cost | Mode |")
    lines.append("|---|---|---|---|---|---|---:|---:|---:|---:|---|")
    for r in results:
        lines.append(
            f"| {r['id']} | {'Y' if r['dependency'] else ''} | "
            f"{'PASS' if r['tool_choice_valid'] else 'FAIL'} | "
            f"{' -> '.join(r['actual_path']) or '(none)'} | "
            f"{'PASS' if r['argument_valid'] else 'FAIL'} | "
            f"{'PASS' if r['outcome_valid'] else 'FAIL'} | "
            f"{r['steps']} | {r['needed_steps']} | {r['step_efficiency']:.2f} | "
            f"${r['estimated_cost']:.6f} | {r['failure_mode']} |"
        )
    lines.append("")

    lines.append("## Failure mode counts")
    lines.append("")
    counts = failure_mode_counts(results)
    lines.append("| Mode | Count |")
    lines.append("|---|---:|")
    for mode, count in sorted(counts.items()):
        lines.append(f"| {mode} | {count} |")
    lines.append("")

    lines.append("## Outcome-vs-trajectory example (right answer, wrong path)")
    lines.append("")
    gap_cases = [r for r in results if r["outcome_valid"] and not (r["tool_choice_valid"] and r["argument_valid"])]
    if gap_cases:
        example = gap_cases[0]
        lines.append(f"**{example['id']}**")
        lines.append("")
        lines.append(f"Question: {example['question']}")
        lines.append("")
        lines.append("Outcome: PASS")
        lines.append("")
        lines.append(f"Trajectory: FAIL ({example['failure_mode']})")
        lines.append("")
        lines.append("Expected path(s):")
        lines.append("")
        lines.append("```text")
        for path in example["expected_paths"]:
            lines.append(" -> ".join(path))
        lines.append("```")
        lines.append("")
        lines.append("Actual path:")
        lines.append("")
        lines.append("```text")
        lines.append(" -> ".join(example["actual_path"]) or "(none)")
        lines.append("```")
        if example["fictional_terms"]:
            lines.append("")
            lines.append(f"Fictional term(s) requested: {example['fictional_terms']}")
        lines.append("")
        lines.append(f"Final answer: {example['answer']}")
    else:
        lines.append("No outcome-pass / trajectory-fail case was observed in this run.")
    lines.append("")

    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================

def run_evaluation(budget: LoopBudget | None = None) -> tuple[list[dict], dict]:
    questions = load_questions()
    if len(questions) != 10:
        raise ValueError("race_questions.json must contain exactly 10 cases.")

    results = []
    for case in questions:
        print(f"\n{'=' * 70}\nEvaluating {case['id']}: {case['question']}\n{'=' * 70}")
        result = evaluate_case(case, budget)
        results.append(result)
        print(f"Actual path: {result['actual_path']}")
        print(f"Tool choice: {'PASS' if result['tool_choice_valid'] else 'FAIL'}")
        print(f"Arguments:   {'PASS' if result['argument_valid'] else 'FAIL'}")
        print(f"Outcome:     {'PASS' if result['outcome_valid'] else 'FAIL'}")
        print(f"Failure mode: {result['failure_mode']}")
        print(f"Cost: ${result['estimated_cost']:.6f}  Tokens: {result['total_tokens']}")

    metrics = calculate_metrics(results)
    return results, metrics


def load_baseline_results() -> list[dict] | None:
    if not BASELINE_RAW_PATH.exists():
        return None
    return json.loads(BASELINE_RAW_PATH.read_text(encoding="utf-8"))["results"]


def check_regression_check_consistency(baseline_results: list[dict], after_results: list[dict]) -> None:
    baseline_counts = failure_mode_counts(baseline_results)
    after_counts = failure_mode_counts(after_results)

    print("\n--- regression_check.md consistency check (NOT auto-edited) ---")
    print(f"Baseline (frozen):     {dict(sorted(baseline_counts.items()))}")
    print(f"After (this run):      {dict(sorted(after_counts.items()))}")

    worsened = [m for m in ALL_FAILURE_MODES if after_counts.get(m, 0) > baseline_counts.get(m, 0)]
    new_modes = [m for m in ALL_FAILURE_MODES if baseline_counts.get(m, 0) == 0 and after_counts.get(m, 0) > 0]

    if not worsened and not new_modes:
        print("OK: no mode worsened, no new mode appeared -- matches regression_check.md's existing claim.")
    else:
        print(
            f"WARNING: this run differs from the frozen baseline -- "
            f"worsened modes: {worsened or 'none'}, new modes: {new_modes or 'none'}. "
            "regression_check.md's prose currently claims no regression; "
            "re-read and update it by hand if that's no longer accurate."
        )


def check_mitigation_diff_consistency(baseline_results: list[dict], after_results: list[dict]) -> None:
    baseline_loop = failure_mode_counts(baseline_results).get("loop", 0)
    after_loop = failure_mode_counts(after_results).get("loop", 0)

    b_tokens = sum(r["total_tokens"] for r in baseline_results)
    a_tokens = sum(r["total_tokens"] for r in after_results)
    b_cost = mean(r["estimated_cost"] for r in baseline_results)
    a_cost = mean(r["estimated_cost"] for r in after_results)

    print("\n--- mitigation_diff.md consistency check (NOT auto-edited) ---")
    print(f"loop count: {baseline_loop}/{len(baseline_results)} -> {after_loop}/{len(after_results)}")
    print(f"total tokens: {b_tokens:,} -> {a_tokens:,} (delta {a_tokens - b_tokens:+,})")
    print(f"mean cost/question: ${b_cost:.6f} -> ${a_cost:.6f} (delta ${a_cost - b_cost:+.6f})")

    diff_path = EVIDENCE_DIR / "mitigation_diff.md"
    if not diff_path.exists():
        print("(no mitigation_diff.md yet -- nothing to check)")
        return

    diff_text = diff_path.read_text(encoding="utf-8")
    match = re.search(r"\*\*`loop` failure count: (\d+)/\d+ -> (\d+)/\d+", diff_text)
    if match:
        documented_before, documented_after = int(match.group(1)), int(match.group(2))
        if documented_before == baseline_loop and documented_after == after_loop:
            print("OK: mitigation_diff.md's documented loop count still matches this run.")
        else:
            print(
                f"WARNING: mitigation_diff.md says loop count went "
                f"{documented_before}/10 -> {documented_after}/10, but this run "
                f"shows {baseline_loop}/10 -> {after_loop}/10. Re-read and "
                "update mitigation_diff.md's prose by hand -- its conclusion "
                "('applied, measured, ineffective') may no longer hold."
            )
    else:
        print("Could not find the documented loop-count line in mitigation_diff.md to compare against.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget-max-steps", type=int, default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--raw-out", type=Path, default=DEFAULT_RAW_PATH)
    parser.add_argument("--title", type=str, default=DEFAULT_TITLE)
    parser.add_argument("--skip-consistency-checks", action="store_true")
    args = parser.parse_args()

    budget = LoopBudget(max_steps=args.budget_max_steps) if args.budget_max_steps else None

    results, metrics = run_evaluation(budget)

    args.out.parent.mkdir(exist_ok=True)
    report = build_markdown_report(results, metrics, args.title)
    args.out.write_text(report, encoding="utf-8")

    args.raw_out.parent.mkdir(exist_ok=True)
    args.raw_out.write_text(json.dumps({"results": results, "metrics": metrics}, indent=2), encoding="utf-8")

    print(f"\n{'=' * 70}\nSUMMARY\n{'=' * 70}")
    print(json.dumps(metrics, indent=2))
    print(f"\nFailure modes: {json.dumps(failure_mode_counts(results), indent=2)}")
    print(f"\nReport: {args.out}")
    print(f"Raw data: {args.raw_out}")

    if not args.skip_consistency_checks:
        baseline_results = load_baseline_results()
        if baseline_results is None:
            print("\n(no trajectory_eval_baseline_raw.json found -- skipping consistency checks)")
        else:
            check_regression_check_consistency(baseline_results, results)
            check_mitigation_diff_consistency(baseline_results, results)
            print(
                "\nDone. mitigation_diff.md and regression_check.md were "
                "intentionally NOT modified -- their numbers are written into "
                "prose, not just a table; see the consistency checks above and "
                "update by hand if either warned."
            )


if __name__ == "__main__":
    main()
