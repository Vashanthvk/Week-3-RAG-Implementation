# Regression check

Task Set F requirement #5: per-mode counts before and after, naming any
mode that got worse or any new mode the mitigation created; if none, list
the modes checked.

## Per-mode counts

| Mode | Before | After | Change |
|---|---:|---:|---|
| loop | 10 | 10 | unchanged |
| wrong_tool | 0 | 0 | unchanged |
| made_up_input | 0 | 0 | unchanged |
| silent_giveup | 0 | 0 | unchanged |
| inefficient_steps | 0 | 0 | unchanged |
| outcome_failure | 0 | 0 | unchanged |
| pass | 0 | 0 | unchanged |

## Honest reading

`loop` was the only failure mode present in either run -- every one of the
10 cases hit the stuck-loop guard both before and after the mitigation, so
there was no other mode for the mitigation to have worsened, and no new
mode appeared. This is a clean (if unexciting) regression check precisely
*because* the mitigation had no effect: it neither helped nor hurt any
mode's classification. The only measurable change from the mitigation is
the added token/cost overhead documented in `mitigation_diff.md`, which
applies uniformly across all 10 cases regardless of failure mode.

All 7 modes in the taxonomy (`agent_loops`/`trajectory_eval.classify_failure`)
were checked: loop, wrong_tool, made_up_input, silent_giveup,
inefficient_steps, outcome_failure, pass. None showed a regression because
none had any baseline presence to regress from.
