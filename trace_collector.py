import json
from pathlib import Path

from rag import answer_question


QUESTIONS_FILE = Path(
    "evaluation_questions.json"
)

TRACE_FILE = Path(
    "traces/traces.jsonl"
)


def load_questions():

    with QUESTIONS_FILE.open(
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


def clear_previous_traces():

    TRACE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    if TRACE_FILE.exists():

        answer = input(
            "\nExisting trace file found. "
            "Type RESET to clear it before collecting "
            "the 20 Week 5 traces: "
        ).strip()

        if answer != "RESET":

            print(
                "\nCollection cancelled. "
                "Existing traces were preserved."
            )

            return False

        TRACE_FILE.unlink()

        print(
            "Previous traces cleared."
        )

    return True


def main():

    questions = load_questions()

    if len(questions) != 20:

        raise ValueError(
            f"Expected exactly 20 questions, "
            f"found {len(questions)}."
        )

    if not clear_previous_traces():

        return

    print(
        "\n" + "=" * 70
    )

    print(
        "WEEK 5 — TRACE COLLECTION"
    )

    print(
        "=" * 70
    )

    print(
        f"Questions to run: {len(questions)}"
    )

    print(
        "Trace file: traces/traces.jsonl"
    )

    print(
        "=" * 70
    )

    completed = 0

    for item in questions:

        question_id = item["id"]

        question = item["question"]

        print(
            "\n" + "#" * 70
        )

        print(
            f"TRACE {question_id}/20"
        )

        print(
            "#" * 70
        )

        print(
            f"Question: {question}"
        )

        try:

            answer_question(
                question,
                log_trace=True
            )

            completed += 1

            print(
                f"\nCollection progress: "
                f"{completed}/20"
            )

        except Exception as error:

            print(
                f"\nERROR while processing "
                f"question {question_id}: "
                f"{type(error).__name__}: {error}"
            )

            print(
                "Continuing with the next question."
            )

    print(
        "\n" + "=" * 70
    )

    print(
        "WEEK 5 TRACE COLLECTION COMPLETE"
    )

    print(
        "=" * 70
    )

    print(
        f"Successfully executed: {completed}/20"
    )

    print(
        f"Trace file: {TRACE_FILE}"
    )

    print(
        "=" * 70
    )


if __name__ == "__main__":
    main()