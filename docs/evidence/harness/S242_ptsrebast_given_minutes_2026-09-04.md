# S242 PTS REB AST Given Minutes

## Verdict

PREMISE FALSIFIED. The binding before-condition is false because the prior
S228 archive already contains 14,231 paired rows across PTS, REB, and AST with
CRPS. No implementation is needed. No model, scored comparison,
preregistration, test, register row, or ledger row was created.

This memo follows `docs/evidence/tracking/specs/S242_spec.md` and
`docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q. Work ran
locally in `C:\Users\neelj\nba-track-a18` because the row is a local source
and store availability assessment; no pod or video route was used.

## Binding before-condition

The spec's named before-condition is that zero CRPS numbers exist for the
seven prop stats and only point MAE exists. The verifier reproduced the prior
paired artifact and found that condition false:

REPRODUCED: paired means PTS=3.910120 (n=5,568), REB=1.613150 (n=5,029), AST=1.317556 (n=3,634), pooled=2.436377 (docs/evidence/harness/S228_pregame_prop_close_upset_2026-09-04_paired.csv:1).

The 14,231-row archive is documented at
`docs/evidence/harness/S228_pregame_prop_close_upset_2026-09-04.md:49`, and
the archived CRPS result is documented at that memo's line 59. The narrower
attempt-1 search found zero CRPS fields in the quantile summary and zero
source hits, but it did not find the prior S228 evidence artifact. The named
before-condition is therefore false, so S242 closes as PREMISE FALSIFIED and
requires no implementation.

## Attempt-1 text (superseded)

### Verdict text

CLOSED AT LIMIT. The binding before-condition holds, but this worktree cannot
construct a fresh chronological labelled holdout for the required scored
comparison. No model, scored comparison, preregistration, test, register row,
or ledger row was created.

### Binding before-condition text

The spec's named before-condition is that zero CRPS numbers exist for the
seven prop stats and only point MAE exists. It was rerun before any proposed
change with this exact command:

```powershell
$q = Get-Content -Raw 'data/models/quantile_pergame_metrics.json' | ConvertFrom-Json
$stats = @('pts','reb','ast','fg3m','stl','blk','tov')
foreach ($stat in $stats) {
  $entry = $q.stats.$stat
  $names = if ($null -eq $entry) { '' } else { ($entry.psobject.Properties.Name -join ',') }
  $crps = if ($null -eq $entry) { @() } else { @($entry.psobject.Properties | Where-Object { $_.Name -match 'crps' }) }
  Write-Output ("{0}: fields=[{1}] crps_fields={2}" -f $stat,$names,$crps.Count)
}
git grep -n -i 'crps' -- 'src/prediction/quantile_props.py' 'src/prediction/quantile_calibration.py' 'src/prediction/prop_quantiles.py'
Write-Output "source_crps_exit=$LASTEXITCODE"
```

Its output was:

```text
pts: fields=[0.1,0.5,0.9,coverage_80,avg_interval_width] crps_fields=0
reb: fields=[0.1,0.5,0.9,coverage_80,avg_interval_width] crps_fields=0
ast: fields=[0.1,0.5,0.9,coverage_80,avg_interval_width] crps_fields=0
fg3m: fields=[0.1,0.5,0.9,coverage_80,avg_interval_width] crps_fields=0
stl: fields=[0.1,0.5,0.9,coverage_80,avg_interval_width] crps_fields=0
blk: fields=[0.1,0.5,0.9,coverage_80,avg_interval_width] crps_fields=0
tov: fields=[0.1,0.5,0.9,coverage_80,avg_interval_width] crps_fields=0
source_crps_exit=1
```

The condition therefore holds. It is not declared falsified.

## Quantile premise and current coverage

Both required modules were read in full.

`src/prediction/quantile_props.py` fits q10/q25/q50/q75/q90 regressors and
returns an in-memory prediction vector. It does not emit a persisted
per-player q10/q50/q90 row or score a holdout. `src/prediction/quantile_calibration.py`
constructs q10/q50/q90 arrays for validation and holdout rows in memory, then
writes only a summary JSON under `data/models/`. Neither module produces a
real persisted per-player quantile row suitable for the S242 differential.

The existing 3,949-byte summary reports an historical coverage field, but it
is not a fresh chronological holdout reproduction and is not used as a S242
score. Fresh coverage is not measurable here: `data/nba` has zero
`gamelog_*.json` files, and none of the three required intelligence stores
contains the realised PTS, REB, or AST target.

## Limit and inputs

The following inputs were opened one store at a time. They are all below the
300 MB rail.

| Path | Bytes | Rows | Fields relevant to S242 |
|---|---:|---:|---|
| `data/intelligence/momentum_signals.parquet` | 5622181 | 673204 | player_id, asof_date, stat, l3_actual, l20_baseline, l20_std, momentum_z |
| `data/intelligence/per_player_calibration.parquet` | 11143409 | 307643 | player_id, asof_date, stat, bias_z_l20, sigma_resid |
| `data/intelligence/gt_weighted_forms.parquet` | 6850050 | 99157 | player_id, game_date, game_id, PTS/REB/AST form and minute form fields |
| `data/models/quantile_pergame_metrics.json` | 3949 | n/a | existing quantile summary only |
| `data/models/props_pergame_metrics.json` | 5799 | n/a | recorded point-model metric summary |

The only label producer named by the quantile calibration route is
`src/prediction/prop_pergame.py::build_pergame_dataset`, which reads
`data/nba/gamelog_*.json`. The required metadata census returned:

```text
data/nba gamelog files=0 bytes= max_file=
```

S241 is also not available as a reusable minutes-quantile module in `HEAD`.
Its closure commit `3e5007f96` is not an ancestor of this branch and its memo
names an absent S233 filename. The current shared
`scripts/platformkit/eval_gate/cpcv_engine.py` exists and has symmetric
embargo and purge behavior, but it cannot create target labels that are absent
from the local inputs.

An additive module would either fit and score on unavailable labels or use
same-row form fields as a substitute outcome. The first is impossible in this
worktree; the second would violate B1, B8, Q4, and the spec's non-tautology
rule. This is the named limit.

## Required metric table

No rows were selected, excluded, or scored. The table is intentionally
complete rather than silently dropping any stat.

| Stat | CRPS | q10 pinball | q50 pinball | q90 pinball | q10-q90 coverage | Labelled point MAE | Holdout rows | Game clusters |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| pts | n/a | n/a | n/a | n/a | n/a | 4.83 | 0 | 0 |
| reb | n/a | n/a | n/a | n/a | n/a | 1.92 | 0 | 0 |
| ast | n/a | n/a | n/a | n/a | n/a | 1.39 | 0 | 0 |

The labelled point MAEs are the production-model chronological holdout values
in `docs/JOB_EVIDENCE_PACKET.md` lines 164-168. They are cited only as the
unchanged acceptance reference, not compared with an unavailable S242 score.

## Preregistration and scoring status

Preregistration path: not applicable.

Preregistration SHA-256 seal: not applicable.

No scored comparison was started, so no preregistration seal was required and
no hash can be misrepresented as predating a metric. No trial was charged; the
ledger was not opened and no K was read. No differential artifact exists
because there are no paired losses or as-of model rows to archive.

## Focused test

No additive module was created after the limit was established, so the
specified new synthetic CRPS/pinball test is inapplicable and was not run.

## Verifier self-check

- B1: no metric or exclusion set was computed.
- B2-B6: no schema, gate, deployment, retirement, or claim loop changed.
- B7-B9: no rows, renders, residuals, or denominators were used.
- B10 and Q3: no threshold changed.
- Q1, Q2, Q4, and Q9: no scoring or charged trial occurred.
- Q5: no AHEAD result is claimed.
- Q6: this memo uses calibration language only.
- Q7: no sampled or scored metric was entered.
- Q8: the binding before-condition was rerun and quoted above before this
  close; the separate label-availability limit is quoted exactly.

## Not verified

The additive conditional distribution, sealed preregistration, fresh
chronological coverage, CRPS, pinball losses, S241 minutes quantiles, paired
loss archive, and focused test remain unverified because no labelled holdout
exists in this worktree.

