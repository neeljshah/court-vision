# Predictor Quickstart -- run a calibrated prediction in minutes

This is the 4-sport (NBA / MLB / Soccer / Tennis) CALIBRATED PREDICTION platform.
One win-prob per sport anchors a coherent pregame surface plus an in-game repricer.
The selling point is RIGOR (leak-free / walk-forward / OOS discipline, self-caught
retractions) and the IN-GAME conditioning edge -- never a fabricated $ edge.

What you get in this quickstart:
1. Slim install (predictor only, no CV / web / daemon stack).
2. One matchup, pregame + in-game, via the unified `predict_matchup` CLI -- with REAL output.
3. Reproduce the leak-free scoreboards on committed fixtures (proof in under 60s, fresh clone).
4. Where the real, canonical numbers live.

Honest framing up front: the pregame model MATCHES the devigged closing line within
sampling noise on team-strength markets, and is BEHIND on totals / ATP only by freshness
data (injuries, lineups, weather, park, starting pitcher) that a public/box model cannot
see. The decisive, measured + calibrated edge is IN-GAME conditioning (pregame intelligence
prior fused with the realized state), which WINS on all 4 sports. No $ edge is claimed
anywhere.

---

## 1. Slim install

The predictor needs only a small scientific-Python surface. The heavy computer-vision,
web, and daemon dependencies in `requirements.txt` are NOT required.

Option A -- requirements file:

```
pip install -r requirements-predictor.txt
```

(Contents: numpy, pandas, pyarrow, scipy, scikit-learn.)

Option B -- editable install (also gives you console scripts):

```
pip install -e .
```

This exposes three commands:

```
cv-matchup   # = python -m scripts.platformkit.predict_matchup  (pregame + in-game)
cv-predict   # = the cohesive pregame read
cv-live      # = the in-game live read
```

---

## 2. One matchup -- pregame + in-game

The unified CLI takes a sport, the two teams, and the realized game state (elapsed +
score; pass zeros for a pure pregame read). It returns both the pregame surface and the
in-game repriced win-prob in one JSON object.

```
python -m scripts.platformkit.predict_matchup \
  --sport nba --home BOS --away LAL \
  --elapsed 0 --home-score 0 --away-score 0
```

REAL output:

```json
{
  "sport": "nba",
  "home": "BOS",
  "away": "LAL",
  "edge_claimed": false,
  "framing": "Pregame MATCHES the devigged close (calibration/sharpness, not an edge); in-game ADDS the realized state. No $ edge.",
  "pregame": {
    "p_home_win": 0.605,
    "total_mean": 211.3,
    "margin_home": 3.0,
    "honest_note": "Best calibrated NBA prediction. Moneyline matches the devigged close within noise; totals trail by the market's injury/lineup freshness edge a box model cannot see. No $ edge claimed."
  },
  "ingame": {
    "p_home_win": 0.5732,
    "pregame_p_home": 0.605,
    "proj_total": 211.3,
    "proj_margin_home": 4.4,
    "honest_note": "In-game = pregame Elo win-prob (the SAME prior predict() reports, anchored into the repricer) + realized score, then the W156 temperature recalibrator (ECE 0.059->0.012). A live book also sees the score. Forecaster quality, no $ edge."
  }
}
```

The `pregame` block is the cohesive read (one win-prob anchors a consistent moneyline /
total / margin surface). The `ingame` block is the live repricer: it fuses the SAME
pregame Elo prior with the realized score and applies a temperature recalibrator. With
`--elapsed`/`--home-score`/`--away-score` set to a mid-game state, the in-game win-prob
moves off the pregame prior as the realized state warrants.

Swap `--sport` for `mlb`, `soccer`, or `tennis` and pass the corresponding teams to run
the other domains.

---

## 3. Reproduce the leak-free scoreboards on committed fixtures

Two proof scoreboards ship with committed fixtures so a fresh clone can reproduce the
machinery in well under 60s, no private data needed. The fixtures are a small demo slice
(so the printed numbers are NOT the canonical headline numbers -- those come from the full
local corpora, see section 4); the point here is that the leak-free / walk-forward
machinery runs end-to-end and produces an honest verdict table.

### 3a. Beat-the-Close (pregame quality vs the devigged closing line)

```
python -m scripts.platformkit.beat_the_close_scoreboard --corpus tests/fixtures/proof
```

REAL output (fixture/demo slice; runs in ~2s):

