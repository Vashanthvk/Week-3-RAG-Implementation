# Week 8 Baseline Trajectory Evaluation (pre-mitigation)

## Summary

- Cases evaluated: 10
- Tool-choice accuracy: 0.00%
- Argument validity rate: 50.00%
- Trajectory pass rate (tool-choice AND argument valid): 0.00%
- Outcome pass rate: 90.00%
- **Outcome-vs-trajectory gap: 90.00%**
- Average step efficiency (steps taken / steps needed): 1.07
- Cost per question -- p50: $0.002670
- Cost per question -- max: $0.003858

## Per-case results

| ID | Dep? | Tool Path | Actual Path | Args | Outcome | Steps | Needed | Eff. | Cost | Mode |
|---|---|---|---|---|---|---:|---:|---:|---:|---|
| T01 |  | FAIL | retrieve_contract_evidence -> get_definitions | FAIL | PASS | 2 | 2 | 1.00 | $0.002614 | loop |
| T02 |  | FAIL | retrieve_contract_evidence -> get_definitions | FAIL | PASS | 2 | 2 | 1.00 | $0.002646 | loop |
| T03 |  | FAIL | retrieve_contract_evidence -> get_definitions -> get_definitions -> get_definitions | FAIL | FAIL | 4 | 2 | 2.00 | $0.003858 | loop |
| T04 |  | FAIL | retrieve_contract_evidence -> get_definitions | FAIL | PASS | 2 | 2 | 1.00 | $0.002642 | loop |
| T05 |  | FAIL | retrieve_contract_evidence -> get_definitions | FAIL | PASS | 2 | 2 | 1.00 | $0.002635 | loop |
| T06 |  | FAIL | retrieve_contract_evidence -> get_definitions | PASS | PASS | 2 | 2 | 1.00 | $0.002695 | loop |
| T07 | Y | FAIL | retrieve_contract_evidence -> get_definitions -> get_definitions -> get_definitions | PASS | PASS | 4 | 3 | 1.33 | $0.003489 | loop |
| T08 | Y | FAIL | retrieve_contract_evidence -> get_definitions | PASS | PASS | 2 | 3 | 0.67 | $0.002231 | loop |
| T09 | Y | FAIL | retrieve_contract_evidence -> get_definitions -> get_definitions | PASS | PASS | 3 | 4 | 0.75 | $0.003368 | loop |
| T10 |  | FAIL | retrieve_contract_evidence -> get_definitions | PASS | PASS | 2 | 2 | 1.00 | $0.002694 | loop |

## Failure mode counts

| Mode | Count |
|---|---:|
| loop | 10 |

## Outcome-vs-trajectory example (right answer, wrong path)

**T01**

Question: What is the annual salary of the employee?

Outcome: PASS

Trajectory: FAIL (loop)

Expected path(s):

```text
retrieve_contract_evidence -> draft_grounded_answer
```

Actual path:

```text
retrieve_contract_evidence -> get_definitions
```

Fictional term(s) requested: ['Annual_Salary']

Final answer: The annual salary of the employee is USD 72,000.

The model retrieved the correct clause (containing "Annual Salary USD
72,000" verbatim), then tried a second retrieve (blocked), then called
`get_definitions(term="Annual_Salary", contract_version="Employment_Agreement")`
-- a term that does not exist in the contract (it is not a `"X" means...`
defined term, just a plain heading). That call correctly returned
"not found," the model repeated the same invalid call twice more, and the
stuck-loop guard forced a draft. The forced draft still produced the right
answer only because the raw retrieved text already had the number in it --
this is the textbook "right answer, wrong path" case: the trajectory never
resolved anything, it just got lucky that the fact was already visible.
