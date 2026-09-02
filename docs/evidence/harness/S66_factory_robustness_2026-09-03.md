# S66 -- factory robustness: claim leases, producer timeouts, two unarmed ProcSpecs

Lane F2, main repo, 2026-09-03. Calibration bookkeeping only: nothing scored,
priced, promoted or charged; no K read, no prereg, no bar or threshold moved, no
`data/registry/` write, no flag flipped ON, pod untouched (supervisor 19236 and
foundry runner 165812 neither read nor signalled).

## (a) results_db claim LEASE (B4: a dead claimer must not strand rows)

`scripts/platformkit/foundry/results_db.py`

- `queue` gains `lease_until TEXT` -- ADDITIVE, in `_SCHEMA` for a new DB and by
  `ALTER TABLE` for one created before S66 (every pre-existing column and row
  untouched; `enqueue` / `claim` keep their old call shape).
- `claim(n, tier=None, lease_seconds=900)` stamps `claimed_at` AND
  `lease_until = claimed_at + lease_seconds`.
- `reap_expired(now=None)` returns every expired claim to the queue and returns
  the row count. `claim()` calls it INSIDE its own `BEGIN IMMEDIATE`, so a
  claimer reaps by construction; the method is public so the runner can also reap
  on a pass that claims nothing.
- `release(hashes)` hands rows back on a failure path without waiting the lease.
- A row claimed BEFORE S66 carries `lease_until` NULL and is NEVER auto-reaped:
  nothing can distinguish a live pre-lease claimer from a dead one, so only
  `release()` frees those. Named, not silently reclaimed.

EVIDENCE `python -m pytest tests/platformkit/foundry/test_results_db.py -q` =
**13 passed** (7 pre-existing + 6 new). The headline case,
`test_expired_claim_is_reclaimable_after_the_lease_never_before`: 3 rows claimed
with a 900 s lease, the claimer then DIES (no release, no record) --
`claim()` returns `[]`, `reap_expired(now+899s)` returns 0 and `claim()` is still
`[]` (never before), `reap_expired(now+901s)` returns 3 and `claim()` returns 3
rows (after). Also proven: `claim` reaps without being asked
(`lease_seconds=-1`, the next claim gets all 3), `release` frees 2 of 3
mid-lease, and a NULL-lease row survives `reap_expired(now+100000s)` = 0.

## (b) artifact_refresh per-producer TIMEOUT

`scripts/platformkit/mcp_server/artifact_refresh.py`

`PRODUCER_TIMEOUT_SEC = 120.0`; `_run_producer` runs each producer on a DAEMON
thread and joins with the cap. Over it the row is `status="TIMEOUT"`, `rc=1`,
`error="producer exceeded 120s wall cap"`, and the pass CONTINUES. `TIMEOUT` is a
NEW status value beside `ok/FAILED/STALE/NO_ARTIFACT/NO_PRODUCER/NO_RUN` (B2
additive: nothing renamed or removed) with its own `n_timeout` count; a repo-wide
grep found no consumer of the status file's values outside this module and its
tests. Ceiling, stated: a hung thread cannot be killed, so it leaks until the
process exits -- harmless under `--once`, one leaked thread per hang under
`--loop`; the upgrade path is to re-invoke the producer out of process.

EVIDENCE `python -m pytest tests/platformkit/mcp_server/test_artifact_refresh.py -q`
= **9 passed** (7 pre-existing + 2 new). A fake producer that sleeps 5.0 s under
`timeout_sec=0.2` records TIMEOUT while the sibling target still advances
(`n_advanced=1`, `n_failed=0`, `n_timeout=1`) and the whole pass returns in
under 3.0 s wall -- i.e. the cap really fired rather than the producer finishing.
A second case proves a HANG and a CRASH stay distinct statuses (TIMEOUT/FAILED,
counts 1 and 1).

## (c) two supervisor ProcSpecs -- REGISTERED, NOT ARMED

`supervisor/stack_specs.py` (a DATA module: the inventory, no process spawned).

- `m50_foundry_runner` -- `scripts.platformkit.foundry_runner`,
  argv `["--db", "data/cache/eval_gate/hypotheses.sqlite", "--batch", "50",
  "--poll-seconds", "30"]`, heartbeat `data/ab_reports/foundry_runner.heartbeat.json`
  (rewritten by `_finish` once per pass, idle passes included), `fresh_sec=1800`,
  restart forever, no `depends_on`. `--allow-charge` is ABSENT BY CONSTRUCTION,
  so nothing this supervised process runs can reach the FWER ledger.
- `m51_artifact_refresh` -- `scripts.platformkit.mcp_server.artifact_refresh`,
  argv `["--loop", "--interval", "3600"]`, heartbeat
  `data/cache/mcp_server/artifact_refresh_heartbeat.jsonl` (one appended line per
  pass, so the mtime advances), `fresh_sec=9000` (2x the interval + margin, the
  m43/m44 pattern), restart forever, no `depends_on`.

`config/boot/paper.json` is UNCHANGED, so neither spec boots anywhere. THE EXACT
CHANGE THE ORCHESTRATOR APPLIES (services array, after `"m44_exec_evidence"`,
which gains a trailing comma):

    "m50_foundry_runner", "m51_artifact_refresh"

and then restarts the supervisor -- the orchestrator's decision, not this lane's.

