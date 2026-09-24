# Pregame rows vs the devigged close: clustered DM recompute (2026-09-24)

**Result.** The MLB moneyline row and the soccer O/U-2.5 row both reproduce to four decimals, and
under the written interval rule both are **TRAILS_CLOSE**, not MATCH. Their 95 percent intervals
on the Brier gap exclude zero by a wide margin. The NBA moneyline row reproduces and is
**MATCHES_CLOSE**, because its interval includes zero. At n = 372 that interval is wide: its MDE
is 0.0150 Brier.

This memo does what `docs/QUANT_BRIEF.md` said was queued: it recomputes the intervals with the
public `dm_test.py`. It is a calibration measurement only. No edge or profit claim is made or
implied.

## Table

The scored games are the held-out second half of each harness's chronological overlap. d is the
per-game squared-error difference, loss_model minus loss_close, so positive d means the close is
sharper. The CI is the game-clustered DM 95 percent interval (Student-t with G - 1 degrees of
freedom). BSS is 1 - Brier_model / Brier_close. MDE is 1.429 x half-width, as defined in
`POWER_PAGE_2026-09-22.md`.

| Sport | Market | n (holdout) | Model Brier | Close Brier | Gap | 95% CI | DM p | BSS vs close | MDE | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| MLB | moneyline | 13,992 | 0.2429 | 0.2390 | +0.0039 | [+0.0028, +0.0051] | 3.6e-12 | -0.0165 | 0.0016 | **TRAILS_CLOSE** |
| Soccer | O/U 2.5 | 7,558 | 0.2465 | 0.2390 | +0.0076 | [+0.0059, +0.0092] | 1.1e-19 | -0.0317 | 0.0023 | **TRAILS_CLOSE** |
| NBA | moneyline | 372 | 0.1735 | 0.1672 | +0.0063 | [-0.0042, +0.0168] | 0.237 | -0.0377 | 0.0150 | **MATCHES_CLOSE** |

Verdict rule, applied mechanically: the verdict is MATCHES_CLOSE only if the CI includes 0.
Otherwise it is TRAILS_CLOSE when the CI lies above 0 and BEATS_CLOSE when it lies below.

### Sensitivity checks (none changes a verdict)

| Row | Shin-devigged close: n, gap, CI, verdict | Shin DM p / MDE | Date-clustered CI (clusters) |
|---|---|---|---|
| MLB ML | 13,983, +0.0040, [+0.0029, +0.0051], TRAILS_CLOSE | 3.4e-12 / 0.0016 | [+0.0028, +0.0051] (1,170 dates) |
| Soccer O/U | 7,555, +0.0076, [+0.0060, +0.0093], TRAILS_CLOSE | 7.2e-19 / 0.0024 | [+0.0059, +0.0092] (685 dates) |
| NBA ML | 372, +0.0069, [-0.0038, +0.0175], MATCHES_CLOSE | 0.20 / 0.0152 | [-0.0028, +0.0154] (74 dates) |

- **Devig method.** All three harnesses use proportional devig, p = imp_h / (imp_h + imp_a). The
  Shin column uses `eval_gate/shin.py`. Shin drops 9 MLB rows and 3 soccer rows whose booksum is
  below 1, because those rows have no valid Shin price. The primary rows keep every game so they
  match the published numbers.
- **Clustering.** The rows are pregame, one row per game, so game clustering reduces to the
  i.i.d. SE. The date-clustered CI allows for correlation between games on the same day. It
  moves the bounds by at most 0.0015.

## Reproduction check (done before trusting the rows)

| Harness | Printed on 2026-09-24 | Recompute |
|---|---|---|
| `python -m scripts.platformkit.proof_mlb.beat_the_close_ml` | n=27983, holdout=13992, close 0.239, Elo 0.2429 | 0.2429 / 0.2390, n=13,992 |
| `python -m scripts.platformkit.proof_soccer.beat_the_close_ou` | n=15115, holdout=7558, close 0.239, Platt-cal 0.2465 | 0.2465 / 0.2390, n=7,558 |
| `python -m scripts.platformkit.proof_nba.ml_accuracy` | n=743, holdout=372, close 0.1672, Elo 0.1735 | 0.1735 / 0.1672, n=372 |

The recompute calls the harnesses' own functions (`_walk_forward_elo`, `_build_model_forecast`,
`_fit_platt` / `_apply_platt`, `load_box`, `american_to_prob`). It also uses the same sort
order, the same inner joins, the same n // 2 split and the same 1e-6 clip. No model is
reimplemented.

## Commands

```
python -m scripts.platformkit.eval_gate.dm_recompute_pregame --json <out.json>
python -m pytest scripts/platformkit/eval_gate/test_dm_recompute_pregame.py -q   # 4 passed
```

## Inputs (local-only corpora, gitignored; sha256 read 2026-09-24)

