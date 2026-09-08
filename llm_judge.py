import argparse
import json
import re
from pathlib import Path

from langchain_ollama import OllamaLLM


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

BENCHMARK_PATH = BASE_DIR / "evaluation_results" / "week6_benchmark.json"
OUTPUT_PATH = BASE_DIR / "evaluation_results" / "llm_judge_baseline.json"

MODEL_NAME = "llama3.2"


# ============================================================
# LLM JUDGE
# ============================================================

judge_llm = OllamaLLM(
    model=MODEL_NAME,
    temperature=0,
)


# ============================================================
# JSON EXTRACTION
# ============================================================

def extract_json(text):
    """
    Extract the first JSON object returned by the judge.
    """

    text = text.strip()

    # Direct JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # JSON inside markdown code block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)

    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # First {...} object
    match = re.search(r"\{.*\}", text, re.DOTALL)

    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None


# ============================================================
# JUDGE PROMPT
# ============================================================

def build_judge_prompt(case):
    question = case.get("question", "")
    expected_answer = case.get("expected_answer", "")
    expected_source = case.get("expected_source", "")
    expected_behavior = case.get("expected_behavior", "")

    actual_answer = case.get("answer", "")
    actual_sources = case.get("sources", [])

    source_text = json.dumps(actual_sources, indent=2)

    if expected_behavior == "unknown":
        expected_section = """
This is an unsupported-question case.

The expected behavior is to refuse to answer because the provided
contracts do not contain enough information to answer the question.

Expected behavior:
UNKNOWN / REFUSAL
"""
    else:
        expected_section = f"""
Expected answer:
{expected_answer}

Expected contract/source:
{expected_source}
"""

    return f"""
You are an evaluator for a Legal Contract RAG system.

Evaluate the system's response strictly against the evaluation target.

Do not reward an answer merely because it sounds plausible.
Do not use outside legal knowledge.
Judge only using the supplied evaluation information.

QUESTION:
{question}

{expected_section}

SYSTEM ANSWER:
{actual_answer}

SYSTEM SOURCES:
{source_text}

Evaluate the response on these dimensions:

1. correctness
   - Is the answer factually consistent with the expected answer?
   - For unsupported questions, determine whether the system correctly refused.

2. grounding
   - Is the answer appropriately grounded in the provided contract/evaluation target?
   - Do not give a high score if the answer contains unsupported claims.

3. source_attribution
   - Does the cited contract/source match the expected contract/source?
   - For unsupported/refusal cases, source attribution is not required.

4. overall
   - Overall quality considering correctness, grounding, and source attribution.

Use scores from 1 to 10:

1-2 = very poor
3-4 = poor
5-6 = partially acceptable
7-8 = good
9-10 = excellent

Return ONLY valid JSON.
Do not include markdown.
Do not include explanations outside the JSON.

Required JSON format:

{{
  "correctness": <integer 1-10>,
  "grounding": <integer 1-10>,
  "source_attribution": <integer 1-10>,
  "overall": <integer 1-10>,
  "reason": "<short explanation>"
}}
"""


# ============================================================
# SCORE VALIDATION
# ============================================================

def normalize_score(value):
    """
    Ensure a judge score is an integer from 1 to 10.
    """

    try:
        score = int(value)
    except (TypeError, ValueError):
        return None

    if 1 <= score <= 10:
        return score

    return None


def validate_judge_result(result):
    """
    Validate the structure returned by the LLM judge.
    """

    if not isinstance(result, dict):
        return False

    required_fields = [
        "correctness",
        "grounding",
        "source_attribution",
        "overall",
        "reason",
    ]

    for field in required_fields:
        if field not in result:
            return False

    for field in [
        "correctness",
        "grounding",
        "source_attribution",
        "overall",
    ]:
        if normalize_score(result[field]) is None:
            return False

    if not isinstance(result["reason"], str):
        return False

    return True


# ============================================================
# JUDGE ONE CASE
# ============================================================

def judge_case(case):
    prompt = build_judge_prompt(case)

    raw_response = judge_llm.invoke(prompt)

    parsed = extract_json(raw_response)

    if not validate_judge_result(parsed):
        return {
            "judge_status": "invalid",
            "correctness": None,
            "grounding": None,
            "source_attribution": None,
            "overall": None,
            "reason": "LLM judge returned invalid JSON or invalid scores.",
            "raw_response": raw_response,
        }

    return {
        "judge_status": "valid",
        "correctness": normalize_score(parsed["correctness"]),
        "grounding": normalize_score(parsed["grounding"]),
        "source_attribution": normalize_score(
            parsed["source_attribution"]
        ),
        "overall": normalize_score(parsed["overall"]),
        "reason": parsed["reason"],
    }


# ============================================================
# SUMMARY
# ============================================================

