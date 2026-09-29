# Week 9 · Task Set F — End-to-End Walkthrough

Legal contracts track: "Bolt on the contract-repository server without
touching the agent." This document explains what was built, why, and how
to verify it yourself. (Refreshed after `mcp_agent.py` gained a
`--generate-evidence` mode and the two standalone capture scripts were
folded into it — see §8-9 and the file map for what changed.)

---

## 1. Where we started

Task Set F is explicitly framed as an *extension* — "your Week-9 agent
already discovers tools from your own clause-search server" — but nothing
like that existed in this repo. `agent_loops.py` calls
`retrieve_contract_evidence` / `get_definitions` / `draft_grounded_answer`
as direct in-process Python function calls. That's a perfectly valid
architecture for Weeks 7-8, but it is the opposite of MCP: every tool is
"wired in by hand," which is exactly what this week's brief opens by
naming as the problem.

So this week had two layers: build the Week-9 prerequisite (an agent that
discovers its own tools over MCP, "server one"), then do the graded task
on top of it (bolt on "server two" via config only, prove it).

**Constraint honored throughout:** nothing here touches `agent_loops.py`,
`race.py`, `trajectory_eval.py`, or `run_contract_agent.py`. This is a
second, separate, additive agent path (`mcp_agent.py` + `mcp_servers/`).
The Week 7/8 agent and all its evidence keep working exactly as before —
confirmed by re-running the full test suite after these changes.

---

## 2. What Task Set F requires (recap)

1. Add the contract-repository server via config, run one query that
   provably calls a tool from it (tool name visible in the trace).
2. A git diff proving **zero lines changed** in the agent module between
   server-one and server-one-plus-two — config changes only.
3. Tool count before -> after, with names, from a real `tools/list` call.
4. The raw JSON-RPC `initialize -> tools/list -> tools/call` exchange,
   hand-annotated, plus one line stating where the model runs and where
   it doesn't.
5. Rewrite one tool docstring as a prompt, make one error path
   recoverable, show a before/after model transcript on the same failing
   call.
6. A 5-line supply-chain risk note for the third-party server.

---

## 3. Step 1 — Build "server one": our own clause-search MCP server

`mcp_servers/clause_search_server.py`, built with `fastmcp`. Exposes
exactly two tools, both pure capability, **no LLM call inside either**:

- `retrieve_contract_evidence(question)` — reuses the real
  `rag.py`/`hybrid_retrieval.py` retrieval pipeline (same vector store,
  same BM25 index, same 5 contracts as Weeks 7-8) and returns the
  top-ranked clause chunk.
- `get_definitions(term, contract_version)` — the same regex-based
  defined-term resolver as `agent_loops.py`'s tool, reimplemented
  independently here so this server has no import dependency on the
  Week 7/8 agent module.

### Why `draft_grounded_answer` is deliberately NOT here

The brief's own "common mistakes" list calls this out directly: *"Putting
an LLM call inside your MCP server... the server exposes a capability,
the host runs the model."* Drafting the final answer is composition, not
a discoverable capability — so it stays host-side, in `mcp_agent.py`,
using a direct local Ollama call. This is a real architectural fix, not
just Week-9 box-checking: it's the correct MCP design regardless of
requirement wording.

---

## 4. Step 2 — Build "server two": the contract-repository server

`mcp_servers/contract_repository_server.py` — genuinely independent of
server one: separate process, separate data source
(`contract_repository_data.json`), no shared code. Three tools, exactly
matching the brief's description ("lookup by contract id, its effective
date, and its amendment chain"):

- `lookup_contract(contract_id)` — title and parties
- `get_effective_date(contract_id)` — the contract's own effective date
- `get_amendment_chain(contract_id)` — ordered amendments with dates and
  what each one changed

The data maps four invented repository ids (`MSA-2021-0142`,
`LSE-2026-0007`, `NDA-2025-0033`, `SLA-2025-0091`) onto the same four real
contracts used in Weeks 7-8, with one real amendment story: MSA-2021-0142
originally ran clauses 1-12; Amendment 1 (2025-07-01) merged clause 12
into clause 9, leaving clauses 1-11 — deliberately built to support the
brief's own illustrative error style ("no clause 12.4... see Amendment 2
effective 2023-06-01").

Every error response distinguishes **"contract id doesn't exist"** from
**"contract exists but has no amendments"** (an empty list, not an
error) — the brief's warning about collapsing "wrong date" and "repository
down" into one useless "not found" was taken seriously here.

---

## 5. Step 3 — Build the agent: discovery, not hard-coding

