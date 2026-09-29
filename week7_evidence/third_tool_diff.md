# Third tool: description diff

Task Set F requirement #1: add a third tool (`get_definitions`) whose
description names exactly one job, uses an enum for the contract-version
parameter, and does not overlap the two existing tool descriptions.

## Before (Week 6, two tools)

```python
TOOL_DESCRIPTIONS = {
    "retrieve_contract_evidence": "Retrieve and rank contract chunks for a legal question.",
    "draft_grounded_answer": "Draft an answer using only the retrieved contract evidence.",
}
```

## After (Week 7 / Task Set F, three tools)

```python
CONTRACT_VERSIONS = [
    "Employment_Agreement",
    "Lease_Agreement",
    "Non_Disclosure_Agreement",
    "Master_Service_Agreement",
    "Software_License_Agreement",
]

TOOL_DESCRIPTIONS = {
    "retrieve_contract_evidence": (
        "Search across all ingested contracts and return the top-ranked "
        "clause chunks relevant to a legal question. Does not look up a "
        "defined term's meaning and does not draft an answer."
    ),
    "get_definitions": (
        "Look up the literal meaning of ONE named defined term (for "
        "example 'Cause' or 'Notice Period') inside a single contract's "
        "Definitions section, chosen with the contract_version enum: "
        f"{CONTRACT_VERSIONS}. Does not search broadly across contracts "
        "and does not draft an answer."
    ),
    "draft_grounded_answer": (
        "Compose the final answer strictly from clause evidence and/or "
        "defined-term lookups already gathered earlier in this run. Does "
        "not search or look anything up itself; call it last."
    ),
}
```

## Why there is no overlap

Each description states one job and explicitly disclaims the other two:

| Tool | Job | Explicitly does NOT do |
|---|---|---|
| `retrieve_contract_evidence` | broad search across every contract for relevant clauses | look up a defined term's meaning; draft an answer |
| `get_definitions` | resolve ONE named defined term inside ONE named contract | search broadly; draft an answer |
| `draft_grounded_answer` | compose the final answer from evidence already gathered | search; look anything up |

`get_definitions(term: str, contract_version: str)` takes a real enum
parameter, `contract_version`, restricted at call time to the five values in
`CONTRACT_VERSIONS` (`agent_loops.get_definitions` rejects anything else with
`{"found": False, "error": "unknown_contract_version"}` rather than silently
guessing a contract). This is what makes it a targeted, single-job lookup
tool rather than a second, narrower version of `retrieve_contract_evidence`:
it never ranks or searches chunks, it does a direct regex resolution of one
term's defining sentence inside one named contract's text.

*(Note: `TOOL_DESCRIPTIONS["get_definitions"]` gained one more sentence in
Week 8 as a trajectory-eval mitigation -- see week8_evidence/mitigation_diff.md
for that later change. This file documents Week 7's diff in isolation.)*
