# S71 -- the answer layer to its non-gated ceiling (2026-09-03)

Fixes the seven defects the I2 gap finder measured in
`docs/evidence/harness/INTELLIGENCE_GAPFINDER_2026-09-03.md` section 4 (F1-F7),
all inside `scripts/platformkit/**`. No human-gated tree was touched; no assert
in `tests/platformkit/mcp_server/test_envelope_contract.py` was weakened and the
probe file `docs/evidence/answer_probe_50.json` is byte-identical (Q3).
Calibration language only (Q6).

## The bar and the honest result

    python -m pytest tests/platformkit/mcp_server/test_envelope_contract.py -q -p no:cacheprovider

| run | result | red probes |
|---|---|---|
| BEFORE (this session, premise re-measured per Q8) | `29 failed, 22 passed in 65.74s` | A01 A06 A09 A11 A13 S01-S03 C01-C03 M01-M03 W01-W04 R01-R05 H01 X01 X02 X04 X05 X06 |
| AFTER (F1-F7) | `5 failed, 46 passed in 60.82s` | W01 W02 W03 W04 H01 |

**The bar was <= 1 red. It is 5. NOT MET, and the bar was NOT moved.** The five
survivors are exactly the two diffs this lane was told to leave to the human:

- **W01-W04 `OK_ASOF_IS_WALL_CLOCK` -- P2.** `answers/winprob_dispatch.py:93`
  stamps `as_of = _now_iso()`. The corpus date is known only to the dispatcher /
  `predict_matchup`; the envelope's `source_artifact` is the *module*
  `scripts/platformkit/predict_matchup.py`, so no shared boundary fix can honestly
  supply a data date -- using that module's mtime would present a code date as a
  corpus date. F1 does now flip their `OK_NO_STALENESS_DAYS` half (each was a
  two-breach red before).
- **H01 `OK_NO_SOURCE_ARTIFACT` + `OK_NO_AS_OF` -- P3.** `tools._system_health`
  must cite its three artifacts and convert `freshness_sla.generated_at` (an
  epoch float) at the boundary.

The gap finder's proposed row said "H01 remains the only red until P3". That was
optimistic: F1 alone cannot clear the wall-clock breach on W01-W04, because
`staleness_days` and `as_of` are separate asserts. Corrected here.

## The seven fixes

| # | file : change | evidence |
|---|---|---|
| F1 | `mcp_server/artifact_tools.finalize()`, called from `mcp_server/tools.handler_for` -- the single point every MCP call passes through. An `ok` envelope naming an existing file gains `staleness_days` (from its own `as_of` when that parses, else the file mtime) plus `staleness_days_source` saying which. `no_data`/`not_supported`/`refused`/`ambiguous` returned untouched | 28 probes lost `OK_NO_STALENESS_DAYS`; 4 asserts in `test_artifact_tools.py` |
| F2 | `artifact_tools.mechanism_exposure`: reads `game_sheets` first, `games`/`rows` kept as fallbacks | real id `2025-10-21-GSW-LAL-0` returns its sheet (0/1,317 addressable before); bogus id still `no_data` |
| F3 | `artifact_tools.execution_status`: the artifact's own `status` passes through when it is one of the four not-ok statuses, with `verdict` in the note. `pm_trading/clv_daily_readout.py:138`: `as_of` is `now_iso` with no settled rows and the caveat moved to `as_of_note` | X06 was `ok` over an artifact reading `status: no_data`, `verdict: INSUFFICIENT`, `as_of: "...+00:00 (no rows)"` (unparseable). Now `no_data` + note |
| F4 | `intel_query/compose_matchup.py`: outer `as_of` = newest of the eight blocks' own `as_of` (parsed as datetimes, not strings); the call time keeps `computed_at` | M01-M03 stamped `_now_iso()` on data months old |
| F5 | `answers/resolver_registry.mechanism_effect`: try name-contained-in-query (`_mech_tokens(name) <= q_tokens`) BEFORE the existing query-contained-in-name test | "why does lefty advantage on return hold or not hold?" was `not_supported`; three phrasings of `lefty_advantage_on_return` now resolve to one hypothesis. 19 pre-existing tests unchanged |
| F6 | `answers/resolver_registry.calibration_number`: serves the newest TRACKED `docs/evidence/calibration/<sport>_reliability_<date>.json` (S05b) with the filename date as `as_of`, plus `verdict` + `prereg_path` + `prereg_seal_sha256`; the gitignored vault scoreboard is the labelled `FALLBACK`. Brier comes from the artifact's stored Murphy decomposition (`reliability - resolution + uncertainty`), not a new fit | nba was served from a 41-day-old gitignored file (`no_data` on a clone). Now nba 1,814 rows ECE 0.053328 -> 0.024843, seal `9051BB6E...` |
| F7 | `analytics_verify/sentinel.build_report`: `overall` is DISCREPANT / VERIFIED / STALE / UNCHECKABLE / INSUFFICIENT in that order -- never VERIFIED at `n_verified == 0` | the served report read `overall: VERIFIED` at 0 verified / 10 STALE / 1 UNCHECKABLE. Re-run locally: `overall=STALE verified=0 stale=10 uncheckable=1` |

