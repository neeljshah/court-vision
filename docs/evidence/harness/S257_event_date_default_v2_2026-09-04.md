# S257 -- event-date default v2 (CLOSED AT LIMIT)

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q1-Q9.
Calibration language only. This is a closed calibration comparison, not a shipped result.

## Premise and preregistration

The exact pre-preregistration command `python -m scripts.platformkit.eval_gate.calibration_report` completed. It printed `mlb/nba/soccer/tennis: <n> rows; prediction=p_base; verdict=FLATTENED; reproduction_max_abs_diff=0.0`. Its no-flag branch was `per_unit = "--per-unit" in args`, passed `{}` to `build_report`, and published `order_basis=POSITIONAL-ORDER`; the premise held.

The archived S50 pairs were read one JSON at a time:

| sport | positional after-ECE | per-unit after-ECE |
| --- | ---: | ---: |
| nba | 0.0248425418540039 | 0.0265834105558316 |
| mlb | 0.00807682464585021 | 0.0126655959300471 |
| soccer | 0.00930178868899538 | 0.0287220888287835 |
| tennis | 0.00840308976184882 | 0.0154027235190685 |

Preregistration path: `docs/evidence/harness/S257_event_date_default_v2_prereg_2026-09-04.md`; commit `46e25909d56158d7745549dee8ddc28628e119cb`; seal `A9AF3C4330263D71A6A5E4A30286190F411610C2552FF99810EA6C5FC4F8FC3C`. `git show HEAD:docs/evidence/harness/S257_event_date_default_v2_prereg_2026-09-04.md | head -n 43 | sha256sum` returned `a9af3c4330263d71a6a5e4a30286190f411610c2552ff99810ea6c5fc4f8fc3c  *-`.

## Q4 and Q9 evidence

Both arms use `cpcv_evaluate` with `n_groups=8`, `n_test_groups=1`, shared same-team/matchup purge, and symmetric one-day embargo. Each regenerated report asserts every calibrated prediction came from that callback. Paired rows carry both squared losses, cluster id, timestamp, and reconstructible AS-OF route:

- `docs/evidence/harness/S257_event_date_default_v2_2026-09-04_paired_nba.json`
- `docs/evidence/harness/S257_event_date_default_v2_2026-09-04_paired_mlb.json`
- `docs/evidence/harness/S257_event_date_default_v2_2026-09-04_paired_soccer.json`
- `docs/evidence/harness/S257_event_date_default_v2_2026-09-04_paired_tennis.json`

Inputs were opened separately, all n/a-tabular: `C:/Users/neelj/nba-track-a17/data/cache/combo/gate_corpus_nba.parquet` (201706 bytes, SHA-256 `716F6F5F3F2181051E352936EFA60D616C9DE029A026B85CC585D6ED20CB0AAF`); `C:/Users/neelj/nba-track-a17/data/cache/combo/gate_corpus_mlb.parquet` (1645142 bytes, `AC60C9CB18958C20FF53D7D0B698700375B6A0CE15E7EF0ECD20FB730E0903BD`); `C:/Users/neelj/nba-track-a17/data/cache/combo/gate_corpus_soccer.parquet` (6053712 bytes, `E0D2F13E7A53B3ED578E81E38DB82F14BB6D3A71E31A9C7CB636D5B4C7E92BC6`); `C:/Users/neelj/nba-track-a17/data/cache/combo/gate_corpus_tennis.parquet` (2745405 bytes, `22D006F2B4F7A7186876E133508E1E9DDF14AF3570F1D20A73D73D1D3669D700`).

## Result and limit

No flag wrote the existing base JSON names; `--positional` wrote `*_reliability_positional_2026-09-03.json`. Zero rows were dropped in all reports.

| sport | event-date base ECE | base abs diff | positional ECE | positional abs diff |
| --- | ---: | ---: | ---: | ---: |
| nba | 0.0390022022088066 | 0.0124187916529750 | 0.0453756842862463 | 0.0205331424322423 |
| mlb | 0.00455266167120642 | 0.00811293425884071 | 0.00430035239903193 | 0.00377647224681829 |
| soccer | 0.0114508611906899 | 0.0172712276380936 | 0.00301571447643407 | 0.00628607421256131 |
| tennis | 0.00427126697967418 | 0.0111314565393944 | 0.00559808266913181 | 0.00280500709271701 |

The required maximum absolute difference of 1e-9 is not met by either arm. The shared Q4 evaluator changes the historical local-walk values, so the simultaneous reproduction bar cannot be met. CLOSED AT LIMIT; no bar moved. Soccer's six-division interleave and the WTA-dominated tennis cost remain named in S50.

## Readers, identity, and test

No caller was edited. Import callers found: `ingame_calibration_report.py` (`_from_bins`), `s200_regime_key_oof.py` (`build_report`), `s202_two_way_neff.py` (`_oof_per_regime`), `s204_close_reference.py` (`_bin_table`, `_oof_per_regime`), `s205_calib_bakeoff.py` (report helpers), `resolver_registry.py`, and tests. Base-path readers: `s200_regime_key_oof.py`, `resolver_registry.py`, `test_calibration_report.py`, and `test_calibration_scoreboard_regex.py`; the positional suffix has no reader. Base names stay unchanged; fields are additive.

Route SHA-256: `calibration_report.py` `EB45011A59667F819C2C75AF4CFE9E1B8B648919BA0BEA4D7A7CCD10A124C00D`; `s257_event_date_default.py` `F4119316825137209A08467B657249E66DC1707E7A63F44976E871B6CF19160B`; `s205_calib_oof.py` `8A7D842312BC7746D8751DABFB42F6B91ED07757B70AB3BF12B2992A5EEC3531`; `cpcv_engine.py` `6F622DC107B432DF0BDC1F4700E44D900DE5C5ADAAD9657E15A22C579269C6E6`.

Test: `python -m pytest scripts/platformkit/eval_gate/test_s257_event_date_default.py -q` returned `1 passed`.

## NOT VERIFIED

- The event-date walk is not the default and the rejected default/base rewrite is not landed.
- The three base-value consumers (`resolver_registry.py`, `test_calibration_report.py`, and `test_calibration_scoreboard_regex.py`) were not switched to an explicit per-unit key in one additive row.
- No production caller was verified to consume the event-date result without the opt-in `--per-unit` flag.
