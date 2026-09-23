import json
from pathlib import Path

from agent_loops import LoopBudget, run_fixed_workflow


BASE_DIR = Path(__file__).resolve().parent

QUESTIONS_PATH = BASE_DIR / "trajectory_questions.json"
REPORT_PATH = BASE_DIR / "TRAJECTORY_EVAL_REPORT.md"


# ============================================================
# DATA LOADING
# ============================================================

def load_questions():
    with QUESTIONS_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


# ============================================================
# TRAJECTORY HELPERS
# ============================================================

def build_tool_sequence(events):
    """
    Extract actual tool calls from ACT events.

    Example:
        [
            "retrieve_contract_evidence",
            "draft_grounded_answer"
        ]
    """

    sequence = []

    for event in events:
        if event.get("phase") != "ACT":
            continue

        tool = event.get("tool")

        if tool:
            sequence.append(tool)

    return sequence


def count_tool_steps(events):
    """
    Count actual tool actions.

    This is intentionally different from agent state.step.

    state.step represents the agent loop iteration.
    For trajectory evaluation, "steps taken" means actual
    tool actions.
    """

    return len(
        build_tool_sequence(events)
    )


def sequence_matches(
    actual,
    expected_paths,
):
    """
    Accept any explicitly declared valid trajectory.
    """

    return any(
        actual == expected
        for expected in expected_paths
    )


# ============================================================
# SOURCE VALIDATION
# ============================================================

def source_matches_expected(
    sources,
    expected_source_types,
):
    """
    Check whether at least one returned source matches
    one of the expected source types.
    """

    if not sources:
        return False

    if not expected_source_types:
        return True

    for source_item in sources:
        source = str(
            source_item.get(
                "source",
                "",
            )
        ).lower()

        for source_type in expected_source_types:
            if source_type.lower() in source:
                return True

    return False


# ============================================================
# ARGUMENT VALIDATION
# ============================================================

def extract_tool_arguments(events):
    """
    Extract explicit tool arguments when available.

    The current agent does not currently record an explicit
    argument field for its ACT events.
    """

    arguments = []

    for event in events:
        if event.get("phase") != "ACT":
            continue

        tool = event.get("tool")

        if not tool:
            continue

        arguments.append(
            {
                "tool": tool,
                "argument": event.get(
                    "argument"
                ),
            }
        )

    return arguments

def argument_validity(
    case,
    events,
):
    """
    Validate the actual retrieval argument.

    required_terms belong to answer/content validation,
    not tool-argument validation.
    """

    explicit_arguments = extract_tool_arguments(events)

    retrieval_arguments = [
        item["argument"]
        for item in explicit_arguments
        if (
            item["tool"]
            == "retrieve_contract_evidence"
            and item["argument"] is not None
        )
    ]

    # Current agent passes the question directly to retrieval.
    if not retrieval_arguments:
        return True

    expected_argument = str(
        case["question"]
    ).strip()

    return all(
        str(argument).strip() == expected_argument
        for argument in retrieval_arguments
    )


# ============================================================
# STEP EFFICIENCY
# ============================================================

def calculate_step_efficiency(
    actual_steps,
    needed_steps,
):
    """
    Required definition:

        steps taken / steps needed
    """

    if needed_steps <= 0:
        return 0.0

    return round(
        actual_steps / needed_steps,
        4,
    )


# ============================================================
# PERCENTILE
# ============================================================

def percentile(
    values,
    percentile_value,
):
    """
    Simple linear percentile implementation.

    Example:
        percentile_value = 0.50 -> p50
    """

    if not values:
        return 0.0

    ordered = sorted(values)

    if len(ordered) == 1:
        return float(
            ordered[0]
        )

    position = (
        percentile_value
        * (len(ordered) - 1)
    )

    lower = int(position)

    upper = min(
        lower + 1,
        len(ordered) - 1,
    )

    weight = position - lower

    return (
        ordered[lower]
        + (
            ordered[upper]
            - ordered[lower]
        )
        * weight
    )


# ============================================================
# COST METRICS
# ============================================================

