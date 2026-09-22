import unittest

from trajectory_evaluator import evaluate_trajectory, evaluate_runs


def event(phase, tool=None, message=""):
    item = {
        "step": 0,
        "phase": phase,
        "message": message,
    }

    if tool:
        item["tool"] = tool

    return item


class TestTrajectoryEvaluator(unittest.TestCase):

    def test_retrieve_then_draft_is_valid(self):
        result = evaluate_trajectory([
            event("PLAN"),
            event("ACT", "retrieve_contract_evidence"),
            event("OBSERVE"),
            event("ACT", "draft_grounded_answer"),
        ])

        self.assertTrue(result["trajectory_valid"])
        self.assertEqual(
            result["trajectory_type"],
            "retrieve_then_draft",
        )

    def test_bounded_retry_is_valid(self):
        result = evaluate_trajectory([
            event("PLAN"),
            event("ACT", "retrieve_contract_evidence"),
            event("OBSERVE"),
            event("PLAN"),
            event("ACT", "retrieve_contract_evidence"),
            event("OBSERVE"),
        ])

        self.assertTrue(result["trajectory_valid"])
        self.assertEqual(
            result["trajectory_type"],
            "bounded_retry_refusal",
        )

    def test_draft_before_retrieval_is_invalid(self):
        result = evaluate_trajectory([
            event("ACT", "draft_grounded_answer"),
            event("ACT", "retrieve_contract_evidence"),
        ])

        self.assertFalse(result["trajectory_valid"])
        self.assertIn(
            "draft_before_retrieval",
            result["violations"],
        )

    def test_more_than_two_retrievals_is_invalid(self):
        result = evaluate_trajectory([
            event("ACT", "retrieve_contract_evidence"),
            event("ACT", "retrieve_contract_evidence"),
            event("ACT", "retrieve_contract_evidence"),
        ])

        self.assertFalse(result["trajectory_valid"])
        self.assertIn(
            "excessive_retrieval",
            result["violations"],
        )

    def test_tool_after_draft_is_invalid(self):
        result = evaluate_trajectory([
            event("ACT", "retrieve_contract_evidence"),
            event("ACT", "draft_grounded_answer"),
            event("ACT", "retrieve_contract_evidence"),
        ])

        self.assertFalse(result["trajectory_valid"])
        self.assertIn(
            "tool_after_draft",
            result["violations"],
        )

    def test_unknown_tool_is_invalid(self):
        result = evaluate_trajectory([
            event("ACT", "delete_contract"),
        ])

        self.assertFalse(result["trajectory_valid"])
        self.assertIn(
            "unknown_tool",
            result["violations"],
        )

    def test_run_metrics(self):
        runs = [
            {
                "agent": {
                    "events": [
                        event(
                            "ACT",
                            "retrieve_contract_evidence",
                        ),
                        event(
                            "ACT",
                            "draft_grounded_answer",
                        ),
                    ],
                    "estimated_cost": 0.001,
                    "elapsed_seconds": 1.0,
                    "tool_calls": 2,
                },
                "agent_correct": True,
            },
            {
                "agent": {
                    "events": [
                        event(
                            "ACT",
                            "retrieve_contract_evidence",
                        ),
                        event(
                            "ACT",
                            "retrieve_contract_evidence",
                        ),
                    ],
                    "estimated_cost": 0.002,
                    "elapsed_seconds": 2.0,
                    "tool_calls": 2,
                },
                "agent_correct": True,
            },
        ]

        metrics = evaluate_runs(runs)

        self.assertEqual(
            metrics["question_count"],
            2,
        )

        self.assertEqual(
            metrics["outcome_accuracy"],
            1.0,
        )

        self.assertEqual(
            metrics["trajectory_accuracy"],
            1.0,
        )

        self.assertEqual(
            metrics["tool_choice_accuracy"],
            1.0,
        )

        self.assertEqual(
            metrics["outcome_trajectory_gap"],
            0.0,
        )

        self.assertEqual(
            metrics["invalid_trajectory_count"],
            0,
        )

        self.assertEqual(
            metrics["mean_cost"],
            0.0015,
        )

        self.assertEqual(
            metrics["p99_cost"],
            0.00199,
        )

        self.assertEqual(
            metrics["mean_latency_seconds"],
            1.5,
        )

        self.assertEqual(
            metrics["p99_latency_seconds"],
            1.99,
        )


if __name__ == "__main__":
    unittest.main()
