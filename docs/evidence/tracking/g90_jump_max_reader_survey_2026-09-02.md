# G90: jump-max reader survey

## Result

ACCEPT. The live gate field is `jump_max`; `jump_p95` remains the retained raw
p95 compatibility measurement. This survey found two live summaries that were
still treating the old field as the current thresholded gate: the tracking
brain/resolver and corpus A/B baseline comparison. Both now read `jump_max`
when present and use `jump_p95` only for a pre-G88 row that lacks the new
field. No harness calculation, verdict, bar, coordinate contract, historical
record, pod, or feature flag changed.

## Search method and scope

The G81 method was followed: enumerate first, inspect each reader's operation,
then reproduce every live broken behavior before changing it. `rg` is absent
in this worktree, so the equivalent commands were:

```text
git grep -l -I -E 'jump_p95(_ft_per_s)?' -- '*.py'
git grep -n -I 'jump_max' -- '*.py'
git grep -n -I -E 'FAILURE_RE|failure.*split|split.*failure|for .* in .*failures|for .* in .*get\("failures"' -- 'scripts/platformkit/**/*.py' 'scripts/platformkit/*.py' 'domains/**/*.py'
git ls-files -- 'docs/evidence/**' 'data/**' | [JSON/JSONL/CSV filter] | Select-String -SimpleMatch 'jump_p95'
```

The final stored-record scan found **22 files / 98 matching lines**. The
runtime survey is **n = 14 unique reader or failure-preserver paths**: ten
structured-field paths and four additional failure-string paths. Test-only
fixtures and harness producers are listed separately and are not counted as
runtime readers.

## Per-consumer decision

| Consumer | What it reads or does | Verdict |
|---|---|---|
| `scripts/platformkit/tracking_brain.py` | Computes threshold margins and action priority from report metrics. | Needs fix; fixed to prefer structured `jump_max`, using p95 only when an old row has no max. |
| `scripts/platformkit/answers/tracking_resolver.py` | Wraps the brain's scorecard and names its metrics in the user-facing caveat. | Needs fix; fixed to name `jump_max` because it delegates current gate scoring to the brain. |
| `scripts/platformkit/tracking_corpus_ab.py` | Renders the gate summary, compares current reports with a stored baseline, and joins failures only for display. | Needs fix; fixed to render/diff `jump_max`, with an old-baseline p95 fallback and both fields retained in new rows; it has no failure-string parser. |
| `scripts/platformkit/answers/corpus_builder_v2.py` | Copies the literal report p95 into an artifact-derived answer. | Safe; it reports the retained raw p95, not the gate statistic. |
| `scripts/platformkit/baseball_calib_probe.py` | Selects the literal raw p95 into a diagnostic probe. | Safe; diagnostic p95 remains present and semantically p95. |
| `scripts/platformkit/corpus_rescore.py` | Ranks raw numeric report deltas, including p95. | Safe; it retains p95 as an informational delta and independently preserves the report verdict. |
| `scripts/platformkit/evidence_page.py` | Renders report p95 and preserves each failure verbatim. | Safe; p95 is explicitly a raw field and failures are not parsed. |
| `scripts/platformkit/tracking/depth_replay.py` | Replays the raw p95 alongside depth quantities. | Safe; it is an explicitly raw-p95 replay. |
| `scripts/platformkit/tracking/tennis_sequential_plan.py` | Includes raw p95 in its evidence payload. | Safe; it does not infer the harness gate from that field. |
| `scripts/platformkit/tracking_timebase.py` | Produces the reporting-only p95-per-second value. | Safe; `jump_p95_ft_per_s` remains derived from the retained p95 and is non-gating. |
| `scripts/platformkit/intelligence_brief.py` | Parses `name value operator threshold` with a name-agnostic regex. | Safe; `jump_max` matches the same grammar and is counted rather than missed. Structured fields would still be preferable for a future gate-oriented brief. |
| `scripts/platformkit/night_report.py` | Preserves failure strings wholesale, except an explicit coordinate-contract filter. | Safe; it has no jump-name branch. |
| `scripts/platformkit/track_daemon.py` | Truncates/stores/prints failure heads without classifying their names. | Safe; it preserves the renamed string. |
| `scripts/platformkit/track_daemon_done.py` | Extends the harness failure list into its sidecar. | Safe; it preserves the renamed string. |

The following grep hits are producers or a distinct measurement, not report
field consumers: `tracking_harness.py` and `metric_local_profile.py` produce
the additive fields; `g82_jump_statistic_measure.py` and `jump_gap_probe.py`
compute their own research p95 values; and
`domains/baseball/tracking/scale_anchor.py` uses separate
`scale_jump_p95_*` fields. Test-only readers retain frozen/raw-p95 fixtures;
the G72 normalizer deliberately maps the known old failure name to the new
one, while coordinate-contract split assertions do not inspect jump failures.

## Required before/after reproduction

The constructed current report had `jump_p95=1.0`, `jump_max=10.0`, and all
other quality metrics clear. Its tennis bar remains 8.0. Before this reader
repair:

