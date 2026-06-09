"""
build_winprob.py
================
Build a LEAK-FREE pregame win-probability model from team strength
(as-of SRS) + home-court + rest, and report its CALIBRATION as scouting
intelligence.

    data/cache/intel_outcome/team_winprob_calibration.json

This is a transparent, sanity-anchor outcome model ("model says OKC 78% to
win tonight"). It is NOT a betting edge: betting these probabilities against
closing spreads was REJECTED (-9% ATS, see OUTCOME_VALIDATION_team_lines).
The value is a *calibrated* outcome probability, nothing more.

Model
-----
For each regular-season game G played on date D between home team H and
away team A:

    model_margin = (rating_H_asof - rating_A_asof)   # leak-free SRS, prior games only
                 + home_court                        # +1.73 pts (league avg home margin)
                 + rest_adjustment                   # signed B2B fatigue delta (home POV)

    win_prob_home = logistic(k * model_margin)       # k = 0.115275

Constants
---------
home_court          = league.home_court_margin_pts   (team_strength.json) = +1.73
k (logistic slope)  = league.logistic_k              (team_strength.json) = 0.115275
b2b_margin_delta    = league.b2b.margin_delta        (team_schedule_spots) = -1.1723
                      (margin penalty, from the fatigued team's POV)

rest_adjustment per game (home perspective):
    + |b2b_delta|  if AWAY team is on a back-to-back  (away fatigued -> helps home)
    - |b2b_delta|  if HOME team is on a back-to-back  (home fatigued -> hurts home)
    0              if both / neither on a B2B
This is the only rest signal carried per-game in the artifacts; it is grounded
in the schedule_spots league B2B bucket, not re-estimated here.

Leak-safety
-----------
rating_H_asof / rating_A_asof come from team_strength.json's `as_of` series,
where `rating_to_date` for game G uses ONLY games strictly before G's date
(see build_team_strength.compute_as_of_series). No outcome from G or any later
game contaminates the inputs. The grade gate `n_games_prior >= 50` additionally
drops the early-season window where the SRS is still noisy.

Outputs (team_winprob_calibration.json)
---------------------------------------
- meta / constants / leak-safety statement / scouting-only caveat
- headline metrics: Brier, log-loss, accuracy on the gated game set
- baselines: predict-home-always, predict-0.5, and the model
- reliability table: predicted-prob buckets vs realized home-win rate
- loose reference to the in-game live_win_prob model Brier
"""

import json
import math
import pathlib
from datetime import datetime, timezone

ROOT = pathlib.Path("C:/Users/neelj/nba-ai-system")
INTEL_DIR = ROOT / "data/cache/intel_outcome"
OUT_PATH = INTEL_DIR / "team_winprob_calibration.json"

TEAM_STRENGTH = INTEL_DIR / "team_strength.json"
SCHEDULE_SPOTS = INTEL_DIR / "team_schedule_spots.json"
SEASON_GAMES = ROOT / "data/nba/season_games_2025-26.json"
LIVE_WP_METRICS = ROOT / "data/models/live_win_prob_metrics.json"

MIN_PRIOR_GAMES = 50  # gate: drop early-season SRS noise


