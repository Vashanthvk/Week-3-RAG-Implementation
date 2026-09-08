import json
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

RESULTS_PATH = (
    BASE_DIR
    / "evaluation_results"
    / "week6_benchmark.json"
)


# ============================================================
# LOAD RESULTS
# ============================================================

def load_results():

    if not RESULTS_PATH.exists():

        raise FileNotFoundError(
            f"Evaluation results not found: "
            f"{RESULTS_PATH}"
        )

    with RESULTS_PATH.open(
        "r",
        encoding="utf-8"
    ) as file:

        data = json.load(file)

    if "results" not in data:

        raise ValueError(
            "week6_benchmark.json does not contain "
            "'results'."
        )

    return data


# ============================================================
# SCORE CATEGORY
# ============================================================

def score_category(
    results,
    category
):

    selected = []

    for result in results:

        failure_type = result.get(
            "failure_type"
        )

        expected_behavior = result.get(
            "expected_behavior"
        )

        # ----------------------------------------------------
        # Answer correctness
        # ----------------------------------------------------

        if category == "answer_correctness":

            selected.append(
                result["answer_pass"]
            )

        # ----------------------------------------------------
        # Source attribution
        # ----------------------------------------------------

        elif category == "source_attribution":

            # Source assertion is only meaningful for
            # answerable questions.
            if expected_behavior == "answer":

                selected.append(
                    result["source_pass"]
                )

        # ----------------------------------------------------
        # Unsupported-question refusal
        # ----------------------------------------------------

        elif category == "unsupported_refusal":

            if expected_behavior == "unknown":

                selected.append(
                    result["behavior_pass"]
                )

        # ----------------------------------------------------
        # Answer + source combined failure
        # ----------------------------------------------------

        elif category == "combined_answer_source":

            if failure_type == (
                "answer_and_source_error"
            ):

                selected.append(False)

            elif expected_behavior == "answer":

                selected.append(True)

        # ----------------------------------------------------
        # All answerable cases
        # ----------------------------------------------------

        elif category == "answerable_cases":

            if expected_behavior == "answer":

                selected.append(
                    result["passed"]
                )

    if not selected:

        return {
            "passed": 0,
            "total": 0,
            "score": 0.0,
        }

    passed = sum(
        1
        for value in selected
        if value
    )

    total = len(
        selected
    )

    score = (
        passed / total
    ) * 100

    return {
        "passed": passed,
        "total": total,
        "score": round(
            score,
            2
        ),
    }


# ============================================================
# FAILURE DISTRIBUTION
# ============================================================

def failure_distribution(results):

    distribution = {}

    for result in results:

        failure_type = result.get(
            "failure_type"
        )

        if not failure_type:

            continue

        distribution[
            failure_type
        ] = (
            distribution.get(
                failure_type,
                0
            )
            + 1
        )

    return distribution


# ============================================================
# BUILD REPORT
# ============================================================

def build_report(data):

    results = data[
        "results"
    ]

    return {
        "evaluation": data.get(
            "evaluation",
            {}
        ),

        "problem_type_scores": {

            "answer_correctness":
                score_category(
                    results,
                    "answer_correctness"
                ),

            "source_attribution":
                score_category(
                    results,
                    "source_attribution"
                ),

            "unsupported_refusal":
                score_category(
                    results,
                    "unsupported_refusal"
                ),

            "combined_answer_source":
                score_category(
                    results,
                    "combined_answer_source"
                ),

            "answerable_cases":
                score_category(
                    results,
                    "answerable_cases"
                ),
        },

        "failure_distribution":
            failure_distribution(
                results
            ),
    }


# ============================================================
# DISPLAY REPORT
# ============================================================

def print_report(report):

    print("\n")
    print("=" * 70)
    print(
        "WEEK 6 — PROBLEM TYPE SCORES"
    )
    print("=" * 70)

    scores = report[
        "problem_type_scores"
    ]

    print("\nAnswer correctness")

    print(
        f"  {scores['answer_correctness']['passed']}/"
        f"{scores['answer_correctness']['total']} "
        f"("
        f"{scores['answer_correctness']['score']:.2f}%"
        f")"
    )

    print("\nSource / contract attribution")

    print(
        f"  {scores['source_attribution']['passed']}/"
        f"{scores['source_attribution']['total']} "
        f"("
        f"{scores['source_attribution']['score']:.2f}%"
        f")"
    )

    print("\nUnsupported-question refusal")

    print(
        f"  {scores['unsupported_refusal']['passed']}/"
        f"{scores['unsupported_refusal']['total']} "
        f"("
        f"{scores['unsupported_refusal']['score']:.2f}%"
        f")"
    )

    print("\nCombined answer + source")

    print(
        f"  {scores['combined_answer_source']['passed']}/"
        f"{scores['combined_answer_source']['total']} "
        f"("
        f"{scores['combined_answer_source']['score']:.2f}%"
        f")"
    )

    print("\nAll answerable cases")

    print(
        f"  {scores['answerable_cases']['passed']}/"
        f"{scores['answerable_cases']['total']} "
        f"("
        f"{scores['answerable_cases']['score']:.2f}%"
        f")"
    )

    print("\n")
    print(
        "Failure distribution"
    )

    distribution = report[
        "failure_distribution"
    ]

    if not distribution:

        print(
            "  None"
        )

    else:

        for failure_type, count in (
            distribution.items()
        ):

            print(
                f"  - {failure_type}: {count}"
            )

    print("\n")
    print("=" * 70)


# ============================================================
# SAVE REPORT
# ============================================================

def save_report(report):

    output_path = (
        BASE_DIR
        / "evaluation_results"
        / "problem_type_scores.json"
    )

    with output_path.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            report,
            file,
            indent=2,
            ensure_ascii=False
        )

    return output_path


# ============================================================
# MAIN
# ============================================================

def main():

    data = load_results()

    report = build_report(
        data
    )

    print_report(
        report
    )

    output_path = save_report(
        report
    )

    print(
        f"\nSaved: {output_path}"
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()