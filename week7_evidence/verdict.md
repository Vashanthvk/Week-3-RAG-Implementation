# Verdict

Fixed workflow wins on all four numbers: 100% pass vs 90%, 2.75s vs 24.2s p50
latency, 4,564 vs 56,671 total tokens, $0.0002 vs $0.0028 per question. Per
the decision rule (does the path vary by input?), none of the 10 questions
-- including the three defined-term-chase ones (MSA Cause/Notice Period, SLA
Initial Term) -- needed dynamic re-planning: the second lookup is knowable
in advance from a small, enumerable vocabulary of defined-term names, so the
fixed workflow resolves it with a static keyword check, not an LLM decision.
The agent's one loss (NDA term length) came from its own freedom: it
rewrote the query to "effective date" and retrieved the wrong contract, then
chased an unrelated term -- a mistake fixed, full-question retrieval can't
make. Ship the fixed workflow here; keep the agent loop only for a
defined-term vocabulary too open-ended for a static table.

(144 words)
