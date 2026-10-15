# Failure case

Injected defined-terms worker HTTP 500 on case 5.
The injected run is recorded in `handoffs.log` with `arm=orchestrator_failure_injected` and `status=500 injected`.
Observed behavior: degraded to a partial answer; no retry and no invented definition.
Stop reason: `answer_ready`.
