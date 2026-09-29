# Week 7 · Task Set F — End-to-End Walkthrough

Legal contracts track: "Race the contract agent against a fixed workflow."
This document explains, step by step, what was built, why, and how to
verify it yourself.

---

## 1. Where we started

The repo already had a Week 6/7 "agent loop" (`agent_loops.py`), but it did
not actually satisfy Task Set F:

- Only **two tools** existed (`retrieve_contract_evidence`,
  `draft_grounded_answer`). No third tool.
- The "agent" was not agentic: `run_agent()` was a hard-coded Python
  `while` loop that always called retrieve then draft in a fixed order.
  **No LLM ever decided which tool to call next.** That is the literal
  definition of "not agentic," and it also meant `run_agent()` and
  `run_fixed_workflow()` were doing almost the same thing.
- `estimated_cost` was `tool_calls * 0.001` — a flat constant, not a real
  token count. `max_tokens` was not enforced at all (only 3 of the
  required 4 budgets existed).
- The 3 existing contracts (Employment, Lease, NDA) had no Definitions
  section and no way to ask a question where a second lookup depends on
  what the first one found — so there was no way to build the 3 required
  dependency questions.
- There was no race harness, no `race.csv`, no budget-termination log, no
  third-tool diff, no verdict.

In short: the pieces existed, but the actual graded deliverables did not.

---

## 2. What Task Set F requires (recap)

1. A **third tool** (`get_definitions` or `compare_versions`) — one job,
   an enum for the version/contract parameter, no overlap with the other two.
2. A **fixed workflow** doing the identical task — same tools, same model,
   same output contract, no loop.
3. A **race** over 10 questions (≥3 requiring a second, dependent lookup),
   reporting **pass rate, p50 latency, total tokens, cost/question** for
   both systems.
4. All **four budgets** (iterations, tokens, cost, wall-clock) enforced in
   code, plus a log of one run that hits a budget and terminates cleanly.
5. A **verdict** (<150 words) applying the decision rule to a *named*
   question class, consistent with the actual numbers.

---

## 3. Step 1 — Build fixture contracts that need a second lookup

The existing 3 contracts were too simple (no Definitions section, no
defined terms). Two new one-page contracts were generated
(`scripts/generate_fixture_contracts.py`, using `fpdf2`) and added to
`contracts/`:

- **`Master_Service_Agreement.pdf`** — defines `"Cause"` (a breach not
  cured within **15 days**) and `"Notice Period"` (**30 days**). The
  Termination clause *references* these terms by name but never restates
  the day counts — you have to look them up.
- **`Software_License_Agreement.pdf`** — defines `"Initial Term"`
  (**12 months** from the Effective Date) and `"Termination Notice
  Period"` (**45 days**), same pattern.

`chroma_db/` was rebuilt (`python ingest.py`) so both new contracts are
indexed alongside the original three (8 total chunks → 9 after fixture
fixes).

---

## 4. Step 2 — Add the third tool: `get_definitions`

`agent_loops.get_definitions(term, contract_version)`:

- `contract_version` is a real enum, checked against `CONTRACT_VERSIONS`
  (the 5 contract names). An unknown value returns
  `{"found": False, "error": "unknown_contract_version"}` rather than
  guessing.
- It concatenates that one contract's chunks, normalizes whitespace, and
  regex-searches for `"<term>" means ...` — a targeted, single-job lookup,
  not a second search tool.
- If the exact term isn't found, a **deterministic fuzzy fallback**
  (`_fuzzy_match_known_term`) checks word overlap between the query and
  each of that contract's real defined terms + their definition text, and
  resolves to the best match. This exists because the small local model
  sometimes asks for a paraphrase (e.g. "cure period") instead of the
  contract's actual term name ("Cause") — see §7.

All three tool descriptions were rewritten so each names one job and
explicitly disclaims the other two (full before/after in
`week7_evidence/third_tool_diff.md`).

`security_controls.ALLOWED_TOOLS` was updated to allowlist the new tool
(easy to miss — the security gate blocks any non-allowlisted tool name).

---

## 5. Step 3 — Make the agent actually agentic (ReAct loop)

`run_agent()` was rewritten around a hand-rolled ReAct loop where the
**model itself** picks the next tool:

1. Each turn, `_build_react_prompt()` shows the model the 3 tool
   descriptions, two worked few-shot examples (one that needs no lookup,
   one that does), the transcript so far, and a hint listing any known
   defined-term names found in the *question's own wording*.
2. `_call_llm()` calls `ollama.generate()` directly (not the LangChain
   wrapper) so every call's **real token usage**
   (`prompt_eval_count` + `eval_count`) is captured — not an assumed
   constant.
