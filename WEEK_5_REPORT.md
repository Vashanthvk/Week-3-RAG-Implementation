# Legal Contract RAG — Week 5 Error Analysis

## 1. Objective

## 2. Trace Collection

20 real traces were collected from the Legal Contract RAG application.

## 3. Trace-by-Trace Observations

Analysis of all 20 traces.

## 4. Open Coding

Observations were recorded before assigning problem categories.

## 5. Error Taxonomy

1. Unsupported / overgeneralized answers
2. Retrieval mismatch
3. Source/chunk confusion
4. Retrieval redundancy
5. Retry dependency

## 6. Frequency × Severity

...

## 7. Ranked Problems

1. Unsupported / overgeneralized answer
2. Retrieval mismatch
3. Source/chunk confusion
4. Retrieval redundancy
5. Retry dependency

## 8. Selected Problem for Next Fix

Unsupported / overgeneralized answers.

## 9. Prediction

If contract/source grounding is strengthened so that the model
must identify the specific agreement supporting an answer and
must not generalize information across contracts, unsupported
cross-document claims should decrease while correct
"I don't know" behavior remains intact.

## 10. Positive Findings

The system correctly handled unsupported questions such as
medical insurance, performance bonus, pet policy, and
work-from-home allowance.

## 11. Conclusion