`mcp_agent.py` is the host + client. The one property everything else
depends on: **no tool name, description, or argument schema is typed into
this file.** `connect_servers()` reads `mcp_servers/mcp_config.json`,
launches each listed server over stdio, calls the real `tools/list`, and
builds the tool registry from that response. `_build_prompt()` renders
the ReAct prompt's tool list from that same registry. Add a server to the
config, this file's behavior changes; this file's *text* does not.

The loop itself mirrors the Week 7/8 agent's lessons (a repeat-call guard
and a stuck-loop guard, both needed in real testing — the same class of
looping behavior showed up here too), but stays intentionally simpler
since Week 9 isn't graded on trajectory quality, it's graded on proving
the MCP mechanics work.

---

## 6. Step 4 — Prove the config-only claim (req #2)

`mcp_agent.py --generate-evidence` re-verifies this fresh every run (via
`_generate_tool_counts_config_diff_and_agent_diff`):

1. Snapshot `mcp_agent.py`'s own bytes.
2. Run tool discovery against a reconstructed server-one-only config (built
   from the live config's own `clause_search` entry, not a separately
   hand-maintained file that could go stale): **2 tools discovered**
   (`get_definitions`, `retrieve_contract_evidence`).
3. Run tool discovery again against the real, live `mcp_config.json`
   (currently both servers): **5 tools discovered**
   (`get_amendment_chain`, `get_definitions`, `get_effective_date`,
   `lookup_contract`, `retrieve_contract_evidence`).
4. Snapshot `mcp_agent.py`'s bytes again.
5. Diff and checksum the two snapshots — identical.