3. `_parse_react_response()` extracts `Action` / `Action Input` via regex.
4. The chosen tool runs; its result is summarized and appended to the
   transcript for the next turn.
5. Loop ends when the model calls `draft_grounded_answer` (which composes
   the final answer and is terminal), or a budget stops it.

Two safety nets were added after real testing showed the 3B local model
can get stuck:

- **Repetition/duplicate-call guard** — `retrieve_contract_evidence` may
  only run once per question; an identical repeated call is skipped with
  a corrective message instead of silently re-executing.
- **Stuck-loop guard** — after 2 consecutive skipped/invalid actions, the
  loop **forces** `draft_grounded_answer` with whatever evidence exists
  rather than spinning out the token budget. This is a deliberate design
  choice, not a bug: it guarantees a clean, bounded answer even when the
  model can't self-correct.

---

## 6. Step 4 — Deterministic date math (shared by both systems)

A 3B local model is not reliable at date arithmetic. `compute_grounded_facts()`
does the math in code (day/month arithmetic from a resolved definition's
number + an anchor date) and hands the model an already-computed fact to
restate. **Both** `run_agent()` and `run_fixed_workflow()` call this same
helper before drafting, so the race compares *tool-selection strategy*,
not *who can add 15 days to a date*.

---

## 7. Step 5 — Question-text term detection (not chunk-content guessing)

Early versions tried to decide "does this need a second lookup?" by
scanning the *retrieved chunk*. That failed: a contract's Definitions
chunk states multiple terms side by side (e.g. `Cause` = 15 days *and*
`Notice Period` = 30 days in the same paragraph), so reading the chunk
alone is a coin flip about which one the question actually needs.

Fix: `question_defined_terms(question)` reads the **question's own
wording** for known defined-term names. Both systems use it:

- The **fixed workflow** uses it directly, deterministically, to decide
  whether (and which) term to resolve via `get_definitions` — this is
  what keeps it a genuine "fixed sequence" (a static keyword check against
  a small enumerable vocabulary), not a hidden loop.
