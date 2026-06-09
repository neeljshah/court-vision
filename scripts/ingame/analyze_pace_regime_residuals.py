"""STEP 1 error-analysis: ensemble residuals sliced by LIVE-vs-EXPECTED pace regime.

QUESTION
--------
Remaining POSSESSIONS drive every counting stat. The routed/score ensemble
projects a team TOTAL (ridge point) and per-player counting-stat finals by
(implicitly) extrapolating the game forward. When the LIVE tempo diverges from
the two teams' structural pace identity, does the ensemble systematically
over/under-project the remaining total (and hence player counting stats)?

This is a READ-ONLY diagnostic. It rebuilds the SAME leak-free walk-forward
records as ``scripts/ingame/eval_routed_ensemble.py`` (identical record builder,
folds, grid -- the EXTENDED grid incl early-Q1 + late-Q4), then for every grid
state computes:

  * live_pace_ppm   = game_row["pace_poss_per_min"]  (possessions-so-far / min
                      so far; FGA + 0.44*FTA + TOV - OREB is the possession est.
                      already computed leak-free by the featurizer)
  * exp_pace_ppm    = pregame structural pace = mean(home_pace_pg, away_pace_pg)
                      / 48, from atlas_team_pace_identity.parquet (LEAK-FREE: a
                      season-prior identity, not derived from this game's future)
  * regime          = live_pace_ppm / exp_pace_ppm   (>1 hot, <1 slow)

It slices, by regime bucket x grid bucket:
  * TEAM TOTAL residual of the ensemble (ridge point): proj_total - actual_total
    (signed -> bias; |.| -> MAE). Also production (pace-extrapolation) total.
  * Per-player counting-stat residual of the routed blend AND production snapshot
    (signed mean -> bias). Counting stats = pts, reb, ast, fg3m, stl, blk, tov.

If, when the game runs HOT (regime>1), the ensemble UNDER-projects the total
(signed residual < 0) and player counting stats, and the reverse when COLD, that
is the systematic pace-regime error the enricher should correct. If instead the
residual is FLAT across regime (the ensemble already prices live pace) OR the
sign says live pace MEAN-REVERTS (hot games regress so extrapolating hot would
LOSE), we report that honestly -- it warns the build step off a naive
extrapolate-live-pace rule.

Leak-safety: live_pace from events<=t only (featurizer guarantee); exp_pace is a
pregame season identity. No future possessions touched.

Run (subsample; matches the eval harness universe):
    set NBA_OFFLINE=1
    python scripts/ingame/analyze_pace_regime_residuals.py --max-games 300 \
        --folds 3 --n-sims 800
Outputs:
    .planning/ingame/pace_regime_residuals.json
    .planning/ingame/pace_regime_residuals.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault("NBA_OFFLINE", "1")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

import numpy as np  # noqa: E402

import scripts.ingame.eval_second_by_second as ESBS  # noqa: E402
from scripts.ingame.eval_second_by_second import (  # noqa: E402
    GamelogStore, load_season_games, build_game_record,
    baseline_player_snapshot, baseline_team_projection,
    _parse_iso_date, TEAM_FEATS, _ridge_fit, _ridge_pred, PLAYER_STATS,
)
from src.ingame.state_featurizer import discover_game_ids  # noqa: E402
from src.ingame import routed_ensemble as RE  # noqa: E402
import scripts.ingame.eval_routed_ensemble as ERE  # noqa: E402
from src.ingame.snapshot_pace_intel_enricher import load_team_pace_priors  # noqa: E402

PLAN_DIR = os.path.join(ROOT, ".planning", "ingame")
os.makedirs(PLAN_DIR, exist_ok=True)

REG_PERIOD_LEN = 720
COUNTING = PLAYER_STATS  # pts reb ast fg3m stl blk tov -- all counting stats

# Pace-regime buckets on (live_pace / expected_pace). Centered on 1.0.
REGIME_EDGES = [0.0, 0.85, 0.93, 0.98, 1.02, 1.07, 1.15, 99.0]
REGIME_LABELS = ["<0.85(vcold)", "0.85-0.93(cold)", "0.93-0.98(cool)",
                 "0.98-1.02(onpace)", "1.02-1.07(warm)", "1.07-1.15(hot)",
                 ">1.15(vhot)"]


def regime_bucket(ratio: float) -> str:
    for i in range(len(REGIME_EDGES) - 1):
        if REGIME_EDGES[i] <= ratio < REGIME_EDGES[i + 1]:
            return REGIME_LABELS[i]
    return REGIME_LABELS[-1]


def expected_game_pace_ppm(home: str, away: str,
                           priors: Dict[str, float]) -> Optional[float]:
    """Pregame expected combined pace in possessions-per-minute.

    pace_pg is per-team possessions-per-GAME (~48 min). The combined game pace
    (total possessions both teams) ~ home_pace_pg + away_pace_pg over the game;
    per minute that is (home+away)/48. We instead use the symmetric mean of the
    two identities * (96/48) to mirror the featurizer's "total possessions both
    teams / minutes" definition: exp_total_poss_per_min = (hp+ap)/48.
    """
    hp = priors.get(home)
    ap = priors.get(away)
    if hp is None or ap is None:
        return None
    return (float(hp) + float(ap)) / 48.0


def _fit_team_ridge(train_recs):
    return ERE._fit_team_ridge(train_recs)


def run(max_games: int, folds: int, min_train: int) -> Dict[str, Any]:
    priors = load_team_pace_priors()
    print(f"[pace-resid] loaded {len(priors)} team pace priors "
          f"(pace_pg mean={np.mean(list(priors.values())):.2f})")

    season_games = load_season_games()
    store = GamelogStore()
    all_ids = [g for g in discover_game_ids() if g in season_games]
    all_ids = [g for g in all_ids
               if _parse_iso_date(season_games[g].get("game_date") or "")]
    all_ids.sort(key=lambda g: season_games[g]["game_date"])
    n_total = len(all_ids)
    if max_games and n_total > max_games:
        idx = np.linspace(0, n_total - 1, max_games).astype(int)
        sampled = [all_ids[i] for i in sorted(set(idx.tolist()))]
    else:
        sampled = all_ids
    print(f"[pace-resid] {n_total} dated games; using {len(sampled)}")

    old_sec, old_labels = ERE._patch_grid()
    records: List[Dict[str, Any]] = []
    try:
        for i, gid in enumerate(sampled):
            try:
                rec = build_game_record(gid, season_games[gid], store)
            except Exception:
                rec = None
            if rec is not None:
                records.append(rec)
            if (i + 1) % 50 == 0:
                print(f"  ...{i+1}/{len(sampled)} ({len(records)} usable)")
    finally:
        ESBS.GRID_SEC, ESBS.GRID_LABELS = old_sec, old_labels
    records.sort(key=lambda r: r["game_date"])
    print(f"[pace-resid] {len(records)} usable records")
    if len(records) < min_train + 10:
        raise SystemExit(f"too few usable games ({len(records)})")

    dates = [r["game_date"] for r in records]
    uniq = sorted(set(dates))
    chunks = np.array_split(np.array(uniq, dtype=object), folds + 1)
    fold_test_dates = [set(chunks[k].tolist()) for k in range(1, folds + 1)]

    # accumulators keyed by (regime_bucket) and (regime_bucket, grid_label)
    # team total: signed residual & abs residual for ensemble(ridge) + production
    team_acc = defaultdict(lambda: defaultdict(list))   # team_acc[regime][metric]
    team_by_grid = defaultdict(lambda: defaultdict(list))  # [(regime,grid)][metric]
    # player counting: signed residual by (regime, stat) for routed + production
    pl_acc = defaultdict(lambda: defaultdict(list))     # pl_acc[regime][f"{m}_{stat}"]
    # correlation pool: (regime_ratio, ens_total_signed_resid, prod_total_signed)
    corr_pool: List[Tuple[float, float, float, float]] = []
    n_states = 0
    n_priced = 0

    for fold_i, test_dates in enumerate(fold_test_dates):
        train_recs = [r for r in records if r["game_date"] < min(test_dates)]
        test_recs = [r for r in records if r["game_date"] in test_dates]
        if len(train_recs) < min_train or not test_recs:
            continue
        ridge_w = _fit_team_ridge(train_recs)
        print(f"[fold {fold_i}] train={len(train_recs)} test={len(test_recs)}")

        for r in test_recs:
            home_final = r["home_final"]
            away_final = r["away_final"]
            actual_total = home_final + away_final
            for t, gd in r["grids"].items():
                grow = gd["game"]
                glabel = ERE.EXTENDED_GRID_LABELS.get(t)
                if glabel is None:
                    continue
                home = grow.get("home_team")
                away = grow.get("away_team")
                exp_ppm = expected_game_pace_ppm(home, away, priors)
                live_ppm = float(grow.get("pace_poss_per_min", 0.0) or 0.0)
                if exp_ppm is None or exp_ppm <= 0 or live_ppm <= 0:
                    continue
                ratio = live_ppm / exp_ppm
                rb = regime_bucket(ratio)
                n_states += 1

                # --- TEAM TOTAL: ensemble(ridge point) + production ---
                ph, pa = baseline_team_projection(grow)
                prod_total = ph + pa
                rw = ridge_w.get(t)
                if rw is not None:
                    feats = np.array([[float(grow.get(k, 0) or 0)
                                       for k in TEAM_FEATS]])
                    rh = float(_ridge_pred(rw["home"], feats)[0])
                    ra = float(_ridge_pred(rw["away"], feats)[0])
                    n_priced += 1
                else:
                    rh, ra = ph, pa
                ens_total = rh + ra
                ens_sr = ens_total - actual_total      # signed (neg = UNDER)
                prod_sr = prod_total - actual_total
                team_acc[rb]["ens_signed"].append(ens_sr)
                team_acc[rb]["ens_abs"].append(abs(ens_sr))
                team_acc[rb]["prod_signed"].append(prod_sr)
                team_acc[rb]["prod_abs"].append(abs(prod_sr))
                team_acc[rb]["ratio"].append(ratio)
                team_acc[rb]["played_share"].append(
                    float(grow.get("played_share", 0) or 0))
                team_by_grid[(rb, glabel)]["ens_signed"].append(ens_sr)
                team_by_grid[(rb, glabel)]["ens_abs"].append(abs(ens_sr))
                corr_pool.append((ratio, ens_sr, prod_sr,
                                  float(grow.get("played_share", 0) or 0)))

                # --- PLAYER counting stats: routed blend + production snapshot ---
                for (_team, _ln), prow in gd["players"].items():
                    pid = prow.get("player_id")
                    if pid is None or pid not in r["player_finals"]:
                        continue
                    lab = r["player_finals"][pid]
                    if lab.get("min", 0) <= 0:
                        continue
                    pf = float(prow.get("pf", 0) or 0)
                    snap = baseline_player_snapshot(prow, grow, pf)
                    for s in COUNTING:
                        truth = lab[s]
                        snap_v = float(snap[s])
                        pl_acc[rb][f"prod_{s}_signed"].append(snap_v - truth)
                        pl_acc[rb][f"prod_{s}_abs"].append(abs(snap_v - truth))

    return _summarize(team_acc, team_by_grid, pl_acc, corr_pool,
                      len(records), n_total, n_states, n_priced)


def _stats(xs):
    if not xs:
        return {"n": 0, "mean": None, "abs_mean": None}
    a = np.array(xs, dtype=float)
    return {"n": int(a.size), "mean": float(a.mean()),
            "median": float(np.median(a))}


def _summarize(team_acc, team_by_grid, pl_acc, corr_pool, n_records, n_total,
               n_states, n_priced) -> Dict[str, Any]:
    team_table = {}
    for rb in REGIME_LABELS:
        d = team_acc.get(rb)
        if not d:
            continue
        team_table[rb] = {
            "n": len(d["ens_signed"]),
            "ratio_mean": float(np.mean(d["ratio"])) if d["ratio"] else None,
            "played_share_mean": (float(np.mean(d["played_share"]))
                                  if d["played_share"] else None),
            "ens_total_bias": float(np.mean(d["ens_signed"])),
            "ens_total_mae": float(np.mean(d["ens_abs"])),
            "prod_total_bias": float(np.mean(d["prod_signed"])),
            "prod_total_mae": float(np.mean(d["prod_abs"])),
        }

    # player counting-stat bias per regime (signed mean residual; neg=UNDER)
    player_table = {}
    for rb in REGIME_LABELS:
        d = pl_acc.get(rb)
        if not d:
            continue
        row = {"n_states_pts": len(d.get("prod_pts_signed", []))}
        for s in COUNTING:
            sg = d.get(f"prod_{s}_signed", [])
            ab = d.get(f"prod_{s}_abs", [])
            row[s] = {
                "n": len(sg),
                "bias": float(np.mean(sg)) if sg else None,
                "mae": float(np.mean(ab)) if ab else None,
            }
        player_table[rb] = row

    # team total by (regime, grid)
    team_grid_table = {}
    for (rb, gl), d in team_by_grid.items():
        team_grid_table.setdefault(rb, {})[gl] = {
            "n": len(d["ens_signed"]),
            "ens_bias": float(np.mean(d["ens_signed"])),
            "ens_mae": float(np.mean(d["ens_abs"])),
        }

    # correlation: does regime ratio predict signed total residual?
    corr = {}
    if len(corr_pool) > 30:
        arr = np.array(corr_pool, dtype=float)
        rat, ens_sr, prod_sr, pshare = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]
        corr["pearson_ratio_vs_ens_signed_total"] = float(
            np.corrcoef(rat, ens_sr)[0, 1])
        corr["pearson_ratio_vs_prod_signed_total"] = float(
            np.corrcoef(rat, prod_sr)[0, 1])
        # split early (<0.5 played) vs late
        early = pshare < 0.5
        if early.sum() > 30 and (~early).sum() > 30:
            corr["pearson_early_ratio_vs_ens"] = float(
                np.corrcoef(rat[early], ens_sr[early])[0, 1])
            corr["pearson_late_ratio_vs_ens"] = float(
                np.corrcoef(rat[~early], ens_sr[~early])[0, 1])
        # OLS slope ens_signed ~ (ratio-1): the naive correction coefficient.
        x = rat - 1.0
        A = np.vstack([np.ones_like(x), x]).T
        beta, *_ = np.linalg.lstsq(A, ens_sr, rcond=None)
        corr["ols_ens_signed_intercept"] = float(beta[0])
        corr["ols_ens_signed_slope_per_unit_ratio"] = float(beta[1])

    return {
        "meta": {
            "n_total_dated_games": n_total,
            "n_usable_records": n_records,
            "n_grid_states": n_states,
            "n_ridge_priced": n_priced,
            "regime_def": "live pace_poss_per_min / pregame expected (mean team "
                          "pace_pg / 48); >1 = running HOT vs structural identity",
            "regime_labels": REGIME_LABELS,
            "leak_safety": "live pace from events<=t (featurizer); exp pace is "
                           "season identity prior; signed residual = proj - actual",
        },
        "team_total_by_regime": team_table,
        "team_total_by_regime_grid": team_grid_table,
        "player_counting_bias_by_regime": player_table,
        "regime_correlation": corr,
    }


def _f(x, nd=3):
    return f"{x:+.{nd}f}" if isinstance(x, (int, float)) else "n/a"


def write_md(summary, path):
    m = summary["meta"]
    L = ["# In-game pace-regime residual analysis (ensemble TOTAL + player)\n"]
    L.append(f"- usable records **{m['n_usable_records']}** / "
             f"{m['n_total_dated_games']} dated; grid states "
             f"**{m['n_grid_states']:,}**; ridge-priced {m['n_ridge_priced']:,}")
    L.append(f"- regime = {m['regime_def']}")
    L.append(f"- leak-safety: {m['leak_safety']}\n")

    L.append("## TEAM TOTAL residual by live-pace regime\n")
    L.append("signed bias = projected_total - actual_total  (NEG = ensemble "
             "UNDER-projects the total)\n")
    L.append("| regime | n | ratio | playshare | ENS bias | ENS mae | "
             "PROD bias | PROD mae |")
    L.append("|---|--:|--:|--:|--:|--:|--:|--:|")
    for rb in REGIME_LABELS:
        d = summary["team_total_by_regime"].get(rb)
        if not d:
            continue
        L.append(f"| {rb} | {d['n']} | {d['ratio_mean']:.3f} | "
                 f"{d['played_share_mean']:.2f} | {_f(d['ens_total_bias'],2)} | "
                 f"{d['ens_total_mae']:.2f} | {_f(d['prod_total_bias'],2)} | "
                 f"{d['prod_total_mae']:.2f} |")
    L.append("")

    c = summary["regime_correlation"]
    if c:
        L.append("## Regime -> signed-total-residual relationship\n")
        L.append(f"- Pearson(ratio, ENS signed total resid) = "
                 f"**{c.get('pearson_ratio_vs_ens_signed_total'):+.4f}**")
        L.append(f"- Pearson(ratio, PROD signed total resid) = "
                 f"{c.get('pearson_ratio_vs_prod_signed_total'):+.4f}")
        if "pearson_early_ratio_vs_ens" in c:
            L.append(f"- early (<50% played): {c['pearson_early_ratio_vs_ens']:+.4f}"
                     f" | late: {c['pearson_late_ratio_vs_ens']:+.4f}")
        L.append(f"- OLS ENS signed resid ~ (ratio-1): intercept "
                 f"{c['ols_ens_signed_intercept']:+.3f}, slope "
                 f"**{c['ols_ens_signed_slope_per_unit_ratio']:+.2f}** pts per "
                 f"unit ratio\n")

    L.append("## PLAYER counting-stat bias by regime (production snapshot)\n")
    L.append("signed bias = projected - actual (NEG = UNDER); the snapshot head "
             "is the production extrapolation that pace would tilt.\n")
    L.append("| regime | n_pts | " + " | ".join(COUNTING) + " |")
    L.append("|---|--:|" + "|".join(["--:"] * len(COUNTING)) + "|")
    for rb in REGIME_LABELS:
        d = summary["player_counting_bias_by_regime"].get(rb)
        if not d:
            continue
        cells = []
        for s in COUNTING:
            b = d[s]["bias"]
            cells.append(_f(b, 2) if b is not None else "n/a")
        L.append(f"| {rb} | {d['n_states_pts']} | " + " | ".join(cells) + " |")
    L.append("")

    L.append("## READ\n")
    L.append("If ENS bias is NEGATIVE in HOT regimes (>1.07) and POSITIVE in "
             "COLD (<0.93), the ensemble under/over-projects with live tempo -> "
             "a pace blend can correct it. If the slope is ~0 or the sign says "
             "live pace MEAN-REVERTS, a naive extrapolate-live-pace rule LOSES.")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=300)
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--min-train", type=int, default=40)
    args = ap.parse_args()
    summary = run(args.max_games, args.folds, args.min_train)
    jp = os.path.join(PLAN_DIR, "pace_regime_residuals.json")
    mp = os.path.join(PLAN_DIR, "pace_regime_residuals.md")
    with open(jp, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)
    write_md(summary, mp)
    print(f"\n[pace-resid] wrote {jp}\n[pace-resid] wrote {mp}")
    print(json.dumps({"team_total_by_regime": summary["team_total_by_regime"],
                      "regime_correlation": summary["regime_correlation"]},
                     indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