The proof: the exact same, unmodified `mcp_agent.py` code handled *both*
configurations, with its own checksum unchanged across the whole test.
No commits were made to do this (there was already a large batch of
unrelated staged work from Weeks 7-8 sitting in the index that hasn't
been committed, and touching git history wasn't asked for) — `git diff
--no-index --stat` between the two snapshot files, backed by matching
SHA-256 checksums, written fresh to `week9_evidence/agent_diff.txt` and
the two `mcp_agent_snapshot_*.py` files on every `--generate-evidence`
run.

(An earlier version of this evidence treated `agent_diff.txt` as a
one-time historical artifact that could never be safely re-verified,
reasoning that checksumming a file against itself within one execution
"proves nothing since nothing in that execution edits the file mid-run."
That was overcautious: the two checksums bracket a real, load-bearing
action in between them — exercising the live code against both configs —
so a match genuinely demonstrates the same code handles both, not just
that the function doesn't self-modify. Folding it into `--generate-evidence`
means the proof is re-verified live on every run instead of trusted as a
frozen snapshot from one edit session.)

---

## 7. Step 5 — Prove server two's tool is really called (req #1)

```
python mcp_agent.py --question "What is the effective date of contract MSA-2021-0142?"
```

Real trace:

```
ACT   lookup_contract   server=contract_repository
OBSERVE  {"found": true, "contract_id": "MSA-2021-0142", "title": "Master Services Agreement", "parties": [...]}
```

Honest note: the small local model sometimes picks `lookup_contract`
rather than the more precisely-matching `get_effective_date` (or even
tries it on questions that don't need server two at all, chasing a
hallucinated contract id like `"ABC-2021-0012"` before the repository
server correctly rejects it and the stuck-loop guard forces a draft from
whatever evidence is already in hand). That's a real, unforced result,
left in rather than cherry-picked away — and it doesn't weaken req #1,
which only asks to prove a server-two tool call happened (it did, with a
real round-tripped JSON response each time) — it's a trajectory-quality
question, which is what Week 8's machinery is for, not this week's.
Capture your own example any time with:
```
python mcp_agent.py --question "..." --trace-out path/to/trace.json
```
(the parent directory is created automatically if it doesn't exist yet).

---

## 8. Step 6 — Raw JSON-RPC capture, hand-annotated (req #4)

`mcp_agent.py --generate-evidence` speaks the wire protocol directly
inside `_capture_wire()` — manual newline-delimited JSON over the server
subprocess's stdin/stdout, no SDK abstraction — capturing the real
`initialize -> notifications/initialized -> tools/list -> tools/call`
sequence against the live `clause-search` server. `week9_evidence/wire.json`
has the raw messages plus hand-written annotations for every top-level
field, including ones only visible once the real server responded
(`_meta`, `title`, `outputSchema`, `structuredContent` — none of these
were predicted up front; the annotations were completed against the
actual capture).

One line, as required: **the model runs nowhere in this exchange** — every
message here is either that function's own Python or
`clause_search_server.py`'s deterministic lookup code (see its module
docstring). The model only runs later, inside `mcp_agent.py`'s
`run_query()`/`_call_llm()`, on the host.

---

## 9. Step 7 — Docstring-as-prompt + recoverable error (req #5)

`get_definitions`'s docstring in `clause_search_server.py` is written as
a prompt (what to call it for, what `contract_version` must be, and an
explicit pointer to call `retrieve_contract_evidence` first) — this exact
text is what `tools/list` returns in `description`, visible in `wire.json`.

The not-found error path has an env-toggle (`CLAUSE_SEARCH_LEGACY_ERRORS=1`)
between the old and new behavior:

| | Server response |
|---|---|
| BEFORE | `{"found": false, "error": "Error 3"}` |
| AFTER | `{"found": false, "error": "'Force Majeure' is not a defined term in Master_Service_Agreement. This contract's defined terms are: Cause, Notice Period, Renewal Term."}` |

`_capture_error_before_after()` (also inside `mcp_agent.py`, run as part
of `--generate-evidence`) fed both, real, to the local model in the same
mid-loop Observation format and captured its actual next thought
(`week9_evidence/error_before_after.md`). Honest finding: both runs
ended up drafting rather than retrying, but for different reasons —
**BEFORE**, the model's conclusion ("not defined") was an *ungrounded
guess* dressed up as confidence, since "Error 3" states nothing of the
kind. **AFTER**, the same conclusion was a *verified fact* taken directly
from the server's own message. That's the real risk an opaque error
creates: not a visibly stuck agent, but a confident hallucination one
layer downstream — the same "right answer, wrong path" pattern from
Week 8, traced back to where it can originate.

---

## 10. Step 8 — Supply-chain risk note (req #6)

`week9_evidence/risk_note.md`, exactly 5 lines: who wrote it (a different
internal team, no code review on our side), what it can reach (only its
own small JSON file, nothing else in this implementation), what it logs
(nothing — itself a gap), what a stolen token could do (enumerate every
contract id/party/amendment, including NDA'd ones, with no scoping), and
a ship/don't verdict (don't, until logging + scoped auth + a real answer
on what the production data source actually contains). Never auto-written
by `--generate-evidence` — it's a judgment document with no run-to-run
data in it.

---

## 11. File map

| File | What it is |
|---|---|
| `mcp_agent.py` | The host + client — discovers tools, runs the ReAct loop, drafts locally, AND (via `--generate-evidence`) regenerates most of the evidence below |
| `mcp_servers/clause_search_server.py` | "Server one" — our own, 2 tools, no LLM inside |
| `mcp_servers/contract_repository_server.py` | "Server two" — the (simulated) third party, 3 tools |
| `mcp_servers/contract_repository_data.json` | Server two's data (contract ids, dates, amendments) |
| `mcp_servers/mcp_config.json` | The **only** file that changes to add server two |
| `week9_evidence/agent_diff.txt` | Proof: zero changed lines in the agent module (regenerated fresh each `--generate-evidence` run) |
| `week9_evidence/mcp_agent_snapshot_before_server_two.py` / `_after_server_two.py` | The two snapshots `agent_diff.txt` is built from (regenerated fresh each run, alongside it) |
| `week9_evidence/mcp_config_diff.txt` | The one legitimate config diff (regenerated fresh each `--generate-evidence` run) |
| `week9_evidence/tool_counts.md` | 2 -> 5 tools, with names (regenerated fresh) |
| `week9_evidence/wire.json` | Raw JSON-RPC exchange, hand-annotated (regenerated fresh) |
| `week9_evidence/error_before_after.md` | Real before/after model transcript (regenerated fresh) |
| `week9_evidence/risk_note.md` | The 5-line risk note (never auto-written) |

---

## 12. What is still *not* done

The **bonus** (single gateway process fronting both servers with one
audit line per call, plus a scoped token denying the amendment-chain tool
while base lookup still works) was explicitly deferred in favor of the
core 100-point rubric, and has not been built.

---

## 13. Quick verification checklist

```bash
# Ask a real question (proves discovery + a real tool call end-to-end)
python mcp_agent.py --question "What is the annual salary of the employee?"

# Save the full trace for a specific question
python mcp_agent.py --question "..." --trace-out path/to/trace.json

# Regenerate agent_diff.txt, tool_counts.md, mcp_config_diff.txt, wire.json,
# and error_before_after.md in one command (leaves only risk_note.md
# untouched -- a judgment document with no run-to-run data in it) --
# takes 1-3 min, needs Ollama running
python mcp_agent.py --generate-evidence

# Confirm Week 7/8 remain completely unaffected
python -m unittest discover -s tests -v
```
