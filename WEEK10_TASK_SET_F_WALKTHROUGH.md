# Week 10 · Task Set F — Multi-Agent and A2A Walkthrough

## Goal

Week 10 compares the existing single contract agent with a small contract squad. The decision is evidence-led: keep the squad only if it improves answer quality without unacceptable latency, token, or cost overhead.

## What was built

`multi_agent.py` implements a local manager-and-worker workflow:

1. The **orchestrator** receives the question and delegates clause retrieval.
2. The **clause worker** retrieves grounded contract evidence and returns the selected contract version.
3. When the question names defined terms, the orchestrator delegates up to two lookups to the **defined-terms worker**.
4. The **answer worker** drafts a grounded answer from the retrieved evidence and definitions.
5. Every delegation is retained as a handoff with sender, receiver, status, and estimated token count.

The implementation deliberately reuses the Week 7 retrieval and grounding controls. It does not introduce a second, inconsistent source of contract truth.

## A2A-style contract

The squad exposes an agent card through `agent_card()`:

- Name: `contract-squad-orchestrator`
- Skills: contract-clause retrieval, defined-term lookup, and grounded answer drafting
- Input/output: plain text and JSON
- Authentication: none, because this is a local evaluation workflow

This is an A2A-style capability description rather than a deployed network service. The handoffs are local Python calls, so the evidence demonstrates delegation boundaries and task state, not cross-process transport.

## Run it

```powershell
venv\Scripts\activate
ollama serve
python multi_agent_race.py
```

The race runs the ten fixed cases from `race_questions.json` through both arms:

- `run_agent` — the pre-existing single-agent baseline
- `run_orchestrator` — the manager plus specialist workflow

To use the UI instead, run `streamlit run app.py`, select **Week 10 · Multi-agent and A2A**, then choose either **Contract squad** for one question or **Race evidence** to regenerate the benchmark.

## Results and decision

The checked-in race evidence reports:

| Metric | Single agent | Contract squad |
|---|---:|---:|
| Pass rate | 90.0% | 100.0% |
| p50 latency | 27.2372 s | 2.856 s |
| p99 latency | 45.9793 s | 9.7419 s |
| Total tokens | 62,127 | 10,619 |
| Cost/question | $0.003106 | $0.000531 |

The verdict is **keep**: on this fixed benchmark, the squad increased pass rate by 10 percentage points while using fewer tokens and lower estimated cost. These are recorded benchmark results, not a guarantee for a new model, machine, or contract set; regenerate the race before making a production decision.

## Failure handling

Case 7 deliberately injects a defined-terms worker HTTP 500. The orchestrator records the failed handoff and returns a `degraded_partial_answer`; it does not invent a definition or silently represent the answer as complete. The current implementation does not retry that worker—this is an explicit limitation and a natural next improvement.

## Evidence map

| Evidence | Purpose |
|---|---|
| `race_evidence/race_table.md` | Quality, latency, token, and cost comparison |
| `race_evidence/handoffs.log` | One JSON record per worker handoff |
| `race_evidence/multiplier.md` | Context re-send multiplier and largest handoff |
| `race_evidence/failure_case.md` | Injected worker-failure behavior |
| `race_evidence/agent_card.json` | Capability contract for the contract squad |
| `race_evidence/a2a_failure_mapping.md` | A2A failure-state mapping note |
| `race_evidence/verdict.md` | Keep/kill conclusion |

## Verification

```powershell
python -m unittest tests.test_multi_agent
python multi_agent_race.py
```

The unit tests validate the agent card, handoff shape, failure handling, and race calculations. The race requires the local embedding/model dependencies and Ollama to be available.
