# Task Set F Race Report

| system | pass_rate | p50_latency_s | total_tokens | cost_per_question |
|---|---|---|---|---|
| agent | 0.9 | 26.9498 | 62127 | 0.003106 |
| fixed_workflow | 1.0 | 2.8433 | 4568 | 0.000228 |

## Per-question detail

| system | id | dependency | pass | latency_s | tokens | cost | steps | stop_reason |
|---|---|---|---|---|---|---|---|---|
| agent | 1 | False | True | 56.3934 | 5575 | 0.002788 | 5 | stuck_loop_forced_draft |
| agent | 2 | False | True | 27.2515 | 5618 | 0.002809 | 5 | stuck_loop_forced_draft |
| agent | 3 | False | False | 25.9399 | 5607 | 0.002804 | 5 | stuck_loop_forced_draft |
| agent | 4 | False | True | 24.9376 | 5583 | 0.002792 | 5 | stuck_loop_forced_draft |
| agent | 5 | False | True | 26.7593 | 5593 | 0.002796 | 5 | stuck_loop_forced_draft |
| agent | 6 | False | True | 27.1402 | 5683 | 0.002841 | 5 | stuck_loop_forced_draft |
| agent | 7 | True | True | 47.2468 | 8604 | 0.004302 | 7 | stuck_loop_forced_draft |
| agent | 8 | True | True | 26.4692 | 5839 | 0.00292 | 5 | stuck_loop_forced_draft |
| agent | 9 | True | True | 41.9546 | 8364 | 0.004182 | 7 | stuck_loop_forced_draft |
| agent | 10 | False | True | 23.8433 | 5661 | 0.00283 | 5 | stuck_loop_forced_draft |
| fixed_workflow | 1 | False | True | 2.3947 | 411 | 0.000205 | 2 | answer_ready |
| fixed_workflow | 2 | False | True | 2.9709 | 414 | 0.000207 | 2 | answer_ready |
| fixed_workflow | 3 | False | True | 2.5173 | 406 | 0.000203 | 2 | answer_ready |
| fixed_workflow | 4 | False | True | 2.8584 | 412 | 0.000206 | 2 | answer_ready |
| fixed_workflow | 5 | False | True | 2.8281 | 421 | 0.00021 | 2 | answer_ready |
| fixed_workflow | 6 | False | True | 2.3936 | 404 | 0.000202 | 2 | answer_ready |
| fixed_workflow | 7 | True | True | 9.57 | 633 | 0.000316 | 3 | answer_ready |
| fixed_workflow | 8 | True | True | 3.921 | 526 | 0.000263 | 3 | answer_ready |
| fixed_workflow | 9 | True | True | 3.9955 | 524 | 0.000262 | 3 | answer_ready |
| fixed_workflow | 10 | False | True | 1.2398 | 417 | 0.000208 | 2 | answer_ready |
