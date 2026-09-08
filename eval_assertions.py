import json
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

# evaluation_questions.json is in the same project directory
# as this file.
QUESTIONS_PATH = Path(__file__).resolve().parent / "evaluation_questions.json"


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(value):
    """
    Normalize text before performing assertion checks.

    This handles:
    - Case differences
    - Curly quotes
    - En/em dashes
    - Non-breaking spaces
    - Extra whitespace
    """
    if value is None:
        return ""

    text = str(value).lower()

    replacements = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u00a0": " ",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return " ".join(text.split())


# ============================================================
# UNKNOWN / REFUSAL DETECTION
# ============================================================

def is_unknown_answer(answer):
    """
    Determine whether the generated answer represents
    an appropriate 'I don't know' / unsupported response.
    """

    text = normalize_text(answer)

    unknown_phrases = (
        "i don't know",
        "i dont know",
        "i don t know",
        "not mentioned",
        "no mention",
        "not provided",
        "not available in the provided contracts",
        "cannot be determined from the provided contracts",
    )

    return any(phrase in text for phrase in unknown_phrases)


# ============================================================
# DATASET LOADING AND VALIDATION
# ============================================================

def load_questions():
    """
    Load and validate the Week 6 evaluation dataset.
    """

    if not QUESTIONS_PATH.exists():
        raise FileNotFoundError(
            f"Evaluation dataset not found: {QUESTIONS_PATH}"
        )

    with QUESTIONS_PATH.open("r", encoding="utf-8") as file:
        questions = json.load(file)

    if not isinstance(questions, list):
        raise ValueError(
            "evaluation_questions.json must contain a JSON list."
        )

    # Current Week 6 evaluation set contains 20 cases.
    if len(questions) != 20:
        raise ValueError(
            f"Expected exactly 20 evaluation questions, "
            f"found {len(questions)}."
        )

    required_fields = {
        "id",
        "question",
        "expected_behavior",
    }

    for item in questions:
        missing = required_fields - set(item.keys())

        if missing:
            raise ValueError(
                f"Question {item.get('id', '<unknown>')} "
                f"is missing fields: {sorted(missing)}"
            )

        if item["expected_behavior"] not in {
            "answer",
            "unknown",
        }:
            raise ValueError(
                f"Question {item['id']} has invalid "
                f"expected_behavior: {item['expected_behavior']}"
            )

        # Answerable questions must define both the
        # expected answer and expected source.
        if item["expected_behavior"] == "answer":

            if not item.get("expected_answer"):
                raise ValueError(
                    f"Question {item['id']} requires expected_answer."
                )

            if not item.get("expected_source"):
                raise ValueError(
                    f"Question {item['id']} requires expected_source."
                )

    return questions


# ============================================================
# SOURCE VALIDATION
# ============================================================

def source_schema_valid(sources):
    """
    Validate the structure of the sources returned by RAG.

    Expected structure:

    [
        {
            "source": "employment_agreement.pdf",
            "page": 3
        }
    ]
    """

    if not isinstance(sources, list):
        return False

    if not sources:
        return False

    for source in sources:

        if not isinstance(source, dict):
            return False

        if "source" not in source:
            return False

        if "page" not in source:
            return False

        if not str(source["source"]).strip():
            return False

    return True


# ============================================================
# EXPECTED SOURCE MATCHING
# ============================================================

def source_matches(sources, expected_source):
    """
    Check whether the expected contract/source is present
    in the retrieved/generated source list.
    """

    expected_name = Path(
        str(expected_source)
    ).name.lower()

    if not isinstance(sources, list):
        return False

    for source in sources:

        actual_name = Path(
            str(source.get("source", ""))
        ).name.lower()

        if actual_name == expected_name:
            return True

    return False


# ============================================================
# EXPECTED ANSWER MATCHING
# ============================================================

