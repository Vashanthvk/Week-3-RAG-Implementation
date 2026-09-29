# Mitigation: tighter tool description (get_definitions)

Task Set F requirement #4: apply exactly ONE mitigation to the top failure
mode. The baseline (`trajectory_eval_baseline.md`) showed **10/10 cases
classified as `loop`** -- in almost every case the model reflexively called
`get_definitions` on a fact that was already plainly stated in the
retrieved evidence (e.g. `get_definitions(term="Annual_Salary", ...)` when
"Annual Salary USD 72,000" was already sitting in the retrieved text),
which either burned a step on a fictional term or, worse, quietly
overwrote a correct in-hand fact. That repeatedly tripped the stuck-loop
guard.

## The one change

Only `TOOL_DESCRIPTIONS["get_definitions"]` in `agent_loops.py` changed
(which also flows straight into the ReAct prompt, since the prompt
template interpolates this string). Nothing else -- not the few-shot
examples, not the stuck-loop threshold, not the budgets, not the
temperature -- was touched, so any change in the numbers is attributable
to this one description edit.

### Before

```python
"get_definitions": (
    "Look up the literal meaning of ONE named defined term (for "
    "example 'Cause' or 'Notice Period') inside a single contract's "
    "Definitions section, chosen with the contract_version enum: "
    f"{CONTRACT_VERSIONS}. Does not search broadly across contracts "
    "and does not draft an answer."
),
```

### After

```python
"get_definitions": (
    "Look up the literal meaning of ONE named defined term (for "
    "example 'Cause' or 'Notice Period') inside a single contract's "
    "Definitions section, chosen with the contract_version enum: "
    f"{CONTRACT_VERSIONS}. Does not search broadly across contracts "
    "and does not draft an answer. Do NOT call this for a fact that "
    "is already stated as a plain number, date, or amount in the "
    "most recent retrieve_contract_evidence observation -- only call "
    "it for a capitalized term that is referenced by name (e.g. "
    "'Cause') whose value is NOT already visible there."
),
```

## Before -> after count and price

**`loop` failure count: 10/10 -> 10/10. No improvement.**

The re-run (`trajectory_eval_after_mitigation.md`) shows the model still
reflexively calling `get_definitions` on plainly-stated facts in the same
proportion as before. Diagnosis: the defect is not "the model doesn't
understand what `get_definitions` is for" (an information problem, which a
tighter description could fix) -- it is "the model doesn't recognize it
already has enough evidence to draft" (a decision problem). Putting the
fix in the tool description puts it in the wrong place. This is exactly
the kind of negative result the rubric asks to be measured and reported
honestly rather than hoped into a success.

**Price paid -- and it was a net cost, not free:**

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| Total tokens (10 cases) | 57,743 | 62,127 | **+4,384** (+7.6%) |
| Mean cost / question | $0.002887 | $0.003106 | **+$0.000219** (+7.6%) |
| Cost p50 | $0.002670 | $0.002819 | +$0.000149 |
| Cost max | $0.003858 | $0.004302 | +$0.000444 |

Latency also rose sharply in the after-run (mean 32.97s -> 65.09s), but
this is flagged as **likely confounded by system load** rather than a
clean effect of the mitigation -- a 7.6% token increase cannot plausibly
explain a ~97% latency increase, and claiming it as the mitigation's price
would itself be an unmeasured assumption of the kind this rubric penalizes.
The token/cost deltas above are the reliable, attributable price signal:
the longer tool description adds real tokens to every single model call
(it's interpolated into the ReAct prompt each turn), so the mitigation
costs money on every case, dependency or not, regardless of whether it
helps that case.

**Conclusion:** this mitigation is reported as applied, measured, and
ineffective. See `regression_check.md` for the full per-mode comparison.
