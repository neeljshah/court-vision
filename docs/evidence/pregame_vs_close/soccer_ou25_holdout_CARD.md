# Pregame versus close data card: soccer_ou25_holdout.csv

calibration readout, paper only, not a verdict

- Source: football-data.co.uk league results, match stats and the Pinnacle closing
  Over/Under 2.5 goals price, held privately as `data/domains/soccer/matches.parquet`,
  `match_stats.parquet` and `odds.parquet`. Market: total goals over 2.5. Outcome
  orientation: p_model, p_close_devig and y all refer to OVER 2.5 (y = 1 when the match
  had 3 or more goals). Model: the `proof_soccer/beat_the_close_ou.py` walk-forward
  EW Poisson forecaster with a pooled Platt recalibration fit on the first half only.
- Licence ledger row: `docs/evidence/LICENCE_LEDGER.md` row 7, football-data.co.uk,
  verdict OK ("My data is free"; All Rights Reserved; no scope stated). Scope checked:
  the OK reasoning in that row notes we did not publish the data. This file publishes
  no raw price, only devigged probabilities, model probabilities and the binary
  outcome; whether that derived export is inside the OK reading is an owner check
  (see NOT VERIFIED).
- Devig method: proportional, applied before export (imp = 1/decimal price;
  p = imp_over / (imp_over + imp_under)). A Shin sensitivity is in the DM memo.
- Exclusions: odds rows with a missing or <= 1.0 over/under price dropped; inner
  join of model rows to odds on event_id; rows with a null model probability, close
  or outcome dropped; the first chronological half (fit split, 7,557 rows of 15,115)
  is excluded and only the held-out second half is exported. Upstream join and
  filter counts before the 15,115 are not itemised here.
- SHA256 of the private source files (identical to `docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md`):
  - `data/domains/soccer/matches.parquet`: 63cd075df7bbedd1892f17140ea0e4b8cf6038e846460d5efecbb31cd3838838
  - `data/domains/soccer/match_stats.parquet`: ae3f0257cf91ad8438386560ac47adcad7f6d6acb2f2406c81beccf1c0638f4e
  - `data/domains/soccer/odds.parquet`: dbaf592c89ecb3c4b7298d6b71c66c4abcc5618dc7c763e2199ffa8341320655
- Row count: 7,558 held-out rows, one unique match_id per match (7,558 clusters).
  Dates 2022-10-08 onward, date precision only (no kickoff time).
- CSV sha256: 68084c2d05836e1cbbfb61a96ee7eb676761ec4a90824e2bf8c005c6c48b0105 (710,594 bytes).
- Generated-by command (from the full private checkout, private trunk 5f4a346cf;
  the export calls `dm_recompute_pregame.rows_soccer()` read-only):
  `python -m scripts.platformkit.eval_gate.export_vs_close --out-dir docs/evidence/pregame_vs_close`
- Score command: `python -m scripts.platformkit.eval_gate.score_vs_close --csv docs/evidence/pregame_vs_close/soccer_ou25_holdout.csv --devig proportional`

CSV columns, in order: date_utc, match_id, p_model, p_close_devig, devig_method, y.
Full float precision; the scorer applies the reference clip at [1e-6, 1-1e-6].

Reading: the model TRAILS the devigged close (gap +0.0076 Brier, 95% CI
[+0.0059, +0.0092]). This reproduces the published DM memo row to four decimals.
MATCHES_CLOSE, had it been the verdict, would only mean the interval includes zero.

NOT VERIFIED: whether publishing derived devigged probabilities is inside the
football-data.co.uk OK reading (the ledger row was written for a non-published use);
kickoff timestamps (date only, so as-of ordering within a day is not shown);
itemised upstream exclusion counts.

## Scorer output (verbatim)

```json
{
  "schema": "score_vs_close/v1",
  "status": "OK",
  "n": 7558,
  "n_clusters": 7558,
  "devig_method": "proportional",
  "model_brier": 0.24653174209394257,
  "close_brier": 0.23895608751999672,
  "gap": 0.007575654573945858,
  "gap_sign": "positive = model trails the close; dm_stat has the same sign as gap",
  "ci95": [
    0.005944816121945759,
    0.009206493025945957
  ],
  "dm_stat": 9.105983862301864,
  "dm_p": 1.0772791656587416e-19,
  "mde": 0.002330468147908141,
  "mde_power": 0.8,
  "model_log_loss": 0.6861514938971582,
  "close_log_loss": 0.6706680132300011,
  "reliability": {
    "model": [
      {
        "mean_p": 0.42059991763949955,
        "observed_rate": 0.4576719576719577,
        "count": 756
      },
      {
        "mean_p": 0.45486053690145173,
        "observed_rate": 0.42328042328042326,
        "count": 756
      },
      {
        "mean_p": 0.47345110785673444,
        "observed_rate": 0.4775132275132275,
        "count": 756
      },
      {
        "mean_p": 0.4889054037255056,
        "observed_rate": 0.4708994708994709,
        "count": 756
      },
      {
        "mean_p": 0.5042739974367186,
        "observed_rate": 0.5224867724867724,
        "count": 756
      },
      {
        "mean_p": 0.5183400998465748,
        "observed_rate": 0.5251322751322751,
        "count": 756
      },
      {
        "mean_p": 0.533130455356135,
        "observed_rate": 0.5158730158730159,
        "count": 756
      },
      {
        "mean_p": 0.5512018593544109,
        "observed_rate": 0.541005291005291,
        "count": 756
      },
      {
        "mean_p": 0.5762200101054396,
        "observed_rate": 0.6066225165562914,
        "count": 755
      },
      {
        "mean_p": 0.6223479268849803,
        "observed_rate": 0.6211920529801325,
        "count": 755
      }
    ],
    "close": [
      {
        "mean_p": 0.3592440307772085,
        "observed_rate": 0.36904761904761907,
        "count": 756
      },
      {
        "mean_p": 0.41483845494037697,
        "observed_rate": 0.4021164021164021,
        "count": 756
      },
      {
        "mean_p": 0.44358212122050816,
        "observed_rate": 0.3994708994708995,
        "count": 756
      },
      {
        "mean_p": 0.46838336948163406,
        "observed_rate": 0.4656084656084656,
        "count": 756
      },
      {
        "mean_p": 0.4920839312492464,
        "observed_rate": 0.503968253968254,
        "count": 756
      },
      {
        "mean_p": 0.5162613080544255,
        "observed_rate": 0.5052910052910053,
        "count": 756
      },
      {
        "mean_p": 0.5432832100190249,
        "observed_rate": 0.5727513227513228,
        "count": 756
      },
      {
        "mean_p": 0.57330362517141,
        "observed_rate": 0.5965608465608465,
        "count": 756
      },
      {
        "mean_p": 0.6132617103856215,
        "observed_rate": 0.6384105960264901,
        "count": 755
      },
      {
        "mean_p": 0.6805149923556911,
        "observed_rate": 0.7086092715231788,
        "count": 755
      }
    ]
  },
  "verdict": "TRAILS_CLOSE",
  "reasons": {},
  "note": "calibration readout, paper only, not a verdict"
}
```