EVIDENCE `python -m pytest tests/supervisor/test_stack_specs.py -q` = **19
passed** (15 pre-existing + 4 new), and `python -m supervisor --profile paper
--dry-run` EXIT=0 printing the same 14 children in the same topo order. The
manifest test asserts: the paper allowlist read from `config/boot/paper.json`
contains neither name and boots 14; a scratch profile of `services` + both names
validates and boots exactly 16 (no unknown name, no dangling `depends_on`, no
cycle); `--allow-charge` is not in m50's argv; and -- the non-tautology check --
each spec's argv is parsed by the module's OWN `ArgumentParser`, so an argv the
module would reject fails the test.

DEVIATIONS from the lane brief, both measured:

1. `--queue` is NOT in m50's argv. `foundry_runner.main()` has no such flag
   (queue mode is the DEFAULT; `--legacy` is the opt-out), and
   `python -m scripts.platformkit.foundry_runner --queue --db ...` exits 2 with
   `unrecognized arguments: --queue`. A ProcSpec carrying it would be unbootable.
   Adding the flag would have touched the same parser lane F1 is editing.
2. `nice 10` is NOT expressed. `supervisor.manifest.ProcSpec` has no `nice`
   field, and adding one changes the dataclass plus the spawner for every spec.
   Filed as a NEW GAP rather than done quietly.

## (d) the claimed-hypothesis FAMILY defect (root cause)

MEASURED by the S16 pod hour: all 6,000 claims were labelled `soccer`.
ROOT CAUSE, one function: `results_db._hypothesis()` rebuilt a `Hypothesis`
without `family` / `runtime_available`, so every claimed row read back with
`family=""` and `run_pass`'s `getattr(hypothesis, "family", "") or queue.family`
fell through to the queue's single sport. The columns were ALWAYS stored
(`hypothesis.family`, `hypothesis.runtime_available`, both hash-excluded since
S46b) and `seed_queue` has always passed them -- only the reconstruction lost
them, so NO schema change and no runner change was needed. `upsert_hypothesis`
now also DEFAULTS both from the hypothesis itself, so a caller that forgets them
cannot strand a row (its `runtime_available` default therefore moves from a
hard-coded True to the hypothesis's own value; the only production caller,
`seed_queue.seed`, passes it explicitly and is unaffected).

EVIDENCE (inside the 13 above): `test_claimed_hypothesis_round_trips_its_family`
(a claim returns `family="pace"`), `test_mixed_queue_claims_group_per_family`
(a queue seeded nba_pace x2 + soccer_form x2 groups to `{nba_pace: 2,
soccer_form: 2}` -- exactly what `run_pass` counts as `screened_n`), and
`test_round_trip_every_column`, whose old assertion `get_hypothesis(digest) ==
HYPOTHESIS` ENCODED the bug and now asserts the family survives.

## Regression sweep (per-file only)

test_results_db 13, test_artifact_refresh 9, test_stack_specs 19,
test_foundry_runner_s16 4, test_tiers 20 + test_catalogue 4 = **69 passed**.
Pre-existing and NOT caused by this lane:
`tests/platformkit/mcp_server/test_intelligence_producers.py` 3 failed / 4
passed -- the identical 3 failures appear with this lane's `artifact_refresh.py`
stashed, so that file is already red at the baseline.

Both touched modules stay under the 300-LOC rail: results_db.py 296,
artifact_refresh.py 300. stack_specs.py (1,028) is a DATA module and exempt.

## NOT VERIFIED

- The lease was never exercised by TWO REAL concurrent claimers or by a killed
  process; the "claimer dies" case is a construct (claim, then never release).
  `reap_expired` is proven with an injected `now`, not by waiting out 900 s.
- The lease comparison is a STRING compare of ISO-UTC stamps. Correct for every
  stamp this module writes (all `datetime.now(timezone.utc).isoformat()`); a row
  hand-written with a non-UTC offset would compare wrongly. Not guarded.
- The pod DB was NOT touched or migrated. The 6,000 rows claimed during the S16
  hour carry `lease_until` NULL and will need a `release()` (or a re-seed), which
  this lane did not run.
- No REAL producer was timed out: the cap is proven with a sleeping fake, and
  `refresh_once` was NOT run for real (only `--dry-run`: 5 targets, 4 runnable),
  so 120 s is a chosen number, not one measured against the slowest producer.
- A leaked timeout thread's effect on a LONG `--loop` run is unmeasured; only the
  single-pass case was run.
- m50 / m51 have NEVER been launched. Their readiness paths, `fresh_sec` values
  and restart behaviour are validated only against the manifest and the dry-run;
  no process was started, and the argv check parses flags, it does not run them.
- `foundry_runner.py` was NOT edited by this lane, so the runner's own
  reap-per-pass call and its per-family `screened_n` were not re-run end to end;
  the family fix is proven at the `claim()` boundary the runner consumes.
- WORKING-TREE CLOBBER, found at lane start and NOT repaired by this lane:
  87 tracked files under `scripts/platformkit/**`, `domains/**` and `tests/**`
  differed from HEAD by 333 insertions / 2,089 deletions -- a stale-base
  overwrite, not authored edits. `scripts/platformkit/foundry_runner.py` was
  among them (reverted to the pre-S16 108-line version, losing the S16/S58/S59
  landings); this lane restored THAT ONE file with
  `git checkout HEAD -- scripts/platformkit/foundry_runner.py` and committed
  nothing for it. The other 86 files are UNTOUCHED and still clobbered.
