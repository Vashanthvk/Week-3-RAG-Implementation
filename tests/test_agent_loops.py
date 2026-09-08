import unittest
from unittest.mock import patch

from agent_loops import LoopBudget, compare_workflows, run_agent


class AgentLoopTests(unittest.TestCase):

    def test_agent_exposes_multi_step_loop_and_memory(self):
        weak_result = {
            "results": [{"keyword_score": 0.0}],
            "attempt": 2,
        }
        strong_result = {
            "results": [{
                "keyword_score": 1.0,
                "document": {"metadata": {"source": "Employment_Agreement.pdf", "page": 1}},
            }],
            "attempt": 1,
        }

        with patch("agent_loops.retrieve_with_retry", side_effect=[weak_result, strong_result]), patch(
            "agent_loops.generate_answer", return_value="The notice period is 30 days."
        ), patch("agent_loops.build_context", return_value="contract context"):
            result = run_agent("What is the notice period?", LoopBudget(max_steps=4))

        phases = [event["phase"] for event in result["events"]]
        self.assertIn("PLAN", phases)
        self.assertIn("ACT", phases)
        self.assertIn("OBSERVE", phases)
        self.assertEqual(result["stop_reason"], "answer_ready")
        self.assertGreaterEqual(result["steps"], 2)
        self.assertTrue(result["memory"])
        self.assertLessEqual(result["estimated_cost"], 0.01)

    def test_agent_stops_at_step_budget(self):
        weak_result = {"results": [], "attempt": 2}

        with patch("agent_loops.retrieve_with_retry", return_value=weak_result):
            result = run_agent("Unsupported question", LoopBudget(max_steps=2))

        self.assertEqual(result["stop_reason"], "max_steps")
        self.assertFalse(result["answer"])
        self.assertLessEqual(result["steps"], 2)

    def test_agent_stops_at_cost_budget(self):
        with patch("agent_loops.retrieve_with_retry", return_value={"results": [], "attempt": 1}):
            result = run_agent(
                "What is not in the contracts?",
                LoopBudget(max_cost=0.0005),
            )

        self.assertEqual(result["stop_reason"], "max_cost")
        self.assertEqual(result["tool_calls"], 0)

    def test_agent_refuses_when_evidence_is_unsupported(self):
        weak_result = {
            "results": [{
                "keyword_score": 1.0,
                "document": {"metadata": {"source": "contract.pdf", "page": 1}},
            }],
            "attempt": 1,
        }

        with patch("agent_loops.retrieve_with_retry", return_value=weak_result), patch(
            "agent_loops.should_refuse_answer", return_value=True
        ):
            result = run_agent("What is the pet policy?", LoopBudget(max_steps=2))

        self.assertEqual(result["stop_reason"], "answer_ready")
        self.assertIn("I don't know", result["answer"])

    def test_comparison_reports_both_workflows(self):
        def fake_agent(question):
            return {
                "answer": "agent",
                "sources": [{"source": "contract.pdf", "page": 1}],
                "steps": 3,
                "estimated_cost": 0.003,
            }

        def fake_fixed(question):
            return {
                "answer": "fixed",
                "sources": [{"source": "contract.pdf", "page": 1}],
                "steps": 2,
                "estimated_cost": 0.002,
            }

        result = compare_workflows(
            [{"id": 1, "question": "What is the rent?"}],
            agent_runner=fake_agent,
            fixed_runner=fake_fixed,
        )

        self.assertEqual(result["question_count"], 1)
        self.assertEqual(result["agent"]["answered"], 1)
        self.assertEqual(result["fixed_workflow"]["answered"], 1)
        self.assertEqual(result["agent"]["average_steps"], 3)
        self.assertEqual(result["fixed_workflow"]["average_steps"], 2)


if __name__ == "__main__":
    unittest.main()
