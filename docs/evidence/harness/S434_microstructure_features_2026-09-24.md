# S434 microstructure feature preparation

PREPARE candidate; construct validation only. Independent acceptance is pending.
WHERE: local Windows worktree `C:/Users/neelj/nba-harness-h86`; stdlib module,
synthetic per-file pytest, no network or pod. No captured archive was opened.
Base commit at this fix (`git rev-parse --short HEAD`, AMENDMENT 7, worktree on
the master tip): `45cecdf6a`. Spec identity at this fix: 17937 bytes, sha256
`9a60f50b77ad203e58c82bcb4ce9986687d79c083751740dcb9fb14839d9cc8f`.

## Binding before-condition

Before any implementation, `Get-Item scripts/platformkit/ingame/microstructure_features.py`
returned `Cannot find path ... because it does not exist.`
`rg` was unavailable; the fallback `git grep -n MICRO_FEATURES -- scripts`
returned no matches. Initial `git status --short` returned no output.
Thus the module-absence premise holds: before = 0 / 18 (CONSTRUCT).

The supporting NFL premise in the spec brief is stale: master's
`baseline_four_arm_features.py` DOES carry an `nfl_state` helper
(`git grep -n nfl master -- scripts/platformkit/ingame/baseline_four_arm_features.py`
returns lines 19/75/86). The candidate neither imports that helper nor changes
its file or `CORPORA`, so this row is unaffected either way.

The sole imported landed API was read in full before coding:
`local_state_capture_dates.py:26 def venue_instant(value: object) -> Decimal | None`
(exact-fraction receipt parsing); its own shared parser,
`venue_time.py:45 def parse_venue_time(value: object) -> float | None`, returns
a float that is never used for feature ages. `local_capture_runner_row.py:44-50`
stamps response-end `capture_ts`; `:110-116` gives `yes_bid`/`no_bid` with no
ask-size field (YES ask size uses `no_bid_size`). `local_capture_writer.py:15-25`
encodes Decimal as a bare JSON number, so the reader uses
`json.loads(..., parse_float=Decimal)`. `local_capture_runner_trades.py:36-40`
spreads raw venue fields into trade rows (`taker_side`, `count_fp`,
`created_time`, `trade_id`). `local_state_capture.py:32-38` gives a key's first
row `state_changed=None`; only strict earlier `True` rows supply change age.

## Behavior and accounting

Every served state row becomes an output tick, including invalid tick receipts
(six null features with `invalid_instant`). Inputs sort by parsed receipt and
canonical JSON; future and equal-time payloads cannot affect a current tick.
Equal-receipt snapshots select canonically under (receipt, canonical JSON) --
the later row in that ordering is the prior book -- and are counted
`equal_receipt_snapshots`. Equal-receipt prior state rows are ordered ties
under that same ordering; there is no separate refusal reason for a repeat
state receipt. A row whose receipt instant does not parse cannot be shown to
precede any tick: it is excluded from every tick's computation and counted
ONCE in the census as `invalid_instant`; it refuses a feature group only when
it is the tick's own receipt (all six features null, reason `invalid_instant`).
No tick is removed for unavailable inputs.

A one-sided book still emits `quote_age_s` (the receipt age of the latest
snapshot) while `touch_imbalance` and `spread_cents` are refused
`one_sided_book`, counted once per row in `refused_by_reason` (never
`absent_by_reason`). Features are flat named fields; `reasons` names
unavailable fields; per-tick `counts` and the census `counts` key each
diagnostic on the offending input row, so a row is counted once however many
ticks observe it (tick-level absences key on the state row itself). Per-feature
present + absent-by-reason + refused-by-reason equals the tick denominator.
Zero flow/count means a prior tape exists but no retained trade falls in the
created-time window; it does not establish that no trades occurred.

A trade only reserves its `trade_id` once it has a parseable `created_time`
and falls inside the tick's `[instant - 60, instant)` window; a malformed or
out-of-window copy never reserves the id, so a later valid copy of the same id
is consumed normally. Among candidates that do reserve an id, the first
eligible copy (by receipt, then canonical JSON) is retained and every later
eligible copy is counted `duplicate_trade_id`.