def logistic(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def load_json(p: pathlib.Path):
    return json.loads(p.read_text(encoding="utf-8"))


def build_asof_lookup(team_strength: dict) -> dict:
    """{(tri, game_id): {"rating": float, "n_prior": int}}"""
    lookup = {}
    for tri, t in team_strength["teams"].items():
        for e in t.get("as_of", []):
            lookup[(tri, e["game_id"])] = {
                "rating": float(e["rating_to_date"]),
                "n_prior": int(e["n_games_prior"]),
            }
    return lookup


def main():
    ts = load_json(TEAM_STRENGTH)
    spots = load_json(SCHEDULE_SPOTS)
    sg = load_json(SEASON_GAMES)
    rows = sg["rows"]

    home_court = float(ts["league"]["home_court_margin_pts"])      # +1.73
    k = float(ts["league"]["logistic_k"])                          # 0.115275
    b2b_delta = float(spots["league"]["b2b"]["margin_delta"])      # -1.1723 (fatigued POV)
    rest_penalty = abs(b2b_delta)                                  # magnitude of B2B fatigue

    asof = build_asof_lookup(ts)

    # ── Build the gradeable game set ───────────────────────────────────────────
    graded = []          # full gated set (n_prior >= MIN_PRIOR_GAMES, both teams)
    ungated = []         # all valid regular-season games (for context)
    n_total = 0
    n_missing_asof = 0
    n_missing_outcome = 0
    n_nonregular = 0

    for r in rows:
        gid = r["game_id"]
        # Regular season only (prefix 0022...). Playoffs (0042...) excluded:
        # the as_of SRS series is regular-season only and is regime-specific.
        if not gid.startswith("0022"):
            n_nonregular += 1
            continue
        n_total += 1

        home = r.get("home_team")
        away = r.get("away_team")
        outcome = r.get("home_win")
        if outcome is None or home is None or away is None:
            n_missing_outcome += 1
            continue
        outcome = int(outcome)

        h = asof.get((home, gid))
        a = asof.get((away, gid))
        if h is None or a is None:
            n_missing_asof += 1
            continue

        # Rest adjustment (home POV), grounded in schedule_spots B2B bucket.
        home_b2b = float(r.get("home_back_to_back") or 0.0)
        away_b2b = float(r.get("away_back_to_back") or 0.0)
        rest_adj = 0.0
        if home_b2b >= 1.0:
            rest_adj -= rest_penalty   # home fatigued -> penalise home
        if away_b2b >= 1.0:
            rest_adj += rest_penalty   # away fatigued -> help home

        model_margin = (h["rating"] - a["rating"]) + home_court + rest_adj
        p_home = logistic(k * model_margin)

        n_prior = min(h["n_prior"], a["n_prior"])
        rec = {
            "game_id": gid,
            "date": r["game_date"],
            "home": home,
            "away": away,
            "home_rating_asof": round(h["rating"], 4),
            "away_rating_asof": round(a["rating"], 4),
            "rest_adj": round(rest_adj, 4),
            "model_margin": round(model_margin, 4),
            "p_home": round(p_home, 6),
            "home_win": outcome,
            "n_prior": n_prior,
        }
        ungated.append(rec)
        if n_prior >= MIN_PRIOR_GAMES:
            graded.append(rec)

    # ── Metric helpers ─────────────────────────────────────────────────────────
    def brier(recs, prob_fn):
        return sum((prob_fn(r) - r["home_win"]) ** 2 for r in recs) / len(recs)

    def logloss(recs, prob_fn):
        eps = 1e-15
        s = 0.0
        for r in recs:
            p = min(max(prob_fn(r), eps), 1 - eps)
            y = r["home_win"]
            s += -(y * math.log(p) + (1 - y) * math.log(1 - p))
        return s / len(recs)

    def accuracy(recs, prob_fn, thresh=0.5):
        correct = 0
        for r in recs:
            pred = 1 if prob_fn(r) >= thresh else 0
            correct += int(pred == r["home_win"])
        return correct / len(recs)

    model_p = lambda r: r["p_home"]
    home_always_p = lambda r: 1.0          # always predict home wins
    coin_p = lambda r: 0.5

    n_graded = len(graded)
    home_win_rate = sum(r["home_win"] for r in graded) / n_graded

    metrics = {
        "model": {
            "brier": round(brier(graded, model_p), 6),
            "log_loss": round(logloss(graded, model_p), 6),
            "accuracy": round(accuracy(graded, model_p), 6),
        },
        "baseline_home_always": {
            # Brier/log-loss of the degenerate p=1.0 predictor are not
            # well-defined (log-loss is infinite on any home loss), so we
            # report only its classification accuracy = season home-win rate.
            "accuracy": round(accuracy(graded, home_always_p), 6),
            "note": "predict home wins every game; accuracy == realized home-win rate",
        },
        "baseline_coin_0.5": {
            "brier": round(brier(graded, coin_p), 6),
            "log_loss": round(logloss(graded, coin_p), 6),
            "accuracy_note": "0.5 is a tie at the 0.5 threshold; accuracy undefined/arbitrary",
        },
    }

    # Improvement vs baselines.
    model_brier = metrics["model"]["brier"]
    coin_brier = metrics["baseline_coin_0.5"]["brier"]
    metrics["model"]["brier_skill_vs_coin"] = round(1.0 - model_brier / coin_brier, 6)
    metrics["model"]["accuracy_lift_vs_home_always"] = round(
        metrics["model"]["accuracy"] - metrics["baseline_home_always"]["accuracy"], 6
    )

    # ── Reliability / calibration table ────────────────────────────────────────
    # Buckets on predicted home-win prob; report realized home-win rate per bucket.
    edges = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0001]
    reliability = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        bucket = [r for r in graded if lo <= r["p_home"] < hi]
        if not bucket:
            continue
        n = len(bucket)
        mean_pred = sum(r["p_home"] for r in bucket) / n
        realized = sum(r["home_win"] for r in bucket) / n
        reliability.append({
            "bucket": f"[{lo:.1f}, {min(hi,1.0):.1f})",
            "n": n,
            "mean_predicted": round(mean_pred, 4),
            "realized_home_win": round(realized, 4),
            "gap": round(realized - mean_pred, 4),
        })

    # Expected Calibration Error (n-weighted mean |realized - predicted|).
    ece = sum(b["n"] * abs(b["gap"]) for b in reliability) / n_graded

    # ── In-game model loose reference ──────────────────────────────────────────
    live_ref = None
    if LIVE_WP_METRICS.exists():
        try:
            lm = load_json(LIVE_WP_METRICS)
            live_ref = {
                "val_brier": lm.get("val_brier"),
                "n_games": lm.get("n_games"),
                "note": "IN-GAME model (uses live game state); only a loose, "
                        "non-comparable reference — a pregame model cannot match it.",
            }
        except Exception:
            live_ref = None

    # ── Sample scouting cards (most lopsided gated games, for the note) ─────────
    sample = sorted(graded, key=lambda r: abs(r["p_home"] - 0.5), reverse=True)[:10]
    sample_cards = [
        {
            "date": r["date"], "matchup": f"{r['away']} @ {r['home']}",
            "p_home": r["p_home"], "model_margin": r["model_margin"],
            "home_win": r["home_win"],
        }
        for r in sample
    ]

    out = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "season": "2025-26",
            "builder": "scripts/intel/outcome/build_winprob.py",
            "purpose": "Leak-free pregame win-probability for SCOUTING / sanity "
                       "anchor. NOT a betting edge.",
            "sources": [
                str(TEAM_STRENGTH.relative_to(ROOT)).replace("\\", "/"),
                str(SCHEDULE_SPOTS.relative_to(ROOT)).replace("\\", "/"),
                str(SEASON_GAMES.relative_to(ROOT)).replace("\\", "/"),
            ],
        },
        "scouting_only_caveat": (
            "This is a transparent pregame outcome probability for scouting and "
            "sanity ('model says OKC ~78% to win tonight'). It is NOT a betting "
            "edge. Betting these probabilities against closing spreads was "
            "REJECTED at -9% ATS (see OUTCOME_VALIDATION_team_lines). The market "
            "already prices team strength, home court and rest. Use this only as "
            "a calibrated outcome read, never as a wager signal."
        ),
        "model": {
            "formula": "win_prob_home = logistic(k * model_margin); "
                       "model_margin = (rating_home_asof - rating_away_asof) "
                       "+ home_court + rest_adjustment",
            "constants": {
                "home_court_pts": home_court,
                "logistic_k": k,
                "b2b_margin_delta_pts": b2b_delta,
                "rest_penalty_magnitude_pts": round(rest_penalty, 4),
                "min_prior_games_gate": MIN_PRIOR_GAMES,
            },
            "rest_rule": (
                "home POV: -|b2b_delta| if home on B2B, +|b2b_delta| if away on "
                "B2B, 0 otherwise. Grounded in team_schedule_spots league B2B "
                "bucket; not re-estimated."
            ),
        },
        "leak_safety": (
            "rating_*_asof come from team_strength.json `as_of` series, where "
            "rating_to_date for a game uses ONLY games strictly before that "
            "game's date (build_team_strength.compute_as_of_series). No outcome "
            "from the graded game or any later game enters the inputs. The "
            "n_prior >= 50 gate additionally drops the noisy early-season SRS "
            "window. Rest flags are derived from prior completed game dates only "
            "(team_schedule_spots, leak_safe=true)."
        ),
        "coverage": {
            "regular_season_rows_seen": n_total,
            "playoff_or_nonregular_skipped": n_nonregular,
            "skipped_missing_outcome": n_missing_outcome,
            "skipped_missing_asof_rating": n_missing_asof,
            "graded_ungated": len(ungated),
            "graded_gated_n_prior_ge_50": n_graded,
            "gated_home_win_rate": round(home_win_rate, 4),
        },
        "metrics": metrics,
        "calibration": {
            "expected_calibration_error": round(ece, 6),
            "reliability_table": reliability,
        },
        "ingame_model_loose_reference": live_ref,
        "sample_scouting_cards_top10_lopsided": sample_cards,
    }

    OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── Console summary ────────────────────────────────────────────────────────
    print(f"Saved -> {OUT_PATH}")
    print(f"\nGated games (n_prior>=50): {n_graded}  "
          f"(ungated valid: {len(ungated)}, regular rows: {n_total})")
    print(f"Home win rate (gated): {home_win_rate:.4f}")
    print(f"\nMODEL:    Brier={metrics['model']['brier']:.4f}  "
          f"LogLoss={metrics['model']['log_loss']:.4f}  "
          f"Acc={metrics['model']['accuracy']:.4f}")
    print(f"COIN 0.5: Brier={coin_brier:.4f}  "
          f"LogLoss={metrics['baseline_coin_0.5']['log_loss']:.4f}")
    print(f"HOME-ALWAYS: Acc={metrics['baseline_home_always']['accuracy']:.4f}")
    print(f"Brier skill vs coin: {metrics['model']['brier_skill_vs_coin']:+.4f}")
    print(f"Acc lift vs home-always: {metrics['model']['accuracy_lift_vs_home_always']:+.4f}")
    print(f"ECE: {ece:.4f}")
    print("\nReliability table:")
    print(f"  {'bucket':<14}{'n':>5}  {'pred':>6}  {'realized':>9}  {'gap':>7}")
    for b in reliability:
        print(f"  {b['bucket']:<14}{b['n']:>5}  {b['mean_predicted']:>6.3f}  "
              f"{b['realized_home_win']:>9.3f}  {b['gap']:>+7.3f}")
    if live_ref:
        print(f"\nIn-game model (loose ref): Brier={live_ref['val_brier']}, "
              f"n={live_ref['n_games']}")


if __name__ == "__main__":
    main()
