# """Week 7 agent-loop comparison runner for the legal-contract track."""

# import json
# from pathlib import Path

# from agent_loops import compare_workflows


# QUESTIONS_PATH = Path(__file__).with_name("evaluation_questions.json")
# REPORT_PATH = Path(__file__).with_name("AGENT_LOOP_REPORT.md")


# def load_questions():
#     with QUESTIONS_PATH.open("r", encoding="utf-8") as file:
#         return json.load(file)


# def main():
#     questions = load_questions()
#     comparison = compare_workflows(questions)
#     summary = {
#         "task": "Answer legal contract questions with grounded sources",
#         "question_set": QUESTIONS_PATH.name,
#         "question_count": len(questions),
#         "agent_loop": comparison["agent"],
#         "fixed_workflow": comparison["fixed_workflow"],
#         "safety": {
#             "max_steps": 6,
#             "max_seconds": 30.0,
#             "max_cost_per_question": 0.01,
#             "visible_events": True,
#             "short_term_memory": True,
#         },
#         "ship_decision": (
#             "Ship the fixed workflow for this known contract-QA path: it has a fixed sequence, "
#             "so it is simpler, cheaper, and more predictable. Keep the agent loop for tasks "
#             "where retrieval quality changes the next action."
#         ),
#         "comparison": comparison,
#     }
#     REPORT_PATH.write_text(
#         "# Legal Contract Agent Loop Report\n\n"
#         + json.dumps(summary, indent=2)
#         + "\n",
#         encoding="utf-8",
#     )
#     print(json.dumps(summary, indent=2))


# if __name__ == "__main__":
#     main()




"""Agent trajectory and workflow evaluation runner.

This runner preserves the existing agent-vs-fixed comparison and additionally
calculates trajectory/efficiency metrics from the agent events.
"""

import json
from pathlib import Path

from agent_loops import compare_workflows
from trajectory_evaluator import evaluate_runs


QUESTIONS_PATH = Path(__file__).with_name("evaluation_questions.json")
REPORT_PATH = Path(__file__).with_name("AGENT_LOOP_REPORT.md")


def load_questions():
    with QUESTIONS_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def print_trajectory_baseline(metrics):
    print("\n" + "=" * 70)
    print("AGENT TRAJECTORY BASELINE")
    print("=" * 70)

    print(f"Question count             : {metrics['question_count']}")
    print(f"Outcome accuracy           : {metrics['outcome_accuracy']:.2%}")
    print(f"Trajectory accuracy        : {metrics['trajectory_accuracy']:.2%}")
    print(f"Tool-choice accuracy       : {metrics['tool_choice_accuracy']:.2%}")
    print(
        "Outcome/trajectory gap     : "
        f"{metrics['outcome_trajectory_gap']:.2%}"
    )

    print(f"Mean tool calls            : {metrics['mean_tool_calls']:.2f}")
    print(f"Mean cost                  : {metrics['mean_cost']:.6f}")
    print(f"p99 cost                   : {metrics['p99_cost']:.6f}")

    print(
        "Mean latency               : "
        f"{metrics['mean_latency_seconds']:.4f}s"
    )
    print(
        "p99 latency                : "
        f"{metrics['p99_latency_seconds']:.4f}s"
    )

    print(
        "Invalid trajectories       : "
        f"{metrics['invalid_trajectory_count']}"
    )

    if metrics["invalid_trajectories"]:
        print("\nInvalid trajectory details:")

        for item in metrics["invalid_trajectories"]:
            trajectory = item["trajectory"]

            print(
                f"  Question {item['index']}: "
                f"{trajectory['trajectory_type']} | "
                f"tools={trajectory['tool_sequence']} | "
                f"violations={trajectory['violations']}"
            )
    else:
        print("Invalid trajectory details: None")


def main():
    questions = load_questions()

    comparison = compare_workflows(questions)

    # compare_workflows already stores the per-question agent result,
    # including events and correctness, in comparison["rows"].
    trajectory_runs = [
        {
            "agent": row["agent"],
            "agent_correct": row["agent_correct"],
        }
        for row in comparison["rows"]
    ]

    trajectory_baseline = evaluate_runs(trajectory_runs)

    print_trajectory_baseline(trajectory_baseline)

    summary = {
        "task": "Answer legal contract questions with grounded sources",
        "question_set": QUESTIONS_PATH.name,
        "question_count": len(questions),

        "agent_loop": comparison["agent"],

        "fixed_workflow": comparison["fixed_workflow"],

        "trajectory_baseline": trajectory_baseline,

        "safety": {
            "max_steps": 6,
            "max_seconds": 30.0,
            "max_cost_per_question": 0.01,
            "visible_events": True,
            "short_term_memory": True,
        },

        "ship_decision": (
            "Ship the fixed workflow for this known contract-QA path: "
            "it has a fixed sequence, so it is simpler, cheaper, and "
            "more predictable. Keep the agent loop for tasks where "
            "retrieval quality changes the next action."
        ),

        "comparison": comparison,
    }

    REPORT_PATH.write_text(
        "# Legal Contract Agent Loop Report\n\n"
        + json.dumps(summary, indent=2)
        + "\n",
        encoding="utf-8",
    )

    print("\n" + "=" * 70)
    print("REPORT")
    print("=" * 70)
    print(f"Saved: {REPORT_PATH}")

    print("\n" + "=" * 70)
    print("COMPARISON SUMMARY")
    print("=" * 70)
    print(json.dumps(comparison, indent=2))


if __name__ == "__main__":
    main()