| Row | File | sha256 |
|---|---|---|
| MLB | `data/domains/mlb/games.parquet` | `ddc69f4a3b0657a1d4011cb038443a5a3faa22552d7d81c4cb9b1af783700c31` |
| MLB | `data/domains/mlb/odds.parquet` | `391bb443bbe5367d10b22942e262ac5696d4435b8f5abec8e69b22ab1e7f1201` |
| Soccer | `data/domains/soccer/matches.parquet` | `63cd075df7bbedd1892f17140ea0e4b8cf6038e846460d5efecbb31cd3838838` |
| Soccer | `data/domains/soccer/match_stats.parquet` | `ae3f0257cf91ad8438386560ac47adcad7f6d6acb2f2406c81beccf1c0638f4e` |
| Soccer | `data/domains/soccer/odds.parquet` | `dbaf592c89ecb3c4b7298d6b71c66c4abcc5618dc7c763e2199ffa8341320655` |
| NBA | `data/domains/basketball_nba/espn_boxscores.parquet` | `9f52c38ae1c02f36cb549c61f12f8068665cc4e552ad51ba13e9a53702ad2949` |
| NBA | `data/domains/basketball_nba/odds.parquet` | `7949f0adf257636bc9baf0097e074ece1de73760cae9119483a9b979218fd15c` |

These are the harnesses' hard-coded defaults, used when `PROOF_CORPUS_ROOT` is unset. All seven
files were present on disk.

## Plain-English reading

- **MLB and soccer.** The published label "MATCH within sampling noise" does not survive an
  interval. With 14k and 7.5k held-out games, the SE is small enough to resolve gaps of about
  0.002 Brier. The measured gaps of 0.0039 and 0.0076 are 2.5x and 3.3x their MDEs, so the close
  is measurably sharper on both.
  - The harnesses called these rows MATCH because their verdicts use fixed gap thresholds (MATCH
    if gap <= 0.005 for MLB and <= 0.012 for soccer). Those thresholds are not intervals.
  - The gaps are still small: the model's Brier is 1.6 and 3.2 percent worse than the close's.
    This is consistent with the documented causes. The MLB Elo does not see the starting pitcher,
    and the soccer model is a pooled-Platt Poisson model scored against Pinnacle.
  - The honest label for both rows is TRAILS_CLOSE.
- **NBA.** The CI includes 0, so the row is MATCHES_CLOSE. The MDE is 0.0150, which is more than
  twice the point gap, so the row cannot tell a match from a real deficit of the size seen in
  MLB and soccer. Read it as underpowered, not as evidence of parity.

## Discrepancies found in existing public text (reported, not edited)

**Update, same day (2026-09-24, before publish):** the items below were fixed on the pages in the same
landing as this memo: MARKET_EFFICIENCY_PROOF.md rows and headline, PROOFS.md rows, EVIDENCE.md rows,
README.md, QUANT_BRIEF.md; JOB_EVIDENCE_PACKET.md and PUBLIC_EVIDENCE.md carry superseding notes beside
their n=743 / TRAILS_CLOSE entries (added, not deleted). The NBA row on EVIDENCE.md and QUANT_BRIEF.md
uses the Shin-devigged close (0.1666) with this table's Shin p and MDE.

1. `docs/MARKET_EFFICIENCY_PROOF.md` lines 39 and 41, `docs/PROOFS.md` lines 62 and 64, and
   MARKET_EFFICIENCY_PROOF line 44 all label MLB ML and soccer O/U as MATCH "within sampling
   noise". Under the interval rule both are TRAILS_CLOSE.
2. `EVIDENCE.md:37` reports the NBA row with n=743. That is the overlap count; 372 games are
   scored.
   - Its Brier values (0.1735 vs 0.1666, gap +0.0069) are the Shin-close version of this same
     holdout. They match the Shin sensitivity row above to four decimals.
   - Its CI [-0.0036, +0.0175] comes from `own_lines_backtest_nba.json` and differs slightly from
     the DM interval here, [-0.0038, +0.0175]. That is plausibly a different interval method; the
     JSON holds aggregates only, so this is not verified.
   - The same JSON and EVIDENCE.md label the row `TRAILS_CLOSE` while noting "CI includes 0".
     Under the written rule that is MATCHES_CLOSE.
3. `docs/MARKET_EFFICIENCY_PROOF.md` gives the NBA close Brier as 0.1672 (proportional devig),
   while EVIDENCE.md gives 0.1666 (Shin). Both are correct for their devig method, but neither
   page names the method it used.

## Task B (per-game NBA CSV): stopped on licensing

The NBA close in `data/domains/basketball_nba/odds.parquet` comes from ESPN's odds endpoint,
ingested by `domains/basketball_nba/ingest_espn_odds.py` (provider priority "ESPN BET", then
"DraftKings"). The outcomes come from ESPN box scores.

`docs/evidence/LICENCE_LEDGER.md` row 1 (ESPN / Disney) has the verdict **DECIDE**. The Disney
consumer licence it records grants no right to reproduce, distribute or make any Disney Product
available to the public, including for model benchmarking or validation. Publishing
per-game devigged close probabilities derived from that feed would make derived ESPN data
available to the public, so the CSV was **not written** to `docs/evidence/pregame/`, and
`score_vs_close.py` was not built.

Two further gaps would remain even with a licence decision:

- `odds.parquet` has no snapshot timestamp.
- The source is a per-date ESPN cache (`data/cache/spreads/YYYYMMDD.json`, 216 files), so it is
  not established that the price is the closing price rather than whatever ESPN served when the
  cache was written.

The rows can be rebuilt privately (743 rows: 371 fit, 372 holdout, 2025-10-21 to 2026-05-23, no
duplicate game keys, verified today):

```
python -m scripts.platformkit.eval_gate.dm_recompute_pregame --dump-nba <private path outside docs/>
```
