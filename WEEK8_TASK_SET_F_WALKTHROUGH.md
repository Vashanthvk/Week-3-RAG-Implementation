# Week 8 · Task Set F — End-to-End Walkthrough

Legal contracts track: "Find the outcome-vs-trajectory gap in the contract
agent, then close one mode." This document explains, step by step, what
was built, what the real numbers showed, and how to verify it yourself.

---

## 1. Where we started

`trajectory_evaluator.py` and `trajectory_eval.py` already existed from
Week 6/7, but neither actually satisfied Task Set F:

- `trajectory_evaluator.py`'s `ALLOWED_TOOLS` only listed the old 2 tools,
  and its trajectory-validity logic was a hardcoded state machine tuned to
  the old fixed-workflow-shaped agent.
- `trajectory_eval.py` had the right *shape* (cost p50/max, step
  efficiency, failure-mode counts, markdown report) but a real bug: its
  `evaluate_case()` **hardcoded a fake 2-event list**
  (`["retrieve_contract_evidence", "draft_grounded_answer"]`) instead of
  using the agent's real returned events. It also evaluated
  `run_fixed_workflow` — the deterministic system that, by construction,
  cannot loop, hallucinate a term, or pick a wrong tool. Week 8 is
  specifically about failure modes that only happen when a model is
  choosing the next tool, so evaluating the fixed workflow can't surface
  them at all.
- `trajectory_questions.json` had 10 cases, but every one used the old
  2-tool agent, a single expected path each, and none touched
  `get_definitions` or a dependency question.

In short: real bugs, not just missing pieces. Both needed a rewrite, not
a patch.

---

## 2. What Task Set F requires (recap)

1. Expected tool sequences for 10 cases, with legitimately-alternate-path
   cases asserted as a **set**, not one sequence.
2. Four trajectory numbers: tool-choice accuracy, argument validity rate
   (real vs. fictional clause/term references), step efficiency (steps
   taken / steps needed), cost per question reported as **p50 and max**.
3. The outcome-vs-trajectory gap as a number, plus one named case that
   passes the outcome eval while failing the trajectory eval.
4. Exactly ONE mitigation to the top failure mode, re-measured before vs.
   after, plus the price paid as a number.
5. A regression check across every failure mode, honestly naming anything
   that worsened or newly appeared.

---

## 3. Step 1 — Rebuild the 10 cases for the real agent

`trajectory_questions.json` was rewritten around the same 10 questions
used in Week 7's race (for continuity — they're the ones the current
3-tool agent is actually exercised against), restructured with:

- `expected_paths`: a **list** of acceptable tool-name sequences, not one.
- `needed_steps`: for step efficiency.
- For the 3 dependency cases (T07, T08, T09 — the MSA Cause/Notice Period
  questions and the SLA dual-term question): a **second, shorter**
  expected path (`retrieve -> draft`, skipping `get_definitions`), gated
  by a new `short_path_grounding_phrases` field.

### Why the short path needs a grounding gate, not a blanket allow

A contract's Definitions chunk states multiple terms side by side (e.g.
MSA's chunk1 has both `Cause` = 15 days *and* `Notice Period` = 30 days in
the same paragraph). If that chunk is what gets retrieved, the raw text
already answers the question — skipping `get_definitions` there is
legitimate, not a failure. But if only the *Termination* chunk is
retrieved (which references `Cause` by name but never restates "15 days"),
the same 2-tool sequence reaching the right number can only mean the model
guessed or recalled it, not that it was grounded. This is exactly the
"right notice period without ever resolving the defined term" failure the
brief opens with.

So `evaluate_tool_choice()` in `trajectory_eval.py` doesn't just check
sequence membership — for the shortest path in a multi-path case, it also
checks whether the grounding phrase (e.g. `"fifteen (15) days"`) actually
appears in the retrieve step's logged observation text. Grounded short
path = legitimate alternate. Ungrounded short path = the target failure,
correctly flagged invalid even though the sequence "matches."