Prices, sizes, and quantities remain Decimal. Every finite, non-negative
Decimal quantity is retained regardless of magnitude or digit count; refusal
(`invalid_number`) is for non-finite, negative, non-numeric or
non-Decimal-parseable values only. `signed_flow_60s`, `quote_age_s`, and
`seconds_since_last_state_change` are exact sums/differences computed under a
local context with `prec = decimal.MAX_PREC` (with `Emax`/`Emin` at their
widest), so no digit count rounds them. `touch_imbalance`'s division is
computed in its own nested, bounded context (80 significant figures, the
figure the earlier rounds settled on) because an exact division of two
Decimals can be non-terminating; only that one ratio is rounded, never the
sums that feed it when they fit. Counts are Python integers derived from
retained rows; `count_fp` is a fractional quantity.

The CLI streams each shard line by line, retaining only served identifiers,
and hashes all input bytes. Its census records absolute path, bytes, SHA-256,
tick/game counts, per-feature reasons, and nearest-rank p0/p10/p50/p90/p100.
Non-dictionary or malformed JSON lines are counted `invalid_record`; unserved
rows are counted `not_served`; marker records are not tape trades. Each output
file is written to a temporary file, flushed, fsynced, and atomically
replaced (individually atomic, not a single transactional pair); a failed
write leaves the previous destination recoverable. Output paths beneath
`data/cache` or `data/registry` are refused before reading inputs or creating
directories, including resolved path aliases.

## Construct validation

Reproduce with:
```
python -m pytest tests/platformkit/ingame/test_microstructure_features.py -q -p no:cacheprovider
python -m pytest tests/platformkit/ingame/test_microstructure_features_1c.py -q -p no:cacheprovider
python -m scripts.platformkit.ingame.microstructure_features --help
python -m scripts.platformkit.tracking.contract_preflight --base master --spec docs/evidence/tracking/specs/S434_spec.md --paths scripts/platformkit/ingame/microstructure_features.py tests/platformkit/ingame/test_microstructure_features.py tests/platformkit/ingame/test_microstructure_features_1c.py docs/evidence/harness/S434_microstructure_features_2026-09-24.md
```

The 20 numbered tests in `test_microstructure_features.py` correspond to the
spec's 18 enumerated construct cases plus the two AMENDMENT 1 regressions:
invalid instants; forbidden output; exact imbalance; both sizes zero;
one-sided books; fractional/nonpositive spreads; missing book; equal receipt
exclusion; exact ages; signed window endpoints; late backfill; refused sides
with count; duplicate IDs; missing tape versus observed zero; state-change
history; truncation; input permutations; names/CORPORA/causal rows and hashed
CLI census; per-row-once counters; window-scoped poisoning. The 10 tests in
`test_microstructure_features_1c.py` add the AMENDMENT 2-6 regressions listed
in Fix history below. 30 tests total, all passing at this fix. CLI `--help`:
exit 0. Before/after SHA-256 comparison: the must-not-move files are
byte-identical throughout every fix (verified again this round; see A9).

## Fix history

- FIX 1b (AMENDMENT 1, round 1 sol REJECT candidate; ACCEPT with corrections): per-row-once
  census counters (keyed on input row identity, not tick); a bad trade
  validates and can only refuse the ticks whose window contains it; one-sided
  book keeps `quote_age_s`. 20 passed.
- FIX 1c (AMENDMENT 2, round 1 sol REJECT, 3 blockers): a row with an
  unparseable receipt is excluded from every tick (never just refuses the one
  that observed it); equal-receipt snapshots are ordered ties, not a
  `duplicate_snapshot` refusal; no invented magnitude ceiling/floor on
  Decimal quantities. New file `test_microstructure_features_1c.py` (3 tests).
  20 + 3 passed.
- FIX 1d (AMENDMENT 3, round 2 sol REJECT, 1 blocker): three literal
  `assert receipt < instant` statements added in `_book`/`_tape`/`_state`
  (direct-helper regressions prove they fire); `test_01` asserts exact
  `invalid_instant` counts. 20 + 6 passed.
- FIX 1e (AMENDMENT 4, round 3 sol REJECT, 3 blockers): `one_sided_book` moved
  from the absent set to a refusal reason; the invented repeat-state-receipt
  guard removed (ties, not a refusal). 20 + 7 passed.
