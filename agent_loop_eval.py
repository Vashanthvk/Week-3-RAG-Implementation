"""Week 7 agent-loop comparison runner for the legal-contract track."""

import json
from pathlib import Path

from agent_loops import compare_workflows


QUESTIONS_PATH = Path(__file__).with_name("evaluation_questions.json")
REPORT_PATH = Path(__file__).with_name("AGENT_LOOP_REPORT.md")


def load_questions():
    with QUESTIONS_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def main():
    questions = load_questions()
    comparison = compare_workflows(questions)
    summary = {
        "task": "Answer legal contract questions with grounded sources",
        "question_set": QUESTIONS_PATH.name,
        "question_count": len(questions),
        "agent_loop": comparison["agent"],
        "fixed_workflow": comparison["fixed_workflow"],
        "safety": {
            "max_steps": 6,
            "max_seconds": 30.0,
            "max_cost_per_question": 0.01,
            "visible_events": True,
            "short_term_memory": True,
        },
        "ship_decision": (
            "Ship the fixed workflow for this known contract-QA path: it has a fixed sequence, "
            "so it is simpler, cheaper, and more predictable. Keep the agent loop for tasks "
            "where retrieval quality changes the next action."
        ),
        "comparison": comparison,
    }
    REPORT_PATH.write_text(
        "# Legal Contract Agent Loop Report\n\n"
        + json.dumps(summary, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