## Tests (per-file only)

| file | result |
|---|---|
| `tests/platformkit/mcp_server/test_envelope_contract.py` | 5 failed, 46 passed (above) |
| `tests/platformkit/mcp_server/test_artifact_tools.py` | 8 passed (5 before, +3 for F1/F2/F3) |
| `tests/platformkit/mcp_server/test_edge_refusal.py` | 16 passed -- refusal rules untouched, E-probes still refused |
| `tests/platformkit/mcp_server/test_server.py` | 8 passed |
| `scripts/platformkit/intel_query/test_compose_matchup.py` | 7 passed (6 + F4) |
| `scripts/platformkit/answers/test_mechanism_effect.py` | 20 passed (19 + F5) |
| `scripts/platformkit/answers/test_calibration_scoreboard_regex.py` | 4 passed (3 + F6 fallback) |
| `scripts/platformkit/answers/test_calibration_resolver.py` | 13 passed |
| `scripts/platformkit/answers/test_resolver_registry_routing.py` | 37 passed |
| `scripts/platformkit/answers/test_answer_consistency_tennis.py` / `test_answer_quality_tennis.py` | 10 / 60 passed |
| `scripts/platformkit/intel_query/test_ask.py` | 46 passed (568 s) |
| `tests/platformkit/analytics_verify/test_sentinel.py` | 9 passed (8 + F7) |
| `tests/platformkit/analytics_verify/test_answers.py` / `test_cycle.py` | 15 / 3 passed |
| `tests/platformkit/execution/test_paper_week_rollup.py` | 4 passed (F3 producer half pinned) |

## Additivity (B2) and the one re-pinned assert

- `staleness_days` / `staleness_days_source` / `computed_at` / `as_of_note` are new
  keys; no key was renamed or removed. `calibration_number` keeps every key its
  two readers use (`contract_client.py:51` and `qa_bank.py:176` read
  `baseline_brier`, `improved_brier`, `baseline_ece`, `improved_ece`, `n`, `method`).
- Readers of `sentinel.overall` (`analytics_verify/answers.py:128`,
  `cycle.py:53`) pass the string through; neither gates on the literal "VERIFIED".
- ONE existing assert changed value:
  `test_calibration_scoreboard_regex.test_calibration_number_nba_returns_real_data_not_no_data`
  pinned `improved_ece == 0.03113`, the vault scoreboard's number. F6 changes the
  truth source, so it now pins the tracked artifact's `0.024842541854003943` and
  additionally pins `source_artifact`, `as_of` and the prereg seal -- strictly more
  than before. The two regex tests that guard the fallback parsing are unchanged.

## NOT VERIFIED

- **The resident MCP server (pid 11348) still serves the OLD code.** Its restart is
  human (gap finder section 0/5). Nothing here was probed through the live server.
- The bar of <= 1 red is NOT met (5 red). W01-W04 and H01 are unfixed, by
  instruction, not by measurement.
- `data/cache/analytics_verify/sentinel_report.json` was re-run locally to confirm
  F7 end-to-end; `data/` is gitignored, so a fresh clone still holds no report and
  a box that has not re-run the producer still serves the old VERIFIED headline.
- `data/frontend/analytics/execution_status.json` was NOT regenerated: its `as_of`
  still carries the "(no rows)" suffix on this box. X06 goes green through the
  tool-side status pass-through (F3a); the producer fix (F3b) only takes effect on
  the next `clv_daily_readout` run.
- F6's Brier is the Murphy identity over the artifact's stored components. It was
  not cross-checked against an independently computed Brier on the same corpus --
  the vault scoreboard scores a DIFFERENT corpus (nba 4,846 rows vs 1,814), so no
  comparison is available.
- F8-F11 from the gap finder (injury_report player arg, strength_atlas prose
  `as_of`, tracking_program_status hard-coded headline, harness_health refresher
  staleness) are NOT in this lane and remain open.
- Timings are single runs on this box; `test_ask.py` at 568 s is dominated by
  subprocess predictors.