def calculate_summary(results):
    valid_results = [
        result
        for result in results
        if result.get("judge_status") == "valid"
    ]

    if not valid_results:
        return {
            "total_cases": len(results),
            "valid_judgments": 0,
            "invalid_judgments": len(results),
            "average_correctness": None,
            "average_grounding": None,
            "average_source_attribution": None,
            "average_overall": None,
        }

    def average(field):
        values = [
            result[field]
            for result in valid_results
            if result.get(field) is not None
        ]

        if not values:
            return None

        return round(sum(values) / len(values), 2)

    return {
        "total_cases": len(results),
        "valid_judgments": len(valid_results),
        "invalid_judgments": len(results) - len(valid_results),
        "average_correctness": average("correctness"),
        "average_grounding": average("grounding"),
        "average_source_attribution": average(
            "source_attribution"
        ),
        "average_overall": average("overall"),
    }


# ============================================================
# LOAD BENCHMARK
# ============================================================

def load_benchmark():
    if not BENCHMARK_PATH.exists():
        raise FileNotFoundError(
            f"Benchmark file not found:\n{BENCHMARK_PATH}\n\n"
            "Run this first:\n"
            "python eval.py --benchmark"
        )

    with open(BENCHMARK_PATH, "r", encoding="utf-8") as file:
        data = json.load(file)

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        if "results" in data:
            return data["results"]

        if "cases" in data:
            return data["cases"]

    raise ValueError(
        "Unsupported benchmark JSON structure. "
        "Expected a list or a dictionary containing "
        "'results' or 'cases'."
    )


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Week 6 LLM-as-Judge evaluation"
    )

    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run LLM judge against the existing Week 6 benchmark.",
    )

    args = parser.parse_args()

    if not args.benchmark:
        parser.print_help()
        return

    print()
    print("=" * 70)
    print("WEEK 6 — LLM-AS-JUDGE")
    print("=" * 70)

    benchmark = load_benchmark()

    print(f"\nBenchmark cases: {len(benchmark)}")
    print(f"Judge model     : {MODEL_NAME}")
    print()

    results = []

    for index, case in enumerate(benchmark, start=1):
        case_id = case.get("id", index)
        question = case.get("question", "")

        print(
            f"[{index}/{len(benchmark)}] "
            f"Case {case_id}: {question}"
        )

        try:
            judge_result = judge_case(case)

        except Exception as exc:
            judge_result = {
                "judge_status": "error",
                "correctness": None,
                "grounding": None,
                "source_attribution": None,
                "overall": None,
                "reason": str(exc),
                "raw_response": None,
            }

        result = {
            "id": case_id,
            "question": question,
            "expected_answer": case.get("expected_answer"),
            "expected_source": case.get("expected_source"),
            "expected_behavior": case.get("expected_behavior"),
            "actual_answer": case.get("answer"),
            "actual_sources": case.get("sources", []),

            # Existing deterministic evaluation
            "deterministic_pass": case.get("pass"),
            "deterministic_answer_pass": case.get("answer_pass"),
            "deterministic_source_pass": case.get("source_pass"),
            "deterministic_behavior_pass": case.get("behavior_pass"),
            "failure_type": case.get("failure_type"),

            # LLM judge
            "judge_status": judge_result["judge_status"],
            "correctness": judge_result["correctness"],
            "grounding": judge_result["grounding"],
            "source_attribution": judge_result[
                "source_attribution"
            ],
            "overall": judge_result["overall"],
            "judge_reason": judge_result["reason"],
        }

        results.append(result)

        if judge_result["judge_status"] == "valid":
            print(
                f"    Correctness        : "
                f"{judge_result['correctness']}/10"
            )
            print(
                f"    Grounding          : "
                f"{judge_result['grounding']}/10"
            )
            print(
                f"    Source attribution : "
                f"{judge_result['source_attribution']}/10"
            )
            print(
                f"    Overall            : "
                f"{judge_result['overall']}/10"
            )
        else:
            print(
                f"    Judge status       : "
                f"{judge_result['judge_status']}"
            )

    summary = calculate_summary(results)

    output = {
        "evaluation": "week6_llm_as_judge_baseline",
        "model": MODEL_NAME,
        "benchmark_file": str(BENCHMARK_PATH),
        "summary": summary,
        "results": results,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as file:
        json.dump(output, file, indent=2, ensure_ascii=False)

    print()
    print("=" * 70)
    print("LLM-AS-JUDGE SUMMARY")
    print("=" * 70)

    print(
        f"\nTotal cases             : "
        f"{summary['total_cases']}"
    )

    print(
        f"Valid judgments        : "
        f"{summary['valid_judgments']}"
    )

    print(
        f"Invalid judgments      : "
        f"{summary['invalid_judgments']}"
    )

    if summary["valid_judgments"] > 0:
        print(
            f"\nAverage correctness     : "
            f"{summary['average_correctness']}/10"
        )

        print(
            f"Average grounding      : "
            f"{summary['average_grounding']}/10"
        )

        print(
            f"Average source         : "
            f"{summary['average_source_attribution']}/10"
        )

        print(
            f"Average overall        : "
            f"{summary['average_overall']}/10"
        )

    print()
    print(f"Saved: {OUTPUT_PATH}")
    print("=" * 70)


if __name__ == "__main__":
    main()