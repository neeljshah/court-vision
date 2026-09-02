# S45 (a)+(b) + RT-7 -- gate-manifest staleness follow-ups

2026-09-03 | LANE D (main repo) | ACCEPT
Rows: `docs/evidence/HARNESS_GAPS_2026-09-03.md` S45 (S09 verifier 18098d582) and S40 RT-7
(`docs/evidence/harness/REDTEAM_HARNESS_CORE_2026-09-03.md`).
Calibration/audit tooling only. No dollar, ROI, profit or edge claim.

## Premise (Q8) -- re-measured, all three HOLD

Read on disk before the change: `gate_manifest.py:241` `row["status"] = "STALE"`
overwrote UNREADABLE/EMPTY; `render_table`'s footer printed TOTAL/OK/EMPTY/UNREADABLE and
no STALE count; `_stale_rows` had no future check, so RT-7's `as_of=2031-01-01` row scored
`staleness_days = -1581.0` with `status = "OK"` and passed every gate.

## (a) Staleness is a separate flag -- MEASURED reader impact

`stale: bool` is now its own row key; `status` keeps saying what the file IS.
Reproduction (2 artifacts: one corrupt, one stamped 976 days old, `--max-age-days 30`,
`--as-of 2026-09-03`), applying `gate_manifest_tool`'s own status filter:

| manifest | rows matching `status == "UNREADABLE"` |
|---|---|
| master behaviour (status overwritten with STALE) | **0** |
| after (separate `stale` flag) | **1** |

Summary after: `{total 2, ok 1, empty 0, unreadable 1, stale 2}`, exit code 1.
The corrupt artifact was invisible to `gate_manifest_tool(status="UNREADABLE")` and to
`harness_health_report._manifest`'s `status == "OK"` split conflated it with merely-old.

## (b) STALE count in the footer

`TOTAL=2 OK=1 EMPTY=0 UNREADABLE=1 STALE=2  as_of=2026-09-03T00:00:00+00:00`

STALE is a separate column (and a separate table column, `-` / `YES` / `FUTURE`), so
OK + EMPTY + UNREADABLE still sums to TOTAL -- it did not before.

## RT-7 -- a self-declared FUTURE timestamp is INVALID, not fresh

`_FUTURE_TOLERANCE_DAYS = 1.0` (clock-skew knob, documented as a knob and not a bar). A
measurement time later than the reference `as_of` by more than the tolerance sets
`measured_at_invalid = "future"`; `_stale_rows` treats that as an offender, so
`assert_fresh` raises and the CLI exits 1. The declared value is KEPT in `measured_at`
and the negative `staleness_days` stays visible -- the row records what the artifact
claimed and names why it cannot be trusted.

Reproduced on RT-7's exact case, `{"as_of": "2031-01-01"}` at `as_of = 2026-09-03`:
`staleness_days = -1581.0` (matching the red-team memo's measurement byte for byte),
`status = OK`, `measured_at_invalid = "future"`, `assert_fresh` raises naming
`future.json`. A stamp 6 hours ahead (inside the tolerance) stays fresh and is NOT
flagged. The rule applies to an mtime-derived measurement time too -- a future mtime is
equally not-fresh, and one rule is cheaper than two.

## Additivity (B2) and real-repo state

`build_manifest` on this repo at `as_of = 2026-09-03`: **53 rows**, summary
`{total 53, ok 53, empty 0, unreadable 0}`. Two keys ADDED per row
(`measured_at_invalid`, `stale`), 13 keys total; none renamed, none removed, no status
value removed from the row schema -- "STALE" simply stops being written into `status`.
Its only reader was the S09 test assertion, updated in place. 0 rows on disk carry a
future stamp today. Default path (no `--max-age-days`) still leaves every `stale` False
and exits on UNREADABLE alone, as before.

## S45(c) -- OUT OF SCOPE, reported not fixed

Which producers would need a `generated_at` stamp, measured by `measured_at_source`:

| source | rows |
|---|---|
| `mtime` (unstamped) | 48 |
| `field:generated_at` | 3 |
| `field:at` | 1 |
| `field:as_of` | 1 |

CORRECTION to the register's framing ("arming assert_fresh today blocks 92 pct of rows"):
the split is **by category, not uniform**. All 5 stamped rows are `category="ledger"`
(`data/cache/eval_gate/`: `backtest_fwer.jsonl` via `at`,
`e4_promotion_trial_2026-09-01.json`, `hedge_trial_2026-09-01.json`,
`s06_stacker_trial_2026-09-03.json` via `generated_at`, plus the manifest's own `as_of`).
All 48 unstamped rows are `category="evidence"` under `docs/evidence/tracking/**` and
`docs/evidence/{calibration,demo}/`.

Measured: `_stale_rows(manifest, 30, ("ledger",))` = **0 of 5** stale, and 0 at
`max_age_days=2` as well. **The claim gate can be armed TODAY scoped to
`categories=("ledger",)`** -- `assert_fresh` already takes that argument. It is the
tracking-evidence writers, not the eval-gate producers, that lack stamps. Producer
modules that would need to stamp their JSON (identified from the paths, NOT edited by
this lane): `scripts/platformkit/tracking/baseball_scale_probe.py`,
`tracking/football_fieldview.py`, `tracking/football_snap.py`, and the
per-lane tracking evidence writers under `docs/evidence/tracking/*_2026-09-0*/`
(soccer/tennis packet + summary writers). S27's gate should scope to `ledger` rather than
wait on 48 producer stamps.

## Tests (per file only)

| file | result |
|---|---|
| `scripts/platformkit/eval_gate/test_gate_manifest_measured_at.py` (extended 4 -> 6) | 6 passed |
| `scripts/platformkit/eval_gate/test_gate_manifest.py` | 14 passed |
| `scripts/platformkit/mcp/test_gate_manifest_tool.py` | 7 passed |
| `scripts/platformkit/eval_gate/test_harness_health_report.py` | 4 passed |

25 passed across the three reader/owner files in the same run. `gate_manifest.py` is
283 LOC (<= 300), ASCII.

## NOT VERIFIED

- No producer module was edited; S45(c) is a report, and no stamp was added anywhere.
- The `ledger`-scoped arming is measured but NOT armed -- no caller passes
  `--max-age-days` or `categories` yet; that is S27's row.
- `_FUTURE_TOLERANCE_DAYS` is a fixed module constant, not a CLI flag; no clock-skew
  distribution was measured to choose 1.0 day.
- A future mtime (as opposed to a future declared field) was not exercised against a real
  on-disk artifact, only through the shared code path.
- No prereg seal and no ledger charge: this is audit tooling, not a scored trial.
  `data/cache/eval_gate/backtest_fwer.jsonl` was never opened by this lane.