- FIX 1f (AMENDMENT 5, round 4 sol REJECT, 1 code + 1 orchestration blocker):
  `trade_id` reservation moved to after `created_time`/window validation, so a
  malformed or out-of-window copy never blocks a later valid copy; worktree
  fast-forwarded to master before each round from here on. 20 + 8 passed.
- FIX 1g (AMENDMENT 6, round 5 sol REJECT, 3 blockers): the module's single
  outer Decimal context moved from a fixed 80-digit precision to
  `decimal.MAX_PREC` so `signed_flow_60s`/`quote_age_s`/
  `seconds_since_last_state_change` sum and subtract exactly at any digit
  count; `touch_imbalance`'s division kept its own nested 80-significant-figure
  context (unchanged representation) since an exact division can be
  non-terminating. A9 rows re-measured from this tree after the fast-forward
  (two were stale: `local_state_capture.py` and `baseline_four_arm_features.py`
  had both grown since S432 landed). Memo condensed under 300 lines; every
  sentence superseded by AMENDMENTS 1-6 restated or removed. 20 + 10 passed.

## Source identity (A9)

All paths below are relative to the absolute worktree root stated above.
Resolution: text, not video. The CLI records full paths for empirical inputs.
Every row below is measured from this tree at base commit `45cecdf6a`
(`python -c "import hashlib,sys;d=open(sys.argv[1],'rb').read();print(len(d),hashlib.sha256(d).hexdigest())" <path>`).

| Input inspected | Bytes | SHA-256 |
| --- | ---: | --- |
| scripts/platformkit/ingame/local_state_capture_dates.py | 5517 | 6362932662249177996c6e12bc20866f418e3ed56ddb556d56c8582523b50f1d |
| scripts/platformkit/execution/venue_time.py | 2029 | 651d80edc0ef0788ea543b2cf3e9f4ae8c1d5114e67211cf7fcd6047eade79f8 |
| scripts/platformkit/ingame/local_capture_runner_row.py | 6901 | 7a962ee8fc1d6dcb46941d1fef0903a4721d57b510b83dcfb8736c91c61570a1 |
| scripts/platformkit/ingame/local_capture_writer.py | 7873 | a450f45e1eb8f9fe37202c488c85afef9e950f97d3c1b8f948b4128231b9279c |
| scripts/platformkit/ingame/local_capture_runner_trades.py | 5327 | 8da9256e99a11c6e11495c342459dac7faa0f284963710d10b0bf42a8d615cbc |
| scripts/platformkit/ingame/local_state_capture.py | 17829 | 129b12eb42895a5ae02cb8a6fd0c2df4e6860e7259f82a8dee0a969f846957c0 |
| scripts/platformkit/ingame/baseline_four_arm_features.py | 15557 | 4cd95bb70b0578318ad04f7144455e083a754924c8b0ee2c6c596e38e9880647 |
| docs/evidence/tracking/specs/S434_spec.md | 17937 | 9a60f50b77ad203e58c82bcb4ce9986687d79c083751740dcb9fb14839d9cc8f |
| scripts/platformkit/ingame/microstructure_features.py | 13920 | f286633c34eb138c6d4dd2c2f41b74d56427555bb0f10a576993110560a95090 |
| tests/platformkit/ingame/test_microstructure_features.py | 14364 | 66dc9b746a5790a87efc06f21c4edcd5c32f55d2999a27a3098c9284e6cceebf |
| tests/platformkit/ingame/test_microstructure_features_1c.py | 6461 | 6fb730f0c2e078c4140c2ae00242ff80a9d4be73d681256bfb7552689cff3226 |
| docs/evidence/forward/schedules/2026-09-22_maker_forward.json | 849 | 10eb2e7b57a2917654caa57be3c8c6d3b1eaab22ade0bbaf530e6682002fa7d8 |

