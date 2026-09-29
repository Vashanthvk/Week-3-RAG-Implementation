# Week 8 Trajectory Evaluation -- After Mitigation

## Summary

- Cases evaluated: 10
- Tool-choice accuracy: 0.00%
- Argument validity rate: 50.00%
- Trajectory pass rate (tool-choice AND argument valid): 0.00%
- Outcome pass rate: 90.00%
- **Outcome-vs-trajectory gap: 90.00%**
- Average step efficiency (steps taken / steps needed): 0.97
- Cost per question -- p50: $0.002819
- Cost per question -- max: $0.004302

## Per-case results

| ID | Dep? | Tool Path | Actual Path | Args | Outcome | Steps | Needed | Eff. | Cost | Mode |
|---|---|---|---|---|---|---:|---:|---:|---:|---|
| 1 |  | FAIL | retrieve_contract_evidence -> get_definitions | FAIL | PASS | 2 | 2 | 1.00 | $0.002788 | loop |
| 2 |  | FAIL | retrieve_contract_evidence -> get_definitions | FAIL | PASS | 2 | 2 | 1.00 | $0.002809 | loop |
| 3 |  | FAIL | retrieve_contract_evidence -> get_definitions | FAIL | FAIL | 2 | 2 | 1.00 | $0.002804 | loop |
| 4 |  | FAIL | retrieve_contract_evidence -> get_definitions | FAIL | PASS | 2 | 2 | 1.00 | $0.002792 | loop |
| 5 |  | FAIL | retrieve_contract_evidence -> get_definitions | FAIL | PASS | 2 | 2 | 1.00 | $0.002796 | loop |
| 6 |  | FAIL | retrieve_contract_evidence -> get_definitions | PASS | PASS | 2 | 2 | 1.00 | $0.002841 | loop |
| 7 | Y | FAIL | retrieve_contract_evidence -> get_definitions -> get_definitions -> get_definitions | PASS | PASS | 4 | 3 | 1.33 | $0.004302 | loop |
| 8 | Y | FAIL | retrieve_contract_evidence -> get_definitions | PASS | PASS | 2 | 3 | 0.67 | $0.002920 | loop |
| 9 | Y | FAIL | retrieve_contract_evidence -> get_definitions -> get_definitions | PASS | PASS | 3 | 4 | 0.75 | $0.004182 | loop |
| 10 |  | FAIL | retrieve_contract_evidence -> get_definitions | PASS | PASS | 2 | 2 | 1.00 | $0.002830 | loop |

## Failure mode counts

| Mode | Count |
|---|---:|
| loop | 10 |

## Outcome-vs-trajectory example (right answer, wrong path)

**1**

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

Fictional term(s) requested: ['Annual Salary']

Final answer: The annual salary of the employee is USD 72,000.
