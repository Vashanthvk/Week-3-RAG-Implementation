import json
from pathlib import Path


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

JUDGE_PATH = (
    BASE_DIR
    / "evaluation_results"
    / "llm_judge_baseline.json"
)

OUTPUT_PATH = (
    BASE_DIR
    / "evaluation_results"
    / "judge_human_validation.json"
)


# ============================================================
# LOAD JUDGE RESULTS
# ============================================================

def load_judge_results():
    if not JUDGE_PATH.exists():
        raise FileNotFoundError(
            f"LLM judge results not found:\n{JUDGE_PATH}\n\n"
            "Run this first:\n"
            "python llm_judge.py --benchmark"
        )

    with open(JUDGE_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


# ============================================================
# CREATE VALIDATION TEMPLATE
# ============================================================

def build_validation_template(data):
    results = data.get("results", [])

    validation_cases = []

    for result in results:
        validation_cases.append(
            {
                "id": result.get("id"),
                "question": result.get("question"),

                "expected_answer": result.get(
                    "expected_answer"
                ),

                "expected_source": result.get(
                    "expected_source"
                ),

                "expected_behavior": result.get(
                    "expected_behavior"
                ),

                "actual_answer": result.get(
                    "actual_answer"
                ),

                "actual_sources": result.get(
                    "actual_sources", []
                ),

                "llm_judge": {
                    "correctness": result.get(
                        "correctness"
                    ),
                    "grounding": result.get(
                        "grounding"
                    ),
                    "source_attribution": result.get(
                        "source_attribution"
                    ),
                    "overall": result.get(
                        "overall"
                    ),
                    "reason": result.get(
                        "judge_reason"
                    ),
                },

                # ------------------------------------------------
                # HUMAN REVIEW
                # ------------------------------------------------
                #
                # Fill these manually.
                #
                # Use 1-10.
                #
                "human_review": {
                    "correctness": None,
                    "grounding": None,
                    "source_attribution": None,
                    "overall": None,
                    "notes": "",
                },
            }
        )

    return {
        "evaluation": "week6_judge_human_validation",
        "instructions": {
            "correctness": (
                "Rate factual correctness from 1-10."
            ),
            "grounding": (
                "Rate how well the answer is grounded "
                "in the supplied contract evidence."
            ),
            "source_attribution": (
                "Rate whether the cited contract/source "
                "is the correct source. For unsupported "
                "questions, use 10 when the refusal behavior "
                "is appropriate."
            ),
            "overall": (
                "Rate the overall response quality from 1-10."
            ),
            "scale": (
                "1-2 very poor, "
                "3-4 poor, "
                "5-6 partially acceptable, "
                "7-8 good, "
                "9-10 excellent"
            ),
        },
        "cases": validation_cases,
    }


# ============================================================
# MAIN
# ============================================================

def main():
    print()
    print("=" * 70)
    print("WEEK 6 — JUDGE HUMAN VALIDATION TEMPLATE")
    print("=" * 70)

    data = load_judge_results()

    validation = build_validation_template(data)

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        OUTPUT_PATH,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            validation,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print()
    print(
        f"Validation cases: "
        f"{len(validation['cases'])}"
    )

    print()
    print("Created:")
    print(OUTPUT_PATH)

    print()
    print(
        "Next step: open the JSON file and fill the "
        "'human_review' scores for each case."
    )

    print("=" * 70)


if __name__ == "__main__":
    main()