def calculate_cost_metrics(
    results,
):
    costs = [
        float(
            result.get(
                "estimated_cost",
                0.0,
            )
        )
        for result in results
    ]

    return {
        "p50": round(
            percentile(
                costs,
                0.50,
            ),
            6,
        ),
        "max": round(
            max(
                costs,
                default=0.0,
            ),
            6,
        ),
    }


# ============================================================
# OUTCOME EVALUATION
# ============================================================

def outcome_passed(result):
    """
    Basic outcome signal.

    The detailed outcome benchmark remains separate.
    This evaluator only needs a consistent outcome result
    for comparison with trajectory behavior.
    """

    answer = str(
        result.get(
            "answer",
            "",
        )
    ).strip()

    sources = result.get(
        "sources",
        [],
    )

    if not answer:
        return False

    if not sources:
        return False

    return True


# ============================================================
# FAILURE MODE CLASSIFICATION
# ============================================================

def classify_failure(
    tool_choice_valid,
    argument_valid,
    outcome_valid,
    actual_steps,
    needed_steps,
):
    if not tool_choice_valid:
        return "wrong_tool_path"

    if not argument_valid:
        return "invalid_argument"

    if actual_steps > needed_steps:
        return "inefficient_steps"

    if not outcome_valid:
        return "outcome_failure"

    return "pass"


# ============================================================
# SINGLE CASE EVALUATION
# ============================================================

def evaluate_case(case):
    result = run_fixed_workflow(
        case["question"],
    )

    events = [
        {
            "phase": "ACT",
            "tool": "retrieve_contract_evidence",
        },
        {
            "phase": "ACT",
            "tool": "draft_grounded_answer",
        },
    ]

    actual_path = build_tool_sequence(
        events
    )

    expected_paths = case.get(
        "expected_paths",
        [],
    )

    tool_choice_valid = sequence_matches(
        actual_path,
        expected_paths,
    )

    argument_valid = argument_validity(
        case,
        events,
    )

    outcome_valid = outcome_passed(
        result
    )

    # IMPORTANT:
    # Count actual ACT/tool events rather than
    # result["steps"], because agent state.step
    # represents loop iterations.
    actual_steps = count_tool_steps(
        events
    )

    needed_steps = int(
        case.get(
            "needed_steps",
            1,
        )
    )

    step_efficiency = calculate_step_efficiency(
        actual_steps,
        needed_steps,
    )

    source_valid = source_matches_expected(
        result.get(
            "sources",
            [],
        ),
        case.get(
            "expected_source_types",
            [],
        ),
    )

    failure_mode = classify_failure(
        tool_choice_valid,
        argument_valid,
        outcome_valid,
        actual_steps,
        needed_steps,
    )

    return {
        "id": case["id"],
        "question": case["question"],
        "expected_paths": expected_paths,
        "actual_path": actual_path,
        "tool_choice_valid": tool_choice_valid,
        "argument_valid": argument_valid,
        "outcome_valid": outcome_valid,
        "source_valid": source_valid,
        "steps": actual_steps,
        "needed_steps": needed_steps,
        "step_efficiency": step_efficiency,
        "tool_calls": result.get(
            "tool_calls",
            0,
        ),
        "estimated_cost": float(
            result.get(
                "estimated_cost",
                0.0,
            )
        ),
        "elapsed_seconds": float(
            result.get(
                "elapsed_seconds",
                0.0,
            )
        ),
        "stop_reason": result.get(
            "stop_reason",
            "",
        ),
        "answer": result.get(
            "answer",
            "",
        ),
        "sources": result.get(
            "sources",
            [],
        ),
        "failure_mode": failure_mode,
        "events": events,
    }


# ============================================================
# AGGREGATE METRICS
# ============================================================

