"""Task Set F submission requirement: run the agent and the fixed workflow
each with a single command.

    python run_contract_agent.py --system agent  --question "What is the monthly rent?"
    python run_contract_agent.py --system fixed  --question "What is the monthly rent?"
"""

import argparse
import json

from agent_loops import run_agent, run_fixed_workflow


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the contract agent or the fixed workflow on one question.")
    parser.add_argument("--system", choices=["agent", "fixed"], required=True)
    parser.add_argument("--question", required=True)
    args = parser.parse_args()

    runner = run_agent if args.system == "agent" else run_fixed_workflow
    result = runner(args.question)

    print("\n" + "=" * 70)
    print(f"SYSTEM: {args.system}")
    print("=" * 70)
    print(f"Answer: {result['answer']}")
    print(f"Sources: {result['sources']}")
    print(
        f"steps={result['steps']} tool_calls={result['tool_calls']} "
        f"total_tokens={result['total_tokens']} cost={result['estimated_cost']} "
        f"elapsed={result['elapsed_seconds']}s stop_reason={result['stop_reason']}"
    )
    print("\nEvent log:")
    print(json.dumps(result["events"], indent=2))


if __name__ == "__main__":
    main()
