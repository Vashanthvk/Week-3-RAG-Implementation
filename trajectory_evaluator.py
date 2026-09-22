"""
Trajectory and efficiency evaluation for the existing legal-contract agent.

This module is intentionally read-only with respect to agent_loops.py.
It evaluates AgentState.events / returned metrics and does not change the
agent's retrieval, prompting, or tool implementation.
"""

from __future__ import annotations

import math
from statistics import mean
from typing import Any, Dict, Iterable, List, Sequence


ALLOWED_TOOLS = {
    "retrieve_contract_evidence",
    "draft_grounded_answer",
}


def _tool_events(events: Sequence[Dict[str, Any]]) -> List[str]:
    return [
        str(event.get("tool"))
        for event in events
        if event.get("phase") == "ACT" and event.get("tool")
    ]


def _trajectory_flags(
    events: Sequence[Dict[str, Any]]
) -> Dict[str, Any]:

    tools = _tool_events(events)
    violations: List[str] = []

    unknown_tools = [
        tool
        for tool in tools
        if tool not in ALLOWED_TOOLS
    ]

    if unknown_tools:
        violations.append("unknown_tool")

    retrieve_positions = [
        i
        for i, tool in enumerate(tools)
        if tool == "retrieve_contract_evidence"
    ]

    draft_positions = [
        i
        for i, tool in enumerate(tools)
        if tool == "draft_grounded_answer"
    ]

    # Drafting requires retrieval first.
    if draft_positions and not retrieve_positions:
        violations.append("draft_before_retrieval")

    elif (
        draft_positions
        and min(draft_positions) < min(retrieve_positions)
    ):
        violations.append("draft_before_retrieval")

    # Agent allows only one retry, therefore max 2 retrieval calls.
    if len(retrieve_positions) > 2:
        violations.append("excessive_retrieval")

    # No retrieval after drafting.
    if draft_positions:
        first_draft = min(draft_positions)

        if any(
            position > first_draft
            for position in retrieve_positions
        ):
            violations.append("tool_after_draft")

    return {
        "tools": tools,
        "violations": violations,
        "valid": not violations and bool(tools),
    }


def evaluate_trajectory(
    events: Sequence[Dict[str, Any]]
) -> Dict[str, Any]:

    """
    Evaluate one agent trajectory.
    """

    flags = _trajectory_flags(events)

    tools = flags["tools"]

    if tools == [
        "retrieve_contract_evidence",
        "draft_grounded_answer",
    ]:
        trajectory_type = "retrieve_then_draft"

    elif tools == [
        "retrieve_contract_evidence",
        "retrieve_contract_evidence",
    ]:
        trajectory_type = "bounded_retry_refusal"

    elif not tools:
        trajectory_type = "no_tool_call"

    else:
        trajectory_type = "other"

    return {
        "trajectory_type": trajectory_type,
        "tool_sequence": tools,
        "trajectory_valid": flags["valid"],
        "violations": flags["violations"],
    }


def _percentile(
    values: Iterable[float],
    percentile: float
) -> float:

    data = sorted(float(value) for value in values)

    if not data:
        return 0.0

    if len(data) == 1:
        return data[0]

    rank = (len(data) - 1) * percentile

    lower = math.floor(rank)
    upper = math.ceil(rank)

    if lower == upper:
        return data[lower]

    weight = rank - lower

    return (
        data[lower]
        + (data[upper] - data[lower]) * weight
    )


def evaluate_runs(
    runs: Sequence[Dict[str, Any]]
) -> Dict[str, Any]:

    """
    Evaluate completed agent runs.

    Expected run fields:

        {
            "agent": {
                "events": [...],
                "estimated_cost": ...,
                "elapsed_seconds": ...,
                "tool_calls": ...
            },
            "agent_correct": True / False
        }
    """

    trajectory_results = []
    outcome_values = []

    for run in runs:

        agent = run.get("agent", {})

        events = agent.get("events", [])

        trajectory = evaluate_trajectory(events)

        trajectory_results.append(trajectory)

        outcome_values.append(
            bool(run.get("agent_correct", False))
        )

    total = len(runs)

    valid_trajectories = sum(
        item["trajectory_valid"]
        for item in trajectory_results
    )

    correct_outcomes = sum(outcome_values)

    costs = [
        float(
            run.get("agent", {})
            .get("estimated_cost", 0.0)
        )
        for run in runs
    ]

    latencies = [
        float(
            run.get("agent", {})
            .get("elapsed_seconds", 0.0)
        )
        for run in runs
    ]

    tool_counts = [
        int(
            run.get("agent", {})
            .get("tool_calls", 0)
        )
        for run in runs
    ]

    outcome_accuracy = (
        correct_outcomes / total
        if total
        else 0.0
    )

    trajectory_accuracy = (
        valid_trajectories / total
        if total
        else 0.0
    )

    return {
        "question_count": total,

        "outcome_accuracy": round(
            outcome_accuracy,
            4
        ),

        "trajectory_accuracy": round(
            trajectory_accuracy,
            4
        ),

        "tool_choice_accuracy": round(
            trajectory_accuracy,
            4
        ),

        "outcome_trajectory_gap": round(
            outcome_accuracy
            - trajectory_accuracy,
            4
        ),

        "mean_tool_calls": round(
            mean(tool_counts),
            4
        ) if tool_counts else 0.0,

        "mean_cost": round(
            mean(costs),
            6
        ) if costs else 0.0,

        "p99_cost": round(
            _percentile(costs, 0.99),
            6
        ),

        "mean_latency_seconds": round(
            mean(latencies),
            4
        ) if latencies else 0.0,

        "p99_latency_seconds": round(
            _percentile(latencies, 0.99),
            4
        ),

        "invalid_trajectory_count": (
            total - valid_trajectories
        ),

        "invalid_trajectories": [
            {
                "index": index,
                "trajectory": trajectory,
            }
            for index, trajectory
            in enumerate(
                trajectory_results,
                start=1
            )
            if not trajectory["trajectory_valid"]
        ],
    }