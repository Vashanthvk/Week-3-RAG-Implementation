# Budget-termination log

Task Set F requirement #4: all four budgets enforced in code
(`agent_loops.LoopBudget` / `_budget_exceeded`), plus a log of one run
that hits a budget and terminates cleanly instead of spinning.

## Which budget fired

`max_tokens`, deliberately set far below the loop's normal per-call
footprint (the ReAct prompt's tool descriptions + two worked few-shot
examples alone run ~850-900 tokens per call, before any transcript
history is added).

Question: Delta sent Orion a written breach notice on 10 May 2025 citing Cause under the Master Services Agreement. If Orion does not cure the breach, on what date does the cure period expire?

Budget: max_steps=8, max_seconds=90.0, max_tokens=600, max_cost=0.045

## Result (clean termination, no exception, no further LLM calls)

```json
{
  "answer": '',
  "steps": 1,
  "tool_calls": 0,
  "total_tokens": 962,
  "estimated_cost": 0.000481,
  "elapsed_seconds": 3.4133,
  "stop_reason": 'max_tokens'
}
```

No tool call happened (`tool_calls: 0`), the answer
is empty rather than fabricated, and the run returns a normal dict -- no
exception, no timeout, no infinite loop.

## All four budgets are checked on every iteration

`agent_loops._budget_exceeded(state, budget)` (called both before and
after every model call inside `run_agent`'s loop) checks, in order:

1. `max_steps` -- iteration count -> `stop_reason = "max_iterations"`
2. `max_seconds` -- wall-clock -> `stop_reason = "max_wall_clock"`
3. `max_tokens` -- cumulative real tokens -> `stop_reason = "max_tokens"` (demonstrated above)
4. `max_cost` -- cumulative notional cost derived from those same real tokens -> `stop_reason = "max_cost"`

`tests/test_agent_loops.py` (`AgentLoopBudgetTests`) covers all four
programmatically with a mocked model call, so each one is exercised
without depending on a live Ollama instance.