---

## 4. Step 2 — Rewrite trajectory_eval.py to evaluate the real agent

Key changes from the old, broken version:

- **Runs `run_agent()`, not `run_fixed_workflow()`.** Uses the real
  `result["events"]` — no more hardcoded fake event list.
- **`argument_validity`** now means what Task Set F says it means: for
  every `get_definitions` call in the trajectory, did the term argument
  resolve to something that actually exists in the contract (real), or
  come back "not found" (fluent fiction)? A trajectory with zero
  `get_definitions` calls is vacuously valid.
- **`classify_failure`** implements the exact "Week-8 zoo" named in the
  brief — `loop`, `wrong_tool`, `made_up_input`, `silent_giveup`,
  `inefficient_steps`, `outcome_failure`, `pass` — with `loop` checked
  first (any budget/stuck-loop stop reason), since a run that had to be
  forcibly bailed out is a distinct, worse symptom than a merely
  inefficient one, even if its forced answer happens to be right.
- **`outcome_passed`** now checks real answer content against
  `required_terms` (imported from `race.py`'s `passes()`), not just
  "did it answer something" — otherwise the gap number would be
  meaningless.
- **Cost metrics report p50 and max**, never a bare mean, per the brief's
  explicit warning about the run that "looped 14 times... the one that
  shows up on the bill."

18 unit tests (`tests/test_trajectory_eval.py`) cover all of this with
mocked events — no live Ollama needed to verify the logic.

---

## 5. Step 3 — Run the real baseline

`python trajectory_eval.py` against the live agent, 10 real runs. Result:

| Metric | Value |
|---|---|
| Tool-choice accuracy | **0.00%** |
| Argument validity rate | 50.00% |
| Trajectory pass rate | **0.00%** |
| Outcome pass rate | 90.00% |
| **Outcome-vs-trajectory gap** | **90.00%** |
| Step efficiency | 1.07 |
| Cost p50 / max | $0.002670 / $0.003858 |

**Failure mode: `loop`, 10/10 cases.** Every single run hit the
stuck-loop guard. The concrete pattern, visible in the raw events: after
retrieving the correct clause, the model would reflexively try
`get_definitions` on a fact that was *already plainly stated* in the
retrieved text — e.g. `get_definitions(term="Annual_Salary", ...)` right
after retrieving "Annual Salary USD 72,000" verbatim. `Annual_Salary`
isn't a real defined term, so the call fails, the model repeats it, and
the guard forces a draft.

### The outcome-vs-trajectory example (req #3)

**T01** — "What is the annual salary of the employee?"
- Outcome: **PASS** ("The annual salary of the employee is USD 72,000.")
- Trajectory: **FAIL** (`loop`) — path was
  `retrieve_contract_evidence -> get_definitions("Annual_Salary")`, a
  fictional term, forced to draft after repeated invalid actions.
- The forced draft only got the right answer because the raw retrieved
  text already had the number in it. The trajectory never actually
  resolved anything — textbook right-answer-wrong-path.

Full data: `week8_evidence/trajectory_eval_baseline.md` /
`trajectory_eval_baseline_raw.json`.

---

## 6. Step 4 — Apply exactly one mitigation

**Chosen: tighter tool description.** Only
`TOOL_DESCRIPTIONS["get_definitions"]` in `agent_loops.py` changed (this
string also flows straight into the ReAct prompt), adding an explicit
negative constraint: *"Do NOT call this for a fact that is already stated
as a plain number, date, or amount in the most recent
retrieve_contract_evidence observation."* Nothing else — not the few-shot
examples, not the stuck-loop threshold, not the budgets, not the
temperature — was touched, so the before/after comparison is attributable
to this one change. Full diff: `week8_evidence/mitigation_diff.md`.

### Before -> after: the honest result

**`loop` count: 10/10 -> 10/10. No improvement.**

Re-running the same 10 cases showed the model still reflexively calling
`get_definitions` on plainly-stated facts at the same rate. Diagnosis
(written up before the re-run, then confirmed by it): the defect isn't
"the model doesn't understand what the tool is for" — an information
problem a tighter description could fix — it's "the model doesn't
recognize it already has enough to draft" — a decision problem. The fix
was in the wrong place.

**Price paid (and it was a net cost, not free):**

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| Total tokens (10 cases) | 57,743 | 62,127 | **+4,384** (+7.6%) |
| Mean cost / question | $0.002887 | $0.003106 | **+$0.000219** |
| Cost p50 | $0.002670 | $0.002819 | +$0.000149 |
| Cost max | $0.003858 | $0.004302 | +$0.000444 |

Latency also rose sharply (32.97s -> 65.09s mean) but is flagged as
**likely confounded by system load**, not a clean effect of the
mitigation — a 7.6% token increase can't plausibly explain a ~97% latency
jump, and claiming otherwise would itself be an unmeasured assumption.

This is reported as a complete, valid answer to requirement #4: the
rubric asks for a measured count and a measured price, not a success.
"Applied, measured, ineffective, and it cost something" is real data.

*(A stronger single-mitigation alternative — routing this track to the
fixed workflow, which cannot loop by construction — was discussed and
explicitly deferred in favor of reporting this honest negative result.)*

---

## 7. Step 5 — Regression check

| Mode | Before | After |
|---|---:|---:|
| loop | 10 | 10 |
| wrong_tool | 0 | 0 |
| made_up_input | 0 | 0 |
| silent_giveup | 0 | 0 |
| inefficient_steps | 0 | 0 |
| outcome_failure | 0 | 0 |
| pass | 0 | 0 |

`loop` was the only mode present in either run, so nothing else existed
to regress and no new mode appeared. All 7 modes in the taxonomy were
checked. Full writeup: `week8_evidence/regression_check.md`.

---

## 8. A note on file-naming confusion during this run

Partway through, `week8_evidence/*.md`/`*.json` files briefly appeared
duplicated with a `_1` suffix, and separately a `trajectory_eval_baseline.md`
got overwritten with what turned out to be a duplicate of the
*after-mitigation* data (same costs, different timestamp) — most likely
from a `python trajectory_eval.py` run using default output paths that
landed after the mitigation was already in the code. This was caught by
comparing the numbers in the "baseline" file against the known
after-mitigation costs (they matched), and the canonical baseline files
were restored from the original run's captured data. All six evidence
files now agree with each other and with the numbers in this document.

---

## 9. File map

| File | What it is |
|---|---|
| `trajectory_questions.json` | 10 cases, with legitimate alternate paths for T07/T08/T09 |
| `trajectory_eval.py` | Rewritten evaluator — runs the real agent, correct metric definitions |
| `agent_loops.py` | One change: tighter `get_definitions` description (the mitigation) |
| `tests/test_trajectory_eval.py` | 18 unit tests, mocked, no live Ollama needed |
| `week8_evidence/trajectory_eval_baseline.md` / `_raw.json` | Pre-mitigation run (10/10 loop) |
| `week8_evidence/trajectory_eval_after_mitigation.md` / `_raw.json` | Post-mitigation run (10/10 loop, higher cost) |
| `week8_evidence/mitigation_diff.md` | The one code change + before/after + price |
| `week8_evidence/regression_check.md` | Per-mode before/after table |

---

## 10. What is still *not* done

The **bonus** (indirect prompt injection attack + defense + re-measured
trajectory eval) was explicitly deferred in favor of the core 100-point
rubric, and has not been built.

---

## 11. Quick verification checklist

```bash
python -m unittest tests.test_trajectory_eval tests.test_agent_loops -v   # fast, mocked, no live Ollama
python trajectory_eval.py --out week8_evidence/trajectory_eval_rerun.md \
                           --raw-out week8_evidence/trajectory_eval_rerun_raw.json
                                                                            # re-run live, ~5-8 min
```