```text
brain_worst=coverage
baseline=g not worse
```

The brain therefore missed the current failing gate and corpus A/B did not
name the current-key regression. After the repair, with the same objects:

```text
brain_worst=jump_max
baseline=g WORSE: jump_max 1.000->10.000
```

The focused regression test proves both that behavior and the legacy fallback:

```text
python -m pytest scripts/platformkit/test_g90_jump_max_readers.py -q
1 passed in 3.46s
```

## Stored baselines, fixtures, and golden records

All 22 literal-containing committed JSON/JSONL/CSV files are below. Only
`tennis_baseline.json` is a live default input to corpus A/B; its old key is
accepted by the explicit fallback. Every other path is a frozen historical
record or evidence fixture and was not rewritten.

| Path | Classification |
|---|---|
| `g72_metric_local_profile/court_feet_after_report.json` | Frozen record |
| `g72_metric_local_profile/court_feet_before_report.json` | Frozen record |
| `g72_metric_local_profile/court_feet_before_reports.json` | Frozen record |
| `g72_metric_local_profile/metric_local_after_report.json` | Frozen record |
| `g72_metric_local_profile/metric_local_before_report.json` | Frozen record |
| `g77_scorecard_scope/constructed_inputs.json` | Frozen fixture |
| `g77_scorecard_scope/constructed_outputs.json` | Frozen fixture |
| `g77_scorecard_scope/mixed_after_scorecard.json` | Frozen fixture |
| `g77_scorecard_scope/mixed_before/reports/baseball/court_feet_pass.json` | Frozen fixture |
| `g77_scorecard_scope/mixed_before/reports/baseball/metric_local.json` | Frozen fixture |
| `g77_scorecard_scope/mixed_before_scorecard.json` | Frozen fixture |
| `g82_jump_statistic/per_table_statistics.csv` | Frozen record |
| `g82_jump_statistic/reproduced_sweep.csv` | Frozen record |
| `g88_jump_statistic_impl/reader_survey.csv` | Frozen record |
| `g88_jump_statistic_impl/sensitivity.csv` | Frozen record |
| `g88_jump_statistic_impl/verdict_impact.csv` | Frozen record |
| `recovered_pod_artifacts/footage_cycle_ledger.jsonl` | Frozen recovered ledger |
| `tennis_baseline.json` | Live corpus-A/B baseline input; read through the old-key fallback |
| `tennis_player_select_limit_2026-09-04/report.json` | Frozen record |
| `tennis_sequential_plan_2026-09-01/tennis_09.json` | Frozen record |
| `tennis_sequential_plan_2026-09-01/tennis_10.json` | Frozen record |
| `tennis_sequential_plan_2026-09-01/tennis_nyYk2nPZAwY_720p.json` | Frozen record |

## Ledger compatibility

The supplied premise confirms real `footage_cycle_ledger.jsonl` rows with a
`jump_p95` key. `footage_cycle.score_item` appends the whole harness report, so
new rows add `jump_max` while retaining the raw `jump_p95`; historical rows
remain old-key-only. Readers must select `jump_max` per new row and fall back
only when that field is absent, never aggregate the two fields as one series.
The repaired brain and corpus A/B do exactly that. `progress_watchdog` reads
these ledgers only for row counts/statuses; no inspected reader aggregates
both metric keys. The local footage-cycle ledger was absent at audit time, so
no live row was modified or treated as verification evidence.

## VERIFIER_CONTRACT self-check

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, section A (including
A7) and section B.

- **A7:** Confirmed at memo time that this memo, `specs/G90_spec.md`,
  `VERIFIER_CONTRACT.md`, the G81 precedent, all three modified reader files,
  `test_g90_jump_max_readers.py`, `RESULTS_LEDGER.md`, and
  `TRACKING_GAPS_2026-09-01.md` exist. The absent live footage-cycle ledger is
  explicitly NOT VERIFIED, not a pass.
- **B1:** No rows are excluded; the reproduction uses all fields of one named
  constructed report.
- **B2:** `jump_max` remains additive, raw `jump_p95` remains present, and old
  baseline/report rows receive an explicit fallback. Every enumerated reader
  has a verdict above.
- **B3:** No absent-evidence gate, quarantine, or pass-through path changed.
- **B4:** No claim, queue, retry, or ownership path changed.
- **B5:** No pod deployment, copy, restart, kill, or remote action occurred.
- **B6:** No module moved or retired; the one new test imports the full package
  paths.
- **B7:** No render or head-slice evidence is claimed; this is a deterministic
  reader-contract reproduction.
- **B8:** No fitted model or self-fit metric is asserted.
- **B9:** The reproduction has a single named report and compares distinct
  structured fields; no denominator is recycled.
- **B10:** `tracking_harness.py`, every numeric bar, every verdict rule, and
  the coordinate contract are untouched.

## NOT VERIFIED

- No pod or production-reader execution occurred; the pod remained read-only.
- The current local `data/tracking/footage_cycle_ledger.jsonl` was absent; the
  supplied real-row fact was not substituted with a synthetic live ledger.
- No full test suite was run; only the required new per-file test was run.
