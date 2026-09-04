# S221 - pod multi-runner construct probe

Date: 2026-09-04

Verdict: ACCEPT. This is an exhaustive local construct probe, not a pod run.
It opens one fresh temporary SQLite database at a time beneath this worktree,
then removes it. No production cache, register, ledger, pod, or deployment
target was opened.

The governing specification is `docs/evidence/tracking/specs/S221_spec.md`.
The self-check used sections B and Q1-Q9 of
`docs/evidence/tracking/VERIFIER_CONTRACT.md`.

## Premise first (Q8)

The current HEAD behavior was reproduced before adding the probe, against a
fresh temporary SQLite database:

```text
LEASE_SECONDS=900.0
renew_present=True
runner_a_claimed=3
runner_b_claimed_at_plus_901=0
sport_null_enqueue_refused=True
undrainable_queued=0
```

The S135 pre-fix double-claim premise is not present at HEAD, so S221 continued
rather than stopping as FALSIFIED.

## HEAD source reading

| Source opened | Bytes | SHA-256 | Relevant lines |
| --- | ---: | --- | --- |
| `scripts/platformkit/foundry/results_db.py` | 16,146 | `2F1B0ED588CCAF6BDF993140138523FB5049A17FA096CBA79743B6AD8CCF2165` | `LEASE_SECONDS = 900.0` at 37; `reap_expired` at 226; `renew` at 241; `claim` at 267 |
| `scripts/platformkit/foundry/runner_leases.py` | 2,276 | `4521A5C1C1D1DC4BE9670939133A8CC8CC491D3B2077B8CED9E19D81C02AC8D4` | host:pid claimer form at 12; SIGTERM release lifecycle at 50 |
| `scripts/platformkit/foundry_runner.py` | 16,800 | `DDFDFA2D8756D57C47FE9315BCC12F7393DDA0DE1F8DB0D070C2FDE0FD410979` | sport-bound claim at 231; in-flight renew at 242; lifecycle context at 293 |

`reap_expired` selects unfinished claims and excludes a matching owner before
clearing a row. `claim` invokes that reap atomically and uses a default lease
of `LEASE_SECONDS * min(batch, 5)`. The runner passes sport and owner to claim.

## Construct method and result grid

`scripts/platformkit/eval_gate/s221_multirunner_probe.py` creates three valid
`nba` construct hypotheses in a new database for each case. It attempts to
seed a sport-NULL hypothesis, requires the seed guard to refuse it, and asserts
`undrainable_queued() == []` before runner A starts.

The full denominator is 12: 901 and 1801 seconds; heartbeat running, heartbeat
stopped, and SIGTERM handler then restart; and sport-bound `nba` plus unbound
claims. No case is sampled or removed. Restart cases invoke the lifecycle's
installed SIGTERM handler, verify release, then have restarted runner A claim
the rows before runner B is checked.

Metric per case: rows runner B claims while runner A holds unfinished, plus
sport-NULL queued rows at startup. The bar is zero for both cells.

Command run locally:

```text
python -m scripts.platformkit.eval_gate.s221_multirunner_probe
```

| Lifecycle | Sport binding | Horizon seconds | Runner B double-claimed | Sport-NULL queued at startup |
| --- | --- | ---: | ---: | ---: |
| heartbeat_running | bound | 901 | 0 | 0 |
| heartbeat_running | unbound | 901 | 0 | 0 |
| heartbeat_stopped | bound | 901 | 0 | 0 |
| heartbeat_stopped | unbound | 901 | 0 | 0 |
| sigterm_restart | bound | 901 | 0 | 0 |
| sigterm_restart | unbound | 901 | 0 | 0 |
| heartbeat_running | bound | 1801 | 0 | 0 |
| heartbeat_running | unbound | 1801 | 0 | 0 |
| heartbeat_stopped | bound | 1801 | 0 | 0 |
| heartbeat_stopped | unbound | 1801 | 0 | 0 |
| sigterm_restart | bound | 1801 | 0 | 0 |
| sigterm_restart | unbound | 1801 | 0 | 0 |

Live defect: none in this construct grid. Any non-zero result is a live queue
defect under the specified bar.

## Summary JSON (Q9)

There is no scored model comparison or paired-loss series in this construct
queue test, so `differential` is intentionally empty and Q9 is not applicable
to a model comparison. The complete machine-readable result is:

