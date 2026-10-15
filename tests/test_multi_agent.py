import unittest
from multi_agent import agent_card
from multi_agent_race import passes, percentile


class MultiAgentTests(unittest.TestCase):
    def test_percentile_tail(self):
        self.assertEqual(percentile([1.0, 2.0, 3.0], 99), 3.0)

    def test_keyword_groups(self):
        self.assertTrue(passes("12 months and 45 days", [["12 month"], ["45 day"]]))

    def test_agent_card(self):
        self.assertIn("skills", agent_card())

    def test_token_usage_is_not_derived_from_payload_size(self):
        # The race's measured token value comes from the model response usage
        # fields; deterministic workers must remain zero-token hand-offs.
        self.assertTrue("_token_count" not in open("multi_agent.py", encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main()
