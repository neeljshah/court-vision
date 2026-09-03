# S161 -- n_eff re-quote archive

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.
Calibration language only. This is an S-row; reproduction replaces an eye check.

## Result

The S158 construct denominator is **45 published n_eff positions**. The completed manifest
contains **45 of 45 rows**: 2 durable re-quotes, 0 re-labels, and 43 LOST rows. The accounting
denominator reached is **45 / 45**. No verdict, threshold, module, ledger, or feature flag moved.

The durable re-quotes are the two S87 MLB positions. The 227 source JSONL tables were streamed
one file at a time, copied verbatim under `neff_requote_2026-09-04/S87_mlb_units/`, and hashed as
the directory fingerprint recorded in `S87_mlb_stream_record.json`. The all-tick recomputation is
`n_ticks=78986`, `n_games=227`, `rho=0.27091658718434597`, `n_eff=831.4655281089265`; the
published one-decimal value was 831.5. The informative-tick recomputation is
`n_ticks=23812`, `n_games=227`, `rho=0.19340711977624836`, `n_eff=1128.811984694203`; the
published one-decimal value was 1128.8. Both agree at published precision.

`source_inventory.csv` records the local source existence, size, mtime, and hash where a source
exists. The copied calibration summary is durable evidence of three published values, but its
cited per-tick series is absent; those rows are correctly marked LOST rather than presented as
recomputations.

## Manifest summary

| category | positions |
|---|---:|
| durable re-quoted | 2 |
| re-labelled | 0 |
| LOST | 43 |
| accounted | 45 / 45 |

The direct re-quote metric is 2 / 45. The acceptance accounting bar is 45 / 45: every S158
position is named in `neff_requote_2026-09-04/manifest.csv`, including every unavailable series.

## NOT VERIFIED

- S58 T2 pooled and D1/E1/I1: the cited per-event CSV is absent.
- S58 trial 1, trial A, S87 trial A, and S87 trial B: their cited per-unit CSVs are absent.
- S80 and S87b player-grain values: the cited CSV and S83 JSON are absent.
- S87b calibration values: the retained JSON is copied, but the cited S06 per-tick series is absent.
- S116 and S152: the landed and re-run S116 CSVs are absent.
- All 20 S137 positions: the cited re-baseline JSON is absent.

Every LOST row records its last cited date, 2026-09-03, in the manifest. No missing value was
recreated from prose.

## Contract self-check

- B1: all 45 S158 positions are present; no unavailable row was dropped.
- B2-B6: this adds evidence and one focused test only; no existing schema, reader, module, or
  deployment path changed.
- B7/Q7: this is an exhaustive 45-position construct, and its two available values use the full
  227-unit source rather than a head slice.
- B8-B10/Q1-Q5/Q9: no model was fit, no scored comparison or ledger action occurred, and no bar
  changed.
- Q6: calibration language only.
- Q8: the source premise was re-measured at inspection time and is recorded in `source_inventory.csv`.

Test: `python -m pytest tests/platformkit/ingame/test_s161_neff_requote_manifest.py -q`.

## ATTEMPT 2 -- restored-source fix pass

Q8 premise re-measurement: the restored worktree has all eleven distinct source paths named by
the 45-position enumeration (ten restored `data/` series plus the already-local calibration
summary). The FWER ledger remains absent and was not opened. `source_inventory.csv` records each
path, size, mtime, and SHA-256. No path is absent.

Before this pass, the manifest had 2 re-quoted rows and 43 LOST rows. After this pass it has 45 of
45 rows: 22 direct helper or requested algebraic re-quotes, 23 durable RE-LABELLED summary rows,
and 0 LOST rows. Every row states its tick rule: `all ticks`, or the published informative
per-game epsilon=1e-9 plus duplicate rule. The latter reproduces S87 MLB's 1128.8 at published
precision.

Small source tables are copied verbatim under `restored_sources/`. For the three files over 2 MB,
`source_artifacts.csv` records per-file SHA-256, row count, and columns. The existing S87 MLB
directory record remains the durable artifact for its 227 copied JSONL units. The three S87b
calibration rows use the requested algebraic calculation from their stored n_ticks, n_games, and
rho values.

The 23 RE-LABELLED rows are not hidden as re-computations: the copied S80/S137 JSON files preserve
the durable published summary, but their named underlying per-unit `series_csv` files are not in
this worktree. Their manifest notes identify that limit and print the source-summary delta where
it differs from the published label. They are durable, accounted findings, not LOST rows and not
new calibration claims.

| attempt | direct re-quoted | re-labelled | LOST | accounted |
|---|---:|---:|---:|---:|
| 1 | 2 | 0 | 43 | 45 / 45 |
| 2 | 22 | 23 | 0 | 45 / 45 |

Contract self-check for attempt 2:

- B1: all 45 enumerated positions remain present; none is excluded.
- B2-B6: evidence and its focused integrity test are additive only; no module, verdict, ledger,
  deployment path, threshold, or feature flag changed.
- B7/Q7: this is the exhaustive 45-position construct. Re-quoted tables use complete archived
  sets; S-row reproduction replaces an eye check.
- B8-B10/Q1-Q5/Q9: no model was fit or scored, no FWER ledger was opened, and no bar moved.
- Q6: calibration language only. Q8 was satisfied before the reconstruction by the source
  inventory re-measurement.

## Corrections at landing (Opus verifier, 2026-09-04)

- The 23 RE-LABELLED rows were re-labelled from summary JSON because their named per-unit series were absent from WORKTREE a10; all 8 distinct cited series exist in the MAIN repo (69 KB to 75 MB). Direct re-quotes are a follow-up (register note under S161).
- The rho behind the three S87b_calibration_* re-quotes derives from data/cache/eval_gate/s06_stacker_series_2026-09-03.csv, now listed in source_inventory.csv.
- The evidence test no longer asserts "no LOST row" (a bar the spec never set); it requires a named source path on any LOST row.
- Verifier reproductions: 6 rows across 5 sources at 0.0 delta; 5 copied tables sha256-identical to their main-repo sources.
