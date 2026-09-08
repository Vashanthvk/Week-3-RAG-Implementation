import json


PATH = "evaluation_results/week6_benchmark.json"


def find_case_list(data):
    """
    Find the list containing evaluation case dictionaries.
    Handles common wrapper structures such as:
    {
        "results": [...]
    }
    or:
    {
        "cases": [...]
    }
    """

    if isinstance(data, list):
        return data

    if isinstance(data, dict):

        for key in (
            "results",
            "cases",
            "evaluations",
            "benchmark",
            "data"
        ):
            value = data.get(key)

            if isinstance(value, list):
                return value

        # Search one level deeper
        for value in data.values():

            if isinstance(value, list):

                if all(
                    isinstance(item, dict)
                    for item in value
                ):
                    return value

    return None


with open(
    PATH,
    "r",
    encoding="utf-8"
) as file:

    data = json.load(file)


cases = find_case_list(data)


if cases is None:

    print("=" * 70)
    print("COULD NOT FIND EVALUATION CASES")
    print("=" * 70)

    print("\nTop-level JSON type:")
    print(type(data).__name__)

    if isinstance(data, dict):

        print("\nTop-level keys:")

        for key in data.keys():
            print(f"  - {key}")

    raise SystemExit(1)


print("=" * 70)
print("FAILED WEEK 6 CASES")
print("=" * 70)


failed_count = 0


for case in cases:

    if not isinstance(case, dict):
        continue

    failure_type = case.get(
        "failure_type"
    )

    # Check several possible result fields
    overall_pass = case.get(
        "overall_pass"
    )

    if overall_pass is False or failure_type:

        failed_count += 1

        print("\n" + "-" * 70)

        print(
            f"ID       : {case.get('id')}"
        )

        print(
            f"Question : {case.get('question')}"
        )

        print(
            f"Failure  : {failure_type}"
        )

        print(
            f"Answer   : {case.get('answer')}"
        )

        print(
            f"Expected : {case.get('expected_answer')}"
        )

        print(
            f"Sources  : {case.get('sources')}"
        )

        print(
            f"Expected source : "
            f"{case.get('expected_source')}"
        )

        print(
            f"Answer pass : "
            f"{case.get('answer_pass')}"
        )

        print(
            f"Source pass : "
            f"{case.get('source_pass')}"
        )

        print(
            f"Behavior pass : "
            f"{case.get('behavior_pass')}"
        )

        print(
            f"Overall pass : "
            f"{case.get('overall_pass')}"
        )


print("\n" + "=" * 70)

print(
    f"Failed cases found: {failed_count}"
)

print("=" * 70)