`git diff --name-only master -- scripts/platformkit/ingame/baseline_four_arm_features.py
scripts/platformkit/ingame/local_state_capture.py` is empty at this base (worktree
HEAD == master tip == `45cecdf6a`), so the two must-not-move files above are
byte-identical to current master; their earlier rows in this memo (measured
before this worktree's fast-forward) are superseded by the rows above, not
appended beside them.

## NOT VERIFIED

- Whether any feature carries information about the mid's next move is NOT
  measured here; that is S435's report.
- Real archive census, both-day shard reproduction, and hand recomputation of
  two real served ticks remain the orchestrator's step. No empirical feature
  distribution, calibration comparison, or prediction was measured.
- Real filesystem crashes, a failure between the two output replacements,
  concurrent CLI writers, and full-shard performance were not exercised.
- Independent verification on master and lane_commit are pending.

## REAL RUN 1 (orchestrator, main tree, 2026-09-24 20:2xZ, after landing 789f94ecd)

Command: python -m scripts.platformkit.ingame.microstructure_features --schedule docs/evidence/forward/schedules/2026-09-22_maker_forward.json --books <books root>/kalshi/mlb/2026-09-22.jsonl <...>/2026-09-23.jsonl --state <v2 state root>/state/mlb/2026-09-22.jsonl <...>/2026-09-23.jsonl --out-dir docs/evidence/forward/microstructure. Exit 0 in 152 s; peak working set 335 MB (streamed; served rows retained only).
Census (docs/evidence/forward/microstructure/2026-09-22_maker_forward_micro_census.json, committed): n_ticks 4290, n_games 3; counts {"no_prior_state_change": 942}.
Per feature (present / absent / refused; nearest-rank quantiles of present values):
- quote_age_s: 4290 / 0 / 0; p0 0.012058 / p10 1.206128 / p50 1693.550638 / p90 21248.002449 / p100 54907.230269 -- the median book age at a served state tick is about 28 minutes and p90 about 5.9 hours: the focus window closes 3600 s after the scheduled start (capture_scheduler.py:123) and later receipts are record_type snapshot_bulk, which this row does not consume by spec (snapshot rows only), so the age reflects both the focus-window close and that exclusion; either way the served ticks after the first hour have no focus-cadence book (evidence for register row S446, and a NEW GAP: whether snapshot_bulk rows should feed the book features is a spec question, not a defect).
- spread_cents: 4290 / 0 / 0; p0 1 / p10 1 / p50 1 / p90 1 / p100 6.
- touch_imbalance: 4290 / 0 / 0; p50 about -0.33 (exact Decimal strings in the census).
- signed_flow_60s: 4290 / 0 / 0; p0 -2054.74 / p10 0 / p50 0 / p90 0 / p100 11993.43 -- p10 through p90 are 0: most 60 s windows before a state tick hold no trade.
- trade_count_60s: 4290 / 0 / 0; p0 0 / p10 0 / p50 0 / p90 0 / p100 95.
- seconds_since_last_state_change: 3348 / 942 (no_prior_state_change) / 0; p0 5.680828 / p10 10.005284 / p50 21.852452 / p90 1297.167935 / p100 49507.281297.
Rows artifact: 2026-09-22_maker_forward_micro_rows.jsonl, 1963153 bytes, sha256 94d4b8297317a122828a537a86dddd95ee390cb5184d222390ad84790f572d65 (NOT committed: reproducible from the shards with the command above; the census JSON is committed).
Nothing here is scored; whether any feature carries information about the mid's next move is S435's question. Two-tick hand recomputation: REAL RUN 1 REPRODUCTION below (MATCH 2 of 2).

## REAL RUN 1 REPRODUCTION (orchestrator, 2026-09-24 20:3xZ; the spec's "hand-recompute two ticks" step)

Two served ticks were recomputed from the raw shards by an independent scratch script (streams both book shards; last record_type snapshot with receipt < T under (receipt, canonical JSON); trades with receipt < T and T-60 <= created_time < T, first copy per trade_id):
- KXMLBGAME-26SEP221840MILPHI-PHI at 2026-09-22T22:19:58.674230Z: recomputed imbalance -0.8324225040044952799..., spread 1, quote_age_s 23785.595119, signed_flow_60s 698.25, trade_count_60s 13 -- census row identical on every field.
- KXMLBGAME-26SEP221840MILPHI-PHI at 2026-09-22T22:38:04.209368Z: recomputed imbalance -0.5816825796659079087..., spread 1, quote_age_s 1.415115, signed_flow_60s 0, trade_count_60s 0 -- census row identical on every field.
Reproduction: MATCH (2 of 2 ticks). Script: scratchpad recompute_s434_ticks.py (not committed; the rule it applies is the spec's).