```json
{"cases":[{"horizon_seconds":901,"lifecycle":"heartbeat_running","runner_b_double_claimed":0,"sigterm_handler_exercised":false,"sport_binding":"bound","sport_null_queued_startup":0},{"horizon_seconds":901,"lifecycle":"heartbeat_running","runner_b_double_claimed":0,"sigterm_handler_exercised":false,"sport_binding":"unbound","sport_null_queued_startup":0},{"horizon_seconds":901,"lifecycle":"heartbeat_stopped","runner_b_double_claimed":0,"sigterm_handler_exercised":false,"sport_binding":"bound","sport_null_queued_startup":0},{"horizon_seconds":901,"lifecycle":"heartbeat_stopped","runner_b_double_claimed":0,"sigterm_handler_exercised":false,"sport_binding":"unbound","sport_null_queued_startup":0},{"horizon_seconds":901,"lifecycle":"sigterm_restart","runner_b_double_claimed":0,"sigterm_handler_exercised":true,"sport_binding":"bound","sport_null_queued_startup":0},{"horizon_seconds":901,"lifecycle":"sigterm_restart","runner_b_double_claimed":0,"sigterm_handler_exercised":true,"sport_binding":"unbound","sport_null_queued_startup":0},{"horizon_seconds":1801,"lifecycle":"heartbeat_running","runner_b_double_claimed":0,"sigterm_handler_exercised":false,"sport_binding":"bound","sport_null_queued_startup":0},{"horizon_seconds":1801,"lifecycle":"heartbeat_running","runner_b_double_claimed":0,"sigterm_handler_exercised":false,"sport_binding":"unbound","sport_null_queued_startup":0},{"horizon_seconds":1801,"lifecycle":"heartbeat_stopped","runner_b_double_claimed":0,"sigterm_handler_exercised":false,"sport_binding":"bound","sport_null_queued_startup":0},{"horizon_seconds":1801,"lifecycle":"heartbeat_stopped","runner_b_double_claimed":0,"sigterm_handler_exercised":false,"sport_binding":"unbound","sport_null_queued_startup":0},{"horizon_seconds":1801,"lifecycle":"sigterm_restart","runner_b_double_claimed":0,"sigterm_handler_exercised":true,"sport_binding":"bound","sport_null_queued_startup":0},{"horizon_seconds":1801,"lifecycle":"sigterm_restart","runner_b_double_claimed":0,"sigterm_handler_exercised":true,"sport_binding":"unbound","sport_null_queued_startup":0}],"differential":[],"metric":"runner_b_double_claimed and sport_null_queued_startup per case","n":12,"q9":"not applicable: construct queue probe has no scored model comparison"}
```

## Two-runner launch recipe - REPORTED, NOT EXECUTED

This recipe is documentation only. It did not contact the pod, seed a queue,
start a process, set a flag, or deploy a file.

1. Bind both runners explicitly to the same sport, for example `--sport nba`,
   so they contend only for the NBA subset of the shared queue.
2. Per S110, pause both runners before running the queue seed; seed while they
   remain paused, verify completion, then start the two sport-bound runners
   with `--allow-charge` absent.
3. The repository coordination stop-flag path is
   `/workspace/nba-ai-system/.bot_state/live_status.json`. Current
   `foundry_runner` does not read that path; its clean lifecycle is SIGTERM,
   which releases unfinished claims through `claim_lifecycle`.
4. For a time-bounded observation, use `--minutes` and preserve distinct
   host:pid claimers. Stop by SIGTERM only after operations sets the
   coordination flag.
5. The aggregate-rate figure is an ESTIMATE, not a two-runner measurement:
   doubling the single-runner references gives 18,663.0 screens/hour from
   9,331.5 and 6,533.4 screens/hour from 3,266.7. Shared queue, SQLite, and
   compute contention can make actual aggregate throughput lower.

## Verification and contract self-check

```text
python -m pytest scripts/platformkit/eval_gate/test_s221_multirunner_probe.py -q
1 passed in 4.38s
```

- B1/B9/Q7: all 12 construct cases are present with a named per-case metric.
- B2/B3/B4/B6/B10: this adds only an isolated probe, test, and evidence; no
  schema, gate, queue module, threshold, or existing reader moved.
- B5: no pod contact, copy, deployment, launch, or stop action occurred.
- B7/B8: no render or fitted/scored comparison is involved.
- Q1/Q2/Q4/Q5/Q9 model-comparison clauses are not applicable; no prereg, K,
  ledger action, corpus score, or model comparison occurred.
- Q3: the specified zero bar and 12-case denominator are unchanged.
- Q6: calibration language only. Q8: the S135 premise was re-measured first.

## NOT VERIFIED

- No two-runner pod process was launched; aggregate figures are estimates from
  prior single-runner references only.
- The pod's current queue contents and sport-NULL count were not read.
- The coordination stop flag is not a `foundry_runner` input today; its path is
  named for operations coordination, while SIGTERM is the verified release path.
- This is the lane's local construct result; a verifier must rerun the focused
  test and probe in a fresh temporary database.