```
| Sport | Market | Metric | n | Our model | Close | Gap | Verdict | Why |
|---|---|---|---|---|---|---|---|---|
| NBA | moneyline | Brier | 112 | 0.2417 | 0.2307 | +0.011 | MATCH | MOV-aware Elo; within sampling noise of the close |
| NBA | total (O/U) | RMSE | 112 | 15.503 | 12.935 | +2.568 | BEHIND (freshness) | possessions/efficiency model; gap = injuries/lineups |
| MLB | moneyline | Brier | 210 | 0.2524 | 0.2517 | +0.0007 | MATCH | walk-forward MOV-Elo; tiny deficit = pitcher-blindness (the close prices SP) |
| MLB | total (O/U) | RMSE | 210 | 3.205 | 3.125 | +0.0804 | MATCH | run-rate expected total vs closing line; gap = park/weather/SP/lineup |
| Soccer | O/U-2.5 | Brier | 252 | 0.2381 | 0.2119 | +0.0261 | BEHIND (freshness) | EW-Poisson+finishing+pooled-Platt vs devigged Pinnacle close |
| Tennis (ATP) | match-win | Brier | 270 | 0.1671 | 0.1507 | +0.0164 | BEHIND (freshness) | surface-Elo+Platt vs devigged Pinnacle; ATP closes very efficient |
```

Reading it: on team-strength win markets (NBA and MLB moneyline) the model MATCHES the
devigged close within sampling noise; on totals / derived / ATP markets it trails by the
freshness edge the market sees and a box model cannot. Closing those gaps needs the data
the market has (a forward freshness feed) or in-game conditioning, not a cleverer pregame
model.

### 3b. In-Game scoreboard (conditional-on-state vs static pregame)

```
python -m scripts.platformkit.ingame_scoreboard --corpus tests/fixtures/proof
```

REAL output (fixture/demo slice; runs in ~5s):

```
| Sport | Checkpoint | n | Metric | Conditional | Static | Delta | Verdict | Why |
|---|---|---|---|---|---|---|---|---|
| NBA | end Q1/Q2/Q3 | 660 | Brier | 0.301 | 0.244 | +0.0567 | no-improvement | combined prior+state; sharpest forecaster fuses rating prior + score |
| MLB | after inning 3/5/7 | 618 | Brier | 0.128 | 0.256 | -0.1279 | WIN | combined pregame MOV-Elo prior + realized runs |
| Soccer | half-time | 252 | Brier (1X2) | 0.453 | 0.675 | -0.2221 | WIN | HT-conditional; O/U-2.5 also sharpens |
| Tennis | after set 1 | 270 | Brier | 0.102 | 0.164 | -0.0624 | WIN | combined pregame Elo prior + realized set lead, leak-free |
```

Reading it: where a leak-free per-period corpus exists, the conditional-on-state
forecaster is decisively sharper than the static pregame line. The strongest forecaster
fuses the pregame intelligence (ratings) AS THE PRIOR with the realized state, not either
alone. This is forecaster quality, not a $ edge -- a live book sees the same state.

(Both commands print "fixture/demo mode -- canonical report NOT written" because `--corpus`
points at the demo fixtures. Run with no `--corpus` against the full local corpora to
refresh the canonical reports.)

---

## 4. Where the real numbers live

The fixtures above prove the machinery on a public, committed slice. The canonical,
headline numbers are computed on the full per-sport corpora, which are local and
gitignored (real prices and outcomes). The canonical numbers live in:

- `vault/_Edge_Maps/_Beat_The_Close.md` -- pregame quality vs the devigged close,
  all 4 sports / 6 markets (NBA moneyline + total, MLB moneyline + total, Soccer O/U-2.5,
  Tennis ATP match-win).
- `vault/_Edge_Maps/_Ingame_Scoreboard.md` -- in-game conditional-vs-static quality,
  all 4 sports (NBA, MLB, Soccer 1X2 + O/U-2.5, Tennis), all 4 WIN.
- `docs/JOB_EVIDENCE_PACKET.md` -- the SINGLE honesty truth-source. Every prediction
  number is cited there, adversarially audited, with self-caught retractions documented.
  Cite this for any number; do not restate retracted figures.

For the honest limits and the explicit retraction context, see `docs/KNOWN_LIMITATIONS.md`.

The headline thesis, in one line: the pregame predictor MATCHES the devigged close on
team-strength markets and is BEHIND on totals / ATP only by freshness data we cannot see;
IN-GAME conditioning (pregame intelligence prior + realized state) is the decisive,
measured, calibrated, and delivered edge across all 4 sports -- and no $ edge is ever
claimed.
