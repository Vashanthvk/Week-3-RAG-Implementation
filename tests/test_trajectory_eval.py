import unittest
from unittest.mock import patch

from trajectory_eval import (
    build_tool_sequence,
    calculate_cost_metrics,
    calculate_metrics,
    calculate_step_efficiency,
    classify_failure,
    evaluate_argument_validity,
    evaluate_case,
    evaluate_tool_choice,
    outcome_passed,
)


T07_CASE = {
    "id": "T07",
    "question": "cure period question",
    "expected_paths": [
        ["retrieve_contract_evidence", "get_definitions", "draft_grounded_answer"],
        ["retrieve_contract_evidence", "draft_grounded_answer"],
    ],
    "short_path_grounding_phrases": ["fifteen (15) days"],
    "expected_keywords": ["25 May 2025"],
    "needed_steps": 3,
    "dependency": True,
}

SIMPLE_CASE = {
    "id": "T01",
    "question": "rent question",
    "expected_paths": [["retrieve_contract_evidence", "draft_grounded_answer"]],
    "expected_keywords": ["1,500"],
    "needed_steps": 2,
    "dependency": False,
}


def act(tool):
    return {"phase": "ACT", "tool": tool}


def observe(message):
    return {"phase": "OBSERVE", "message": message}


class ToolChoiceTests(unittest.TestCase):

    def test_full_path_with_real_lookup_is_valid(self):
        events = [
            act("retrieve_contract_evidence"),
            observe('Top result from X.pdf: "...Termination for Cause..." (best_score=0.80)'),
            act("get_definitions"),
            observe("'Cause' in Master_Service_Agreement means: fifteen (15) days ..."),
            act("draft_grounded_answer"),
        ]
        valid, path = evaluate_tool_choice(T07_CASE, events)
        self.assertTrue(valid)
        self.assertEqual(path, ["retrieve_contract_evidence", "get_definitions", "draft_grounded_answer"])

    def test_short_path_without_grounding_is_the_target_failure(self):
        events = [
            act("retrieve_contract_evidence"),
            observe('Top result from X.pdf: "...Termination for Cause, cure period..." (best_score=0.80)'),
            act("draft_grounded_answer"),
        ]
        valid, path = evaluate_tool_choice(T07_CASE, events)
        self.assertFalse(valid)

    def test_short_path_with_grounding_is_a_legitimate_alternate(self):
        events = [
            act("retrieve_contract_evidence"),
            observe('Top result from X.pdf: "Cause means ... fifteen (15) days ..." (best_score=1.00)'),
            act("draft_grounded_answer"),
        ]
        valid, path = evaluate_tool_choice(T07_CASE, events)
        self.assertTrue(valid)

    def test_unexpected_sequence_is_invalid(self):
        events = [act("get_definitions"), act("draft_grounded_answer")]
        valid, path = evaluate_tool_choice(SIMPLE_CASE, events)
        self.assertFalse(valid)


class ArgumentValidityTests(unittest.TestCase):

    def test_no_lookups_is_vacuously_valid(self):
        valid, fictional = evaluate_argument_validity([act("retrieve_contract_evidence")])
        self.assertTrue(valid)
        self.assertEqual(fictional, [])

    def test_hallucinated_term_is_invalid(self):
        events = [
            act("get_definitions"),
            observe("'cure period' was not found as a defined term in Master_Service_Agreement. This contract's defined terms are: Cause."),
        ]
        valid, fictional = evaluate_argument_validity(events)
        self.assertFalse(valid)
        self.assertEqual(fictional, ["cure period"])

    def test_real_term_is_valid(self):
        events = [act("get_definitions"), observe("'Cause' in Master_Service_Agreement means: 15 days ...")]
        valid, fictional = evaluate_argument_validity(events)
        self.assertTrue(valid)


class FailureClassificationTests(unittest.TestCase):

    def test_loop_takes_priority(self):
        self.assertEqual(
            classify_failure("max_tokens", False, False, False, "", [], 5, 2),
            "loop",
        )

    def test_wrong_tool(self):
        self.assertEqual(
            classify_failure("answer_ready", False, True, True, "answer", [{"s": 1}], 2, 2),
            "wrong_tool",
        )

    def test_made_up_input(self):
        self.assertEqual(
            classify_failure("answer_ready", True, False, True, "answer", [{"s": 1}], 2, 2),
            "made_up_input",
        )

    def test_silent_giveup(self):
        self.assertEqual(
            classify_failure(
                "answer_ready", True, True, False,
                "I don't know based on the provided contracts.", [{"s": 1}], 2, 2,
            ),
            "silent_giveup",
        )

    def test_inefficient_steps(self):
        self.assertEqual(
            classify_failure("answer_ready", True, True, True, "answer", [{"s": 1}], 4, 2),
            "inefficient_steps",
        )

    def test_pass(self):
        self.assertEqual(
            classify_failure("answer_ready", True, True, True, "answer", [{"s": 1}], 2, 2),
            "pass",
        )


class MetricsTests(unittest.TestCase):

    def test_cost_p50_and_max_not_mean(self):
        metrics = calculate_cost_metrics([0.001, 0.002, 0.003, 0.05])
        self.assertEqual(metrics["max"], 0.05)
        self.assertNotEqual(metrics["p50"], metrics["max"])

    def test_step_efficiency(self):
        self.assertEqual(calculate_step_efficiency(4, 2), 2.0)
        self.assertEqual(calculate_step_efficiency(2, 2), 1.0)

    def test_outcome_passed_checks_real_content(self):
        self.assertTrue(outcome_passed("The monthly rent is USD 1,500.", SIMPLE_CASE))
        self.assertFalse(outcome_passed("I don't know based on the provided contracts.", SIMPLE_CASE))

    def test_calculate_metrics_gap(self):
        results = [
            {"tool_choice_valid": True, "argument_valid": True, "outcome_valid": True, "step_efficiency": 1.0, "estimated_cost": 0.001},
            {"tool_choice_valid": False, "argument_valid": True, "outcome_valid": True, "step_efficiency": 1.0, "estimated_cost": 0.002},
        ]
        metrics = calculate_metrics(results)
        self.assertEqual(metrics["outcome_pass_rate"], 1.0)
        self.assertEqual(metrics["trajectory_pass_rate"], 0.5)
        self.assertEqual(metrics["outcome_trajectory_gap"], 0.5)


class EvaluateCaseTests(unittest.TestCase):

    def test_evaluate_case_uses_run_agent(self):
        fake_result = {
            "answer": "USD 1,500.",
            "sources": [{"source": "Lease_Agreement.pdf", "page": 1}],
            "events": [
                act("retrieve_contract_evidence"),
                observe('Top result from Lease_Agreement.pdf: "Monthly Rent USD 1,500" (best_score=1.00)'),
                act("draft_grounded_answer"),
            ],
            "tool_calls": 2,
            "total_tokens": 500,
            "estimated_cost": 0.0002,
            "elapsed_seconds": 3.0,
            "stop_reason": "answer_ready",
        }
        with patch("trajectory_eval.run_agent", return_value=fake_result):
            result = evaluate_case(SIMPLE_CASE)

        self.assertTrue(result["tool_choice_valid"])
        self.assertTrue(result["argument_valid"])
        self.assertTrue(result["outcome_valid"])
        self.assertEqual(result["failure_mode"], "pass")


if __name__ == "__main__":
    unittest.main()