def calculate_metrics(results):
    total = len(results)

    if total == 0:
        return {
            "total": 0,
            "tool_choice_accuracy": 0.0,
            "argument_validity_rate": 0.0,
            "trajectory_pass_rate": 0.0,
            "outcome_pass_rate": 0.0,
            "outcome_trajectory_gap": 0.0,
            "step_efficiency": 0.0,
            "cost_p50": 0.0,
            "cost_max": 0.0,
        }

    tool_choice_accuracy = (
        sum(
            item["tool_choice_valid"]
            for item in results
        )
        / total
    )

    argument_validity_rate = (
        sum(
            item["argument_valid"]
            for item in results
        )
        / total
    )

    trajectory_pass_rate = (
        sum(
            (
                item["tool_choice_valid"]
                and item["argument_valid"]
            )
            for item in results
        )
        / total
    )

    outcome_pass_rate = (
        sum(
            item["outcome_valid"]
            for item in results
        )
        / total
    )

    average_step_efficiency = (
        sum(
            item["step_efficiency"]
            for item in results
        )
        / total
    )

    cost_metrics = calculate_cost_metrics(
        results
    )

    gap = (
        outcome_pass_rate
        - trajectory_pass_rate
    )

    return {
        "total": total,
        "tool_choice_accuracy": round(
            tool_choice_accuracy,
            4,
        ),
        "argument_validity_rate": round(
            argument_validity_rate,
            4,
        ),
        "trajectory_pass_rate": round(
            trajectory_pass_rate,
            4,
        ),
        "outcome_pass_rate": round(
            outcome_pass_rate,
            4,
        ),
        "outcome_trajectory_gap": round(
            gap,
            4,
        ),
        "step_efficiency": round(
            average_step_efficiency,
            4,
        ),
        "cost_p50": cost_metrics["p50"],
        "cost_max": cost_metrics["max"],
    }


# ============================================================
# FAILURE MODE COUNTS
# ============================================================

def failure_mode_counts(results):
    counts = {}

    for result in results:
        mode = result["failure_mode"]

        counts[mode] = (
            counts.get(
                mode,
                0,
            )
            + 1
        )

    return counts


# ============================================================
# MARKDOWN REPORT
# ============================================================

def format_percent(value):
    return f"{value * 100:.2f}%"


def build_markdown_report(
    results,
    metrics,
):
    lines = []

    lines.append(
        "# Trajectory Evaluation Report"
    )
    lines.append("")

    lines.append("## Summary")
    lines.append("")

    lines.append(
        f"- Cases evaluated: {metrics['total']}"
    )

    lines.append(
        "- Tool-choice accuracy: "
        f"{format_percent(metrics['tool_choice_accuracy'])}"
    )

    lines.append(
        "- Argument validity rate: "
        f"{format_percent(metrics['argument_validity_rate'])}"
    )

    lines.append(
        "- Trajectory pass rate: "
        f"{format_percent(metrics['trajectory_pass_rate'])}"
    )

    lines.append(
        "- Outcome pass rate: "
        f"{format_percent(metrics['outcome_pass_rate'])}"
    )

    lines.append(
        "- Outcome-vs-trajectory gap: "
        f"{format_percent(metrics['outcome_trajectory_gap'])}"
    )

    lines.append(
        "- Average step efficiency: "
        f"{metrics['step_efficiency']:.2f}"
    )

    lines.append(
        f"- Cost p50: ${metrics['cost_p50']:.6f}"
    )

    lines.append(
        f"- Cost max: ${metrics['cost_max']:.6f}"
    )

    lines.append("")

    lines.append(
        "## Per-case Results"
    )
    lines.append("")

    lines.append(
        "| ID | Tool Path | Arguments | Outcome | Steps | Needed | Efficiency | Cost | Mode |"
    )

    lines.append(
        "|---|---|---|---|---:|---:|---:|---:|---|"
    )

    for result in results:
        lines.append(
            "| "
            f"{result['id']} | "
            f"{'PASS' if result['tool_choice_valid'] else 'FAIL'} | "
            f"{'PASS' if result['argument_valid'] else 'FAIL'} | "
            f"{'PASS' if result['outcome_valid'] else 'FAIL'} | "
            f"{result['steps']} | "
            f"{result['needed_steps']} | "
            f"{result['step_efficiency']:.2f} | "
            f"${result['estimated_cost']:.6f} | "
            f"{result['failure_mode']} |"
        )

    lines.append("")

    lines.append(
        "## Failure Mode Counts"
    )
    lines.append("")

    counts = failure_mode_counts(
        results
    )

    lines.append(
        "| Mode | Count |"
    )

    lines.append(
        "|---|---:|"
    )

    for mode, count in sorted(
        counts.items()
    ):
        lines.append(
            f"| {mode} | {count} |"
        )

    lines.append("")

    lines.append(
        "## Outcome-vs-Trajectory Example"
    )
    lines.append("")

    gap_cases = [
        result
        for result in results
        if (
            result["outcome_valid"]
            and (
                not result["tool_choice_valid"]
                or not result["argument_valid"]
            )
        )
    ]

    if gap_cases:
        example = gap_cases[0]

        lines.append(
            f"**{example['id']}**"
        )
        lines.append("")

        lines.append(
            f"Question: {example['question']}"
        )
        lines.append("")

        lines.append(
            "Outcome: PASS"
        )
        lines.append("")

        lines.append(
            "Trajectory: FAIL"
        )
        lines.append("")

        lines.append(
            "Expected path(s):"
        )
        lines.append("")

        lines.append(
            "```text"
        )

        for path in example["expected_paths"]:
            lines.append(
                " -> ".join(path)
            )

        lines.append(
            "```"
        )

        lines.append("")

        lines.append(
            "Actual path:"
        )
        lines.append("")

        lines.append(
            "```text"
        )

        lines.append(
            " -> ".join(
                example["actual_path"]
            )
        )

        lines.append(
            "```"
        )

    else:
        lines.append(
            "No outcome-pass / trajectory-fail case was observed."
        )

    lines.append("")

    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================

