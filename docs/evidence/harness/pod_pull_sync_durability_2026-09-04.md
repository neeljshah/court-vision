# S185 pod pull sync durability, 2026-09-04

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.

## Premise and limit

Step 0 reproduced the headline construct before the change: 7 non-comment
`scp` lines, 2 directly checked, and 0 of the four named capture stores in the
pull list. The stale literals were `213.192.2.83:40048`; the local SSH config
names `213.192.2.123:40034`. This worktree has none of the four cache
directories locally, so the descriptive claim that three are already local was
not reproducible here; no data was created or changed. Step 1 used
`scp -P 1 -q -o ConnectTimeout=3 root@127.0.0.1:/nope /tmp/x` and received exit
255, confirming that the client signals an unreachable endpoint.

| Metric | Before | After | Fixed bar |
| --- | ---: | ---: | ---: |
| (a) checked pull invocations / all pull invocations | 2/7 | 8/8 | 8/8 |
| (b) named absent capture store in pull list | 0/1 | 1/1 | 1/1 |

`n = 8 (CONSTRUCT)`: every non-comment `scp` call site is enumerated below.
The sole added target is `data/cache/ingame_books`; the original seven remain.

| Call site target | Checked through `pull_target` |
| --- | --- |
| data/frontend/predict_service | yes |
| data/frontend/clv_ledger.jsonl | yes |
| data/frontend/ops | yes |
| data/cache/benchmarks | yes |
| data/cache/ingame_grade | yes |
| data/cache/ingame_books | yes |
| data/tracking_reports/. | yes |
| data/tracking/track_daemon_ledger.jsonl | yes |

The helper checks every command status, writes a target WARN to stderr, adds to
the failure accumulator, and makes the final one-pass status non-success.
The existing tracking_reports and track_daemon_ledger WARN strings are retained.

## Unreachable-host reproduction

```
pod_pull_sync: WARN predict_service pull failed
pod_pull_sync: WARN clv_ledger pull failed
pod_pull_sync: WARN ops pull failed
pod_pull_sync: WARN benchmarks pull failed
pod_pull_sync: WARN ingame_grade pull failed
pod_pull_sync: WARN ingame_books pull failed
pod_pull_sync: WARN tracking_reports pull failed
pod_pull_sync: WARN track_daemon_ledger pull failed
pod_pull_sync: pass INCOMPLETE (8 target(s) failed) 18:49:51Z
exit status: 8
```

The focused test independently asserts a non-zero exit, stderr WARN output, the
INCOMPLETE final line, absence of the success final line, eight call sites, and
no redirected call site. `eye check = n/a (S-row); reproduction = run
tests/platformkit/test_pod_pull_sync.py, which constructs every call site and
executes the unreachable-endpoint path.`

## NOT VERIFIED

- No live pod was contacted, so a real pull of ingame_books was not demonstrated.
- The other 14 hardcoded pod-address files under scripts/ were not changed.
- The loop remains a repeated pull with its existing 300-second interval; it was
  not run indefinitely during this check.
