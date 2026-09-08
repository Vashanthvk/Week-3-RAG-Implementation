# import json
# import unittest
# from pathlib import Path

# from rag import answer_question


# QUESTIONS_PATH = Path(__file__).resolve().parents[1] / "evaluation_questions.json"


# class EvaluationRegressionTests(unittest.TestCase):

#     def test_all_20_questions_are_loaded(self):
#         with QUESTIONS_PATH.open("r", encoding="utf-8") as file:
#             questions = json.load(file)
#         self.assertEqual(len(questions), 20)

#     def test_valid_questions_return_source_schema_and_non_empty_answer(self):
#         with QUESTIONS_PATH.open("r", encoding="utf-8") as file:
#             questions = json.load(file)

#         for item in questions[:16]:
#             answer, sources = answer_question(item["question"])
#             self.assertIsInstance(answer, str)
#             self.assertTrue(answer.strip())
#             self.assertIsInstance(sources, list)
#             self.assertTrue(sources)
#             self.assertIn("source", sources[0])
#             self.assertIn("page", sources[0])

#     def test_unsupported_questions_are_refused_cleanly(self):
#         with QUESTIONS_PATH.open("r", encoding="utf-8") as file:
#             questions = json.load(file)

#         for item in questions[16:]:
#             question = item["question"]
#             answer, _ = answer_question(question)
#             self.assertTrue(
#                 "I don't know" in answer or "not mentioned" in answer.lower() or "no mention" in answer.lower()
#             )


# if __name__ == "__main__":
#     unittest.main()








# Updated


import json
import unittest
from pathlib import Path

from rag import answer_question


QUESTIONS_PATH = (
    Path(__file__).resolve().parents[1] / "evaluation_questions.json"
)


def normalize_text(value):
    if value is None:
        return ""

    text = str(value).lower()

    replacements = {
        "\u2019": "'",
        "\u2018": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u00a0": " ",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return " ".join(text.split())


def is_unknown_answer(answer):
    text = normalize_text(answer)

    phrases = (
        "i don't know",
        "i dont know",
        "i don t know",
        "not mentioned",
        "no mention",
        "not provided",
        "not available in the provided contracts",
        "cannot be determined from the provided contracts",
    )

    return any(phrase in text for phrase in phrases)


class EvaluationRegressionTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with QUESTIONS_PATH.open("r", encoding="utf-8") as file:
            cls.questions = json.load(file)

    def test_all_20_questions_are_loaded(self):
        self.assertEqual(len(self.questions), 20)

    def test_every_case_has_required_schema(self):
        required = {
            "id",
            "question",
            "expected_behavior",
        }

        for item in self.questions:
            self.assertTrue(
                required.issubset(item.keys()),
                msg=f"{item['id']} is missing required fields",
            )

            self.assertIn(
                item["expected_behavior"],
                {"answer", "unknown"},
            )

            if item["expected_behavior"] == "answer":
                self.assertTrue(item.get("expected_answer"))
                self.assertTrue(item.get("expected_source"))

    def test_answerable_cases_return_valid_source_schema(self):
        answerable = [
            item
            for item in self.questions
            if item["expected_behavior"] == "answer"
        ]

        self.assertEqual(len(answerable), 19)

        for item in answerable:
            with self.subTest(question_id=item["id"]):
                answer, sources = answer_question(item["question"])

                self.assertIsInstance(answer, str)
                self.assertTrue(answer.strip())

                self.assertIsInstance(sources, list)
                self.assertTrue(sources)

                for source in sources:
                    self.assertIsInstance(source, dict)
                    self.assertIn("source", source)
                    self.assertIn("page", source)

    def test_unknown_cases_are_refused_cleanly(self):
        unknown_cases = [
            item
            for item in self.questions
            if item["expected_behavior"] == "unknown"
        ]

        self.assertEqual(len(unknown_cases), 1)

        for item in unknown_cases:
            with self.subTest(question_id=item["id"]):
                answer, _ = answer_question(item["question"])

                self.assertTrue(
                    is_unknown_answer(answer),
                    msg=(
                        f"{item['id']} should be refused as unsupported. "
                        f"Actual answer: {answer}"
                    ),
                )


if __name__ == "__main__":
    unittest.main()
