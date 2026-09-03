# S134 / S135 / S130 -- red-team round 2 fixes: alias chains, the claim lease, tick flags

Date 2026-09-03 | area harness | register rows S134 (was S141), S135 (was S142),
S130 (was S137) in `docs/evidence/HARNESS_GAPS_2026-09-03.md`, filed from
`docs/evidence/harness/REDTEAM_ROUND2_2026-09-03.md`.

Verdict **ACCEPT** on all three. Calibration bookkeeping only (Q6): no dollar,
ROI, profit or edge word appears here, and no retracted figure is restated.
Uncharged -- nothing in this lane calls `_charge_ledger`, reads K, or seals a
prereg. `data/cache/eval_gate/backtest_fwer.jsonl` is 18 rows,
md5 `a4ae7c13995672e478d59770591b83ba` before and after. `data/registry`
untouched, no flag flipped, no bar moved, no pod contact, no push.

---

## STEP 0 -- every premise reproduced first (Q8), on master, before any edit

Probe script (scratchpad, not committed) output, verbatim:

```
== S134 probe A: rename with no alias re-zeroes K ==
  next_k_family(rows, 'new_fam') = 1 (expected 3 if the rename kept K)
== S134 probe B: alias CHAIN a->b->c is not transitive ==
  resolve_family('a') = b (expected 'c')
  next_k_family(rows, 'c') = 1 (expected 3)
  k_family read path over the same rows: 0 (expected 2)
== S134 probe C: the two K counters disagree on a pre-S13 row ==
  next_k_family(rows,'X') = 2 (write path)
  k_family('X')           = 2 (read path)  -> next-1 = 1 vs 2
== S134 probe D: real 18-row ledger, do the two counters agree? ==
   ingame_arms_mlb          k_family=2 next_k_family-1=2
   ingame_arms_nba          k_family=1 next_k_family-1=1
   soccer_gate              k_family=1 next_k_family-1=1

== S135 probe: two runners claim the same rows at 901 s ==
  runner A claimed 3
  runner B claimed at +901 s while A still works: 3 (expected 0)
  renew API present: False
  sport-NULL hypothesis enqueued: 1 rows (expected: refused)
  claim(sport='mlb') -> 0 | claim(sport=None) -> 1

== S130 probe: tick flags are string-exact and order-dependent ==
  same instant, two spellings -> n_dup = 0 (expected 1)
  n_informative in tick order = 6 | same six rows reordered = 2 (expected equal)
  requote() sorts its frame: False
```

All four described symptoms reproduce, including the register's exact numbers
(`1 instead of 3`, `2 instead of 3`, `6 vs 2`). One premise detail is CORRECTED,
not falsified: the two counters already agree on every family of the REAL ledger
(probe D), because all four of its family-carrying rows also carry `k_family` --
the disagreement is a shape defect that only a pre-S13 family row exposes.

---

## S134 -- alias chains resolve to a fixed point

`scripts/platformkit/eval_gate/family_bars.py`. `resolve_family` was a single
`dict.get`, so it stopped one hop short: a rename written ON TOP of an existing
alias (`a -> b -> c`) resolved to `b`, matched no ledger row, and re-zeroed that
family's K. It now loops to a fixed point and raises `ValueError` on a cycle
rather than spinning. `None` is not a key, so the no-family contract is
unchanged, and `ledger.next_k_family` imports THIS function (line 152), so the
write path is fixed by the same edit -- the reason the fix could land without
touching the token-locked module.

The remaining half -- the two counters disagreeing on a pre-S13 row -- is one
line inside `eval_gate/ledger.py`, which is SHARED-TOKEN. It is filed as
`docs/research/organization-sprint/PROPOSED-S134-ledger-alias-transitive.md` for
the orchestrator to apply, and its landing test is already in the tree marked
`xfail(strict=True)` so applying the diff makes the file fail until the marker
is removed. The patch is a **no-op on the real 18-row ledger** (probe D).