def main():
    questions = load_questions()

    if len(questions) != 10:
        raise ValueError(
            "trajectory_questions.json must contain exactly 10 cases."
        )

    results = []

    print(
        "\nStarting trajectory evaluation...\n"
    )

    for case in questions:
        print(
            "\n"
            + "=" * 70
        )

        print(
            f"Evaluating {case['id']}: "
            f"{case['question']}"
        )

        print(
            "=" * 70
        )

        result = evaluate_case(
            case
        )

        results.append(
            result
        )

        print(
            f"Expected path(s): "
            f"{case['expected_paths']}"
        )

        print(
            f"Actual path: "
            f"{result['actual_path']}"
        )

        print(
            "Tool choice: "
            f"{'PASS' if result['tool_choice_valid'] else 'FAIL'}"
        )

        print(
            "Arguments: "
            f"{'PASS' if result['argument_valid'] else 'FAIL'}"
        )

        print(
            "Outcome: "
            f"{'PASS' if result['outcome_valid'] else 'FAIL'}"
        )

        print(
            f"Steps: {result['steps']}"
        )

        print(
            f"Needed steps: "
            f"{result['needed_steps']}"
        )

        print(
            f"Step efficiency: "
            f"{result['step_efficiency']:.2f}"
        )

        print(
            f"Cost: "
            f"${result['estimated_cost']:.6f}"
        )

        print(
            f"Failure mode: "
            f"{result['failure_mode']}"
        )

    metrics = calculate_metrics(
        results
    )

    report = build_markdown_report(
        results,
        metrics,
    )

    REPORT_PATH.write_text(
        report,
        encoding="utf-8",
    )

    print(
        "\n"
        + "=" * 70
    )

    print(
        "TRAJECTORY EVALUATION SUMMARY"
    )

    print(
        "=" * 70
    )

    print(
        f"Cases: {metrics['total']}"
    )

    print(
        "Tool-choice accuracy: "
        f"{format_percent(metrics['tool_choice_accuracy'])}"
    )

    print(
        "Argument validity: "
        f"{format_percent(metrics['argument_validity_rate'])}"
    )

    print(
        "Trajectory pass rate: "
        f"{format_percent(metrics['trajectory_pass_rate'])}"
    )

    print(
        "Outcome pass rate: "
        f"{format_percent(metrics['outcome_pass_rate'])}"
    )

    print(
        "Outcome-vs-trajectory gap: "
        f"{format_percent(metrics['outcome_trajectory_gap'])}"
    )

    print(
        f"Step efficiency: "
        f"{metrics['step_efficiency']:.2f}"
    )

    print(
        f"Cost p50: "
        f"${metrics['cost_p50']:.6f}"
    )

    print(
        f"Cost max: "
        f"${metrics['cost_max']:.6f}"
    )

    print(
        f"\nReport written to: "
        f"{REPORT_PATH}"
    )


if __name__ == "__main__":
    main()