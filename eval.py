from rag import answer_question


# ============================================================
# Evaluation Dataset
# ============================================================

TEST_CASES = [

    {
        "question":
            "What is the notice period for an employee?",

        "expected":
            "30 calendar days",

        "expected_source":
            "Employment_Agreement.pdf"
    },

    {
        "question":
            "How many annual leave days does the employee receive?",

        "expected":
            "18 paid annual leave days",

        "expected_source":
            "Employment_Agreement.pdf"
    },

    {
        "question":
            "How many sick leave days does the employee receive?",

        "expected":
            "10 sick leave days",

        "expected_source":
            "Employment_Agreement.pdf"
    },

    {
        "question":
            "How long must the employee maintain confidentiality after leaving?",

        "expected":
            "2 years",

        "expected_source":
            "Employment_Agreement.pdf"
    },

    {
        "question":
            "What is the monthly rent in the lease agreement?",

        "expected":
            "USD 1,500",

        "expected_source":
            "Lease_Agreement.pdf"
    },

    {
        "question":
            "What is the security deposit?",

        "expected":
            "USD 3,000",

        "expected_source":
            "Lease_Agreement.pdf"
    },

    {
        "question":
            "What is the lease termination notice period?",

        "expected":
            "60 days",

        "expected_source":
            "Lease_Agreement.pdf"
    },

    {
        "question":
            "What is the employee's medical insurance coverage?",

        "expected":
            "I don't know",

        "expected_source":
            None
    }
]


# ============================================================
# Evaluation
# ============================================================

def run_evaluation():

    passed = 0

    total = len(
        TEST_CASES
    )

    print("\n" + "=" * 70)

    print(
        "LEGAL CONTRACT RAG EVALUATION"
    )

    print("=" * 70)

    for index, test in enumerate(
        TEST_CASES,
        start=1
    ):

        question = test["question"]

        expected = test["expected"]

        expected_source = test[
            "expected_source"
        ]

        print(
            f"\nTEST {index}"
        )

        print(
            "-" * 70
        )

        print(
            f"Question: {question}"
        )

        try:

            answer, sources = answer_question(
                question
            )

            answer_lower = (
                answer.lower()
            )

            expected_lower = (
                expected.lower()
            )

            answer_correct = (
                expected_lower
                in answer_lower
            )

            source_correct = True

            if expected_source:

                source_correct = any(
                    expected_source.lower()
                    in source["source"].lower()
                    for source in sources
                )

            if (
                answer_correct
                and source_correct
            ):

                print(
                    "Result: PASS"
                )

                passed += 1

            else:

                print(
                    "Result: FAIL"
                )

            print(
                f"Expected: {expected}"
            )

            print(
                f"Actual: {answer}"
            )

            print(
                "Sources:"
            )

            displayed = set()

            for source in sources:

                key = (
                    source["source"],
                    source["page"]
                )

                if key in displayed:

                    continue

                displayed.add(key)

                print(
                    f"  - {source['source']} "
                    f"(Page {source['page']})"
                )

        except Exception as error:

            print(
                "Result: FAIL"
            )

            print(
                f"Error: {error}"
            )

    accuracy = (
        passed / total
    ) * 100

    print("\n" + "=" * 70)

    print(
        "EVALUATION SUMMARY"
    )

    print("=" * 70)

    print(
        f"Passed: {passed}/{total}"
    )

    print(
        f"Accuracy: {accuracy:.2f}%"
    )

    print("=" * 70)


# ============================================================
# Entry Point
# ============================================================

if __name__ == "__main__":

    run_evaluation()