BAR: `k_family` over the unmodified ledger is unchanged for every frozen family.
MET, asserted from the spec rather than restated:
`{ingame_arms_mlb: 2, ingame_arms_nba: 1, soccer_gate: 1}`, all others 0. The
register row says "39 frozen families"; the frozen spec now carries **40**
(S102 added a tickgrid family after the row was filed) -- a stale count in the
row, not a moved bar.

## S135 -- the claim lease renews, the reap is owner-scoped, a sport-NULL row is refused

`scripts/platformkit/foundry/results_db.py`, three additive changes:

1. `renew(hashes, lease_seconds, now)` -- the heartbeat the register asks for.
   Only STILL-CLAIMED rows move, so a reaped or released row is not silently
   re-taken (that would be a re-claim loop wearing a heartbeat's clothes, B4).
2. `claim(..., lease_seconds=None)` is the new default and leases
   `LEASE_SECONDS` **per claimed row**, because a claimer screens its batch
   serially and a flat 900 s expired mid-batch. An explicit `lease_seconds` is
   honoured exactly as passed, so every pre-S135 caller and test is unchanged.
   This is what fixes the running pod without editing `foundry_runner.py`
   (line 240 calls `claim` with no lease), which this lane does not own.
3. `claim(..., owner=...)` records the claimer in a new additive `queue.claimer`
   column (migrated in place beside `lease_until`), and `reap_expired(now,
   owner)` skips rows whose claimer IS the caller. The reap was global, so a
   runner whose batch outran its lease reaped and then re-claimed the very
   hypotheses it was still screening. Ceiling, commented in the file: a
   restarted runner reusing the same owner id will not self-reap either -- it
   calls `release()`, which is the deliberate act reaping cannot be.

Sport-NULL: **refused at seed time with a named reason** (the option this lane
picked). `enqueue` now raises `ValueError("refusing to queue N of M hypotheses
with no claimable sport ...")` for any hash whose hypothesis has a NULL/empty
sport OR no hypothesis row at all -- both are rows `claim(sport=...)` can never
hand to a sport-bound runner, which is a NEVER-claim loop, not a re-claim one.
The check is chunked (`_SQL_VARS = 500`) because a pod seed queues thousands.
`undrainable_queued()` reports any such row a pre-S135 seed already left behind,
which is how "the pod queue reports 0 sport-NULL queued rows" becomes checkable
without contacting the pod (this lane made none). The real seed path is
unaffected: `seed_queue.frozen_hypotheses()` yields 3,564 hypotheses, **0**
without a sport.

BAR: the double-claim probe returns 0 rows for runner B. MET
(`test_a_renewed_lease_is_not_double_claimed_at_901_seconds`), and also met
without any renew call at all, by the batch-scaled default
(`test_the_default_lease_scales_with_the_batch`: `reap_expired(+901)` was 3,
is now 0; the rows free at +2701 for a 3-row batch).

## S130 -- tick flags are neither string-exact nor order-dependent

`scripts/platformkit/eval_gate/tick_informative.py`. `flag_ticks` now normalises
the timestamp column with `pd.to_datetime(utc=True)` before `duplicated()`, and
stably sorts by `(game, ts)` ITSELF rather than relying on one of its two callers
-- `attach_informative_summary` sorted, `requote` did not, which is the whole of
the 6-vs-2 order dependence. The sort moved OUT of `attach_informative_summary`
into the shared function, so both callers and every future one get it.

The parse is deliberately ALL-OR-NOTHING: a column that does not fully parse
(a synthetic `t0`/`t1`, or a mixed dialect) falls back to its raw values, because
half a column of NaT would collapse every unparsed row into one duplicate and
DELETE real ticks -- the opposite failure, and the worse one. A test pins that.
A reserved scratch column name is refused, not clobbered.

BAR: the two reproduced probes agree, and the three archived S87 re-quotes
reproduce their published CIs unchanged. MET. Re-run of `requote` over the three
archived artifacts, diffed against `data/cache/eval_gate/s87_requote_2026-09-03.json`:

```
s58_trialA_clamp        n_informative 14543 -> 14543 | n_dup 0 -> 0 | after ci95 [-0.000475, 0.000537] -> [-0.000475, 0.000537] | unchanged
s58_trialB_nba_halftime n_informative  1593 ->  1593 | n_dup 0 -> 0 | after ci95 [-0.011503, -0.001664] -> [-0.011503, -0.001664] | unchanged
s80_player_grain        n_informative  1106 ->  1106 | n_dup 5 -> 5 | after ci95 [-0.032578, 0.036079] -> [-0.032578, 0.036079] | unchanged
```

`published_ci_reproduced_from_series` is True on all three, verdicts NULL /
BEHIND / SCREEN_NULL unchanged. Byte-identical because those three CSVs were
already written in tick order with one timestamp spelling -- the defect was real
but had not yet bitten a published artifact, which is the honest finding.

---

## Tests (per-file only)

```
python -m pytest scripts/platformkit/eval_gate/test_family_bars.py -q          18 passed, 1 xfailed
python -m pytest scripts/platformkit/eval_gate/test_tick_informative.py -q     17 passed
python -m pytest scripts/platformkit/eval_gate/test_ledger_schema_s13.py -q     6 passed (read-only on the ledger)
python -m pytest tests/platformkit/foundry/test_results_db.py -q               21 passed
python -m pytest tests/platformkit/foundry/test_foundry_runner_s16.py -q        7 passed
```

The three eval_gate files run together as `41 passed, 1 xfailed in 4.86s`.
Regression on downstream readers of the changed flags:
`tests/platformkit/foundry/test_ingame_supply_mlb.py` 4 passed,
`tests/platformkit/ingame/test_s98_nba_better_prior.py` 11 passed.

A5 -- every reader of a touched surface was grepped. `flag_ticks` /
`attach_informative_summary`: 10 production call sites, all under
`scripts/platformkit/eval_gate/` (s58 x3, s80, s84, s98, s103, s114, s115, s121,
`ingame_calibration_report`), every one of which already sorted or fed
already-sorted rows -- the change can only make their flags MORE stable.
`ResultsDB.enqueue`: `foundry/seed_queue.py:87` and `eval_gate/s111_screen.py:50`.
`ResultsDB.claim`: `foundry_runner.py:240`. `resolve_family`: `ledger.py:152`
plus `family_bars` internals. `next_k_family`: `backtest_runner.py:192`.

## NOT VERIFIED

- `renew()` has ZERO production callers: `foundry_runner.py` belongs to another
  lane, so the pod is protected by the batch-scaled default lease, not by a
  heartbeat. A batch that runs longer than `900 s x rows` is still reclaimable.
- `undrainable_queued()` was exercised only on constructed tmp DBs. The pod DB
  was NOT inspected (no pod contact this lane), so "the pod queue reports 0
  sport-NULL queued rows" is unmeasured on the pod itself.
- The `owner` argument is optional and nothing passes it yet; with `owner=None`
  the reap is global exactly as before.
- The S130 fix changed NO published number (the three archives were already
  clean), so its effect is demonstrated on constructed frames only.
- The `k_family` / `next_k_family` agreement on a pre-S13 row is xfail-pending
  the token-locked one-liner.
- `results_db.py` is 372 lines, over the 300-LOC rail; it was already at 301
  before this lane. Trimming further would delete existing documentation.
- Lane's own report; no verifier re-run.

## Appendix -- the PROPOSED one-liner, verbatim

`docs/research/organization-sprint/` is gitignored, so the proposal file is local
only; the diff itself is recorded here so the committed evidence is complete.
In `scripts/platformkit/eval_gate/ledger.py`, `next_k_family`:

```
-    return 1 + sum(1 for r in rows if r.get("k_family") is not None
-                   and resolve_family(r.get("family")) == target)
+    return 1 + sum(1 for r in rows if resolve_family(r.get("family")) == target)
```

The count rule is `family`, aliases resolved. `k_family` is not part of it: a
pre-S13 row carries `family` with `k_family` None and is still a charge against
that family. No-op on the real 18-row ledger, which has no such row.