def answer_matches_expected(answer, expected_answer):
    """
    Perform deterministic assertion checks against the
    expected answer.

    This is intentionally lightweight.

    It does not attempt to determine semantic equivalence
    for every possible answer. More advanced semantic
    evaluation will be handled later using an LLM judge.
    """

    actual = normalize_text(answer)
    expected = normalize_text(expected_answer)

    if not actual:
        return False

    # An unsupported/refusal answer cannot satisfy an
    # answerable evaluation case.
    if is_unknown_answer(actual):
        return False

    # Direct expected-answer match.
    if expected in actual:
        return True

    # Known equivalent / decomposed answer patterns.
    alternatives = {

        "misconduct, breach of contract, or mutual agreement": (
            "misconduct",
            "breach of contract",
            "mutual agreement",
        ),

        "18 paid annual leave days and 10 sick leave days each year": (
            "18 paid annual leave days",
            "10 sick leave days",
        ),

        "before the 5th of each month": (
            "before the 5th",
        ),

        "the landlord": (
            "landlord",
        ),

        "lease_agreement.pdf": (
            "lease agreement",
        ),

        "employment_agreement.pdf": (
            "employment agreement",
        ),
    }

    required_parts = alternatives.get(
        expected,
        ()
    )

    if required_parts:
        return all(
            part in actual
            for part in required_parts
        )

    return False


# ============================================================
# SINGLE CASE EVALUATION
# ============================================================

def evaluate_case(item, answer, sources):
    """
    Evaluate one question against its expected behavior.

    Returns a dictionary containing individual assertion
    dimensions and the overall result.
    """

    expected_behavior = item["expected_behavior"]

    # --------------------------------------------------------
    # Unsupported / unknown question
    # --------------------------------------------------------

    if expected_behavior == "unknown":

        answer_ok = is_unknown_answer(answer)

        # For an unsupported question, the primary assertion
        # is that the system refuses to invent an answer.
        #
        # Sources are not required for refusal correctness.
        # This avoids incorrectly failing a valid refusal when
        # the RAG pipeline intentionally returns no sources.
        return {
            "answer_pass": answer_ok,
            "source_pass": True,
            "behavior_pass": answer_ok,
            "passed": answer_ok,
            "failure_type": (
                None
                if answer_ok
                else "refusal_error"
            ),
        }

    # --------------------------------------------------------
    # Answerable question
    # --------------------------------------------------------

    expected_answer = item.get(
        "expected_answer"
    )

    expected_source = item.get(
        "expected_source"
    )

    answer_ok = answer_matches_expected(
        answer,
        expected_answer
    )

    source_schema_ok = source_schema_valid(
        sources
    )

    expected_source_ok = source_matches(
        sources,
        expected_source
    )

    # --------------------------------------------------------
    # Failure classification
    # --------------------------------------------------------

    if not answer_ok and not expected_source_ok:
        failure_type = "answer_and_source_error"

    elif not answer_ok:
        failure_type = "answer_or_grounding_error"

    elif not expected_source_ok:
        failure_type = "source_attribution_error"

    elif not source_schema_ok:
        failure_type = "source_schema_error"

    else:
        failure_type = None

    # Overall pass requires:
    # 1. Correct answer
    # 2. Valid source structure
    # 3. Expected source present
    passed = (
        answer_ok
        and source_schema_ok
        and expected_source_ok
    )

    return {
        "answer_pass": answer_ok,
        "source_pass": expected_source_ok,
        "behavior_pass": answer_ok,
        "passed": passed,
        "failure_type": failure_type,
    }


# ============================================================
# DATASET SUMMARY
# ============================================================

def print_dataset_summary(questions):
    """
    Print a concise summary of the evaluation dataset.
    """

    answer_cases = sum(
        1
        for item in questions
        if item["expected_behavior"] == "answer"
    )

    unknown_cases = sum(
        1
        for item in questions
        if item["expected_behavior"] == "unknown"
    )

    print(
        f"Total evaluation cases : {len(questions)}"
    )

    print(
        f"Answerable cases       : {answer_cases}"
    )

    print(
        f"Unknown/refusal cases  : {unknown_cases}"
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    questions = load_questions()

    print("=" * 70)
    print("WEEK 6 EVALUATION ASSERTIONS")
    print("=" * 70)

    print(
        f"Validated evaluation cases: {len(questions)}"
    )

    print()

    print_dataset_summary(questions)

    print()

    print("Assertion dimensions:")

    print("  ✓ Answer correctness")
    print("  ✓ Source schema integrity")
    print("  ✓ Expected contract/source")
    print("  ✓ Unsupported-question refusal")

    print("=" * 70)