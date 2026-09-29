# Error path: before vs after (req #5)

Same failing call in both cases: `get_definitions(term="Force Majeure", contract_version="Master_Service_Agreement")` -- "Force Majeure" genuinely is not a defined term in this contract, so this is a real, correct failure, not a simulated one.

## BEFORE -- unrecoverable error

Server response:
```json
{
  "found": false,
  "error": "Error 3"
}
```

Model's next thought:
```text
Thought: This observation indicates that the Force Majeure event is not explicitly defined in the Master Services Agreement, and the error code suggests that there may be a missing or unclear provision related to this term.

Next action: draft the answer now
```

Note the model's stated conclusion here is UNGROUNDED: it guesses that
"Error 3" means the term isn't defined, but "Error 3" carries no
information that actually says that. This is the real risk of an
unrecoverable error: not that the model visibly gets stuck, but that it
fills the gap with a confident-sounding hallucination instead of a fact.

## AFTER -- recoverable error

Server response:
```json
{
  "found": false,
  "error": "'Force Majeure' is not a defined term in Master_Service_Agreement. This contract's defined terms are: Cause, Notice Period, Renewal Term."
}
```

Model's next thought:
```text
Thought: This observation tells me that the contract does not explicitly define "Force Majeure" as a term, which means it may not be explicitly covered under the Master Services Agreement.

Next action: draft the answer now
```

Here the model reaches the same practical conclusion, but for the right
reason: the server's own message states plainly that Force Majeure is not
defined, which is a verified fact, not a guess. That distinction --
grounded conclusion vs. a lucky-looking hallucination -- is exactly the
"right answer, wrong path" risk from Week 8, now traced back one layer
further to where it can start: an opaque error at the tool boundary.

## The docstring rewrite (also req #5)

`get_definitions`'s docstring in `mcp_servers/clause_search_server.py` is
written as a prompt, not a comment -- it tells the calling model exactly
when to use this tool vs. `retrieve_contract_evidence`, and what
`contract_version` must be. This exact text is what `tools/list` returns
in `description` -- see `wire.json`.