- The **agent** gets it as a hint line in its prompt, but is still free to
  ignore it (it's an agent, not a script).

---

## 8. Step 6 — The fixed workflow

`run_fixed_workflow()` is a straight-line, bounded sequence with **no
`while` loop and no model-made routing decision**:

1. Always: `retrieve_contract_evidence` (once).
2. Only if `question_defined_terms(question)` finds a known term name in
   the question **and** retrieval identified a valid contract: call
   `get_definitions` for it (capped at 2 terms — a fixed, compile-time
   bound, not dynamic re-planning).
3. Always: `draft_grounded_answer` (once).

Same tools, same model, same output contract as the agent — the only
difference is *who decides the sequence* (static Python code vs. the LLM).

---

## 9. Step 7 — The 10-question race

`race_questions.json` — 10 questions across all 5 contracts, 3 flagged
`"dependency": true`:

| # | Question | Needs a 2nd lookup? |
|---|---|---|
| 1,2,4,5,6,10 | Direct facts (salary, rent, deposit, sick leave, effective dates) | No |
| 3 | NDA term length | No |
| 7 | MSA — Cause cure-period deadline | **Yes** (`Cause` → 15 days) |
| 8 | MSA — convenience-termination deadline | **Yes** (`Notice Period` → 30 days) |
| 9 | SLA — Initial Term length + Termination Notice Period | **Yes** (2 separate terms) |

`race.py`:
- Runs every question through `run_agent` and `run_fixed_workflow`.
- Pass/fail checked against `expected_keywords` (substring match, with
  OR-groups for phrasing variants — see Q9's two-part check).
- Aggregates **pass rate, p50 latency (`statistics.median`), summed real
  tokens, mean cost** per system.
- Writes `week7_evidence/race.csv` (the 8-number summary table),
  `race_details.csv` (per-question detail), `race_report.md` (both,
  rendered as markdown).

**Latest confirmed run:**

| system | pass_rate | p50_latency_s | total_tokens | cost_per_question |
|---|---|---|---|---|
| agent | 0.9 | 24.18 | 56,671 | 0.002834 |
| fixed_workflow | 1.0 | 2.75 | 4,564 | 0.000228 |

Fixed workflow wins on all four numbers — see §11 for why the one agent
failure happened and why it was left in rather than patched away.

---

## 10. Step 8 — Budgets

`LoopBudget` has all four required limits, all checked in
`_budget_exceeded()` before (and after) every model call inside
`run_agent()`:

| Budget | Field | Stop reason |
|---|---|---|
| Iterations | `max_steps` | `max_iterations` |
| Wall-clock | `max_seconds` | `max_wall_clock` |
| Tokens | `max_tokens` (real, from Ollama's own counts) | `max_tokens` |
| Cost | `max_cost` (derived from those same real tokens) | `max_cost` |

`week7_evidence/budget_termination_log.md` captures one real run
(`LoopBudget(max_tokens=600)` against a dependency question) hitting
`max_tokens` and stopping cleanly: no exception, no further model calls,
empty answer, `tool_calls: 0`. All four are additionally covered by
`AgentLoopBudgetTests` in `tests/test_agent_loops.py` with a mocked model
call (so they run in milliseconds, no live Ollama needed).

---

## 11. Step 9 — The one agent failure (Q3, NDA) — explained, not patched

Question 3 asks about the NDA's term length. The agent rewrote its own
search query down to `"effective date"` instead of using the full
question. That shorter query's top match happened to be the MSA (which
also has a prominent "Effective Date" section), so the agent chased the
wrong contract's defined terms and, via the stuck-loop guard, correctly
refused: *"I don't know based on the provided contracts."*

This is reproducible (confirmed in two separate race runs) and was
**deliberately left in** rather than prompt-engineered away: it's the
clearest, most honest evidence for the verdict. The fixed workflow always
searches with the user's literal question, so it can't make this mistake
— that asymmetry is real, not manufactured.

---

## 12. Step 10 — The verdict

`week7_evidence/verdict.md` (144 words) applies the decision rule ("does
the path vary by input?") to the defined-term-chase question class and
concludes: even those 3 dependency questions don't need dynamic
re-planning, because the vocabulary of defined terms is small and
enumerable — a static keyword check handles it. Ship the fixed workflow;
reserve the agent loop for a genuinely open-ended term vocabulary.

---

## 13. Step 11 — Make everything runnable and testable

- **`run_contract_agent.py`** — one command per system:
  ```
  python run_contract_agent.py --system agent  --question "..."
  python run_contract_agent.py --system fixed  --question "..."
  ```
- **`tests/test_agent_loops.py`** — fully rewritten: `get_definitions`
  (exact match, not-found + hint, fuzzy fallback, unknown contract),
  `question_defined_terms`, all 4 budgets, fixed-workflow determinism
  (bounded tool-call counts, no loop), `compare_workflows` compatibility.
  15 tests, all mocked (no live Ollama), run in ~0.05s.
- **`tests/test_security_integration.py`** — fixed a stale assertion that
  hardcoded the old 2-tool allowlist (it now imports
  `security_controls.ALLOWED_TOOLS` instead of duplicating the list, so it
  won't go stale again if a 4th tool is ever added).
- Full regression suite: **41/41 passing.**

---

## 14. File map

| File | What it is |
|---|---|
| `agent_loops.py` | Agent (ReAct loop), fixed workflow, tools, budgets, date math |
| `rag.py` | Added `generate_answer_with_usage()` (real token counts via `ollama.generate`) |
| `security_controls.py` | `ALLOWED_TOOLS` now includes `get_definitions` |
| `scripts/generate_fixture_contracts.py` | Generates the 2 new contract PDFs |
| `contracts/Master_Service_Agreement.pdf`, `Software_License_Agreement.pdf` | New fixtures with Definitions sections |
| `race_questions.json` | The 10 race questions |
| `race.py` | Race harness — writes the evidence CSVs/report |
| `run_contract_agent.py` | Single-command CLI for either system |
| `tests/test_agent_loops.py` | Rewritten unit tests |
| `tests/test_security_integration.py` | Allowlist test fixed |
| `week7_evidence/race.csv`, `race_details.csv`, `race_report.md` | Race numbers |
| `week7_evidence/budget_termination_log.md` | Clean budget-stop demonstration |
| `week7_evidence/third_tool_diff.md` | Tool description before/after |
| `week7_evidence/verdict.md` | The graded verdict paragraph |

---

## 15. What is still *not* done

The **bonus** (sliding-window context + summarization surviving a 30-turn
conversation, persisting the effective date across a process restart,
re-racing on 3 long conversations) was explicitly deferred earlier in
favor of the core 100-point rubric, and has not been built.

---

## 16. Quick verification checklist

```bash
python -m unittest tests.test_agent_loops -v      # fast, mocked, ~0.05s
python -m unittest discover -s tests -v           # full suite, ~3 min, needs Ollama running
python race.py                                    # regenerate the race evidence
ollama ps                                          # if anything hangs, check the model isn't stuck "Stopping..."
```
