"""exp_pace_residual.py — do leak-free PACE + TEAM-STRENGTH signals explain the
PTS/REB OOF residual out-of-sample? (The model currently has NO pace feature.)

season_games_<season>.json['rows'] carries as-of (leak-free, verified) per-team
pace / off_rtg / def_rtg / net_rtg. For each 2025-26 OOF row we attach the
player's-team and opponent pre-game state and test whether an XGB correction on
  { avg_pace, team_off, opp_def, exp_scoring_env, exp_margin, abs_exp_margin, ... }
reduces MAE on a future hold-out. Train on early 2025-26, test on late. If
oof_pred + correction beats oof_pred OOS, these signals are worth wiring in.
GPU XGB. Touches no production model.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
from scripts.run_gate1_full_analysis import _load_gamelog_combined  # noqa: E402

OOF = _ROOT / "data" / "cache" / "pregame_oof.parquet"
SPLIT = "2026-02-15"


def load_team_state():
    """idx[(date, team)] = {pace, off, def, net} as-of pre-game, from both sides."""
    idx = {}
    for season in ("2023-24", "2024-25", "2025-26"):
        p = _ROOT / "data" / "nba" / f"season_games_{season}.json"
        if not p.exists():
            continue
        for r in json.load(open(p, encoding="utf-8")).get("rows", []):
            d = r.get("game_date")
            for side in ("home", "away"):
                t = r.get(f"{side}_team")
                pace = r.get(f"{side}_pace")
                if not t or d is None or pace is None:
                    continue
                idx[(d, t)] = {
                    "pace": float(pace),
                    "off": float(r.get(f"{side}_off_rtg") or 112.0),
                    "def": float(r.get(f"{side}_def_rtg") or 112.0),
                    "net": float(r.get(f"{side}_net_rtg") or 0.0),
                }
    return idx


def _parse_matchup(m):
    """'LAC @ MIA' -> (LAC, MIA, away);  'OKC vs. SAS' -> (OKC, SAS, home)."""
    if not m:
        return None
    if " @ " in m:
        a, b = m.split(" @ "); return a.strip(), b.strip(), 0  # player team away
    if " vs. " in m:
        a, b = m.split(" vs. "); return a.strip(), b.strip(), 1
    return None


def main():
    oof = pd.read_parquet(OOF)
    oof = oof[oof["game_date"].astype(str) >= "2025-10-01"].copy()
    team_state = load_team_state()
    # gamelog date->matchup per player
    glcache = {}

    def team_for(pid, gdate):
        if pid not in glcache:
            mp = {}
            for d, g in _load_gamelog_combined(pid):
                mp[d.date().isoformat()] = g.get("MATCHUP")
            glcache[pid] = mp
        return glcache[pid].get(gdate)

    recs = []
    for stat in ("pts", "reb"):
        sub = oof[oof["stat"] == stat]
        for r in sub.itertuples(index=False):
            gd = str(r.game_date)[:10]
            mu = team_for(int(r.player_id), gd)
            pm = _parse_matchup(mu)
            if not pm:
                continue
            team, opp, is_home = pm
            ts = team_state.get((gd, team))
            os_ = team_state.get((gd, opp))
            if ts is None or os_ is None:
                continue
            avg_pace = (ts["pace"] + os_["pace"]) / 2
            exp_margin = ts["net"] - os_["net"]
            recs.append({
                "stat": stat, "date": gd,
                "oof_pred": float(r.oof_pred), "actual": float(r.actual),
                "resid": float(r.actual - r.oof_pred),
                "avg_pace": avg_pace, "team_pace": ts["pace"], "opp_pace": os_["pace"],
                "team_off": ts["off"], "opp_def": os_["def"],
                "exp_env": (ts["off"] + os_["def"]) / 2,
                "exp_margin": exp_margin, "abs_margin": abs(exp_margin),
                "is_home": is_home,
            })
    df = pd.DataFrame(recs)
    FEATS = ["avg_pace", "team_pace", "opp_pace", "team_off", "opp_def",
             "exp_env", "exp_margin", "abs_margin", "is_home"]

    for stat in ("pts", "reb"):
        d = df[df["stat"] == stat]
        tr = d[d["date"] < SPLIT]; te = d[d["date"] >= SPLIT]
        if len(te) < 200:
            print(f"[{stat}] too few test rows ({len(te)})"); continue
        params = {"objective": "reg:absoluteerror", "max_depth": 4, "eta": 0.03,
                  "subsample": 0.8, "colsample_bytree": 0.8, "device": "cuda",
                  "tree_method": "hist"}
        dtr = xgb.DMatrix(tr[FEATS], label=tr["resid"])
        dte = xgb.DMatrix(te[FEATS])
        try:
            bst = xgb.train(params, dtr, num_boost_round=300)
        except Exception as exc:
            print(f"[cuda->cpu: {exc}]"); params["device"] = "cpu"
            bst = xgb.train(params, dtr, num_boost_round=300)
        corr = bst.predict(dte)
        mae_base = te["resid"].abs().mean()  # = MAE of oof_pred vs actual
        mae_corr = (te["resid"].values - corr).__abs__().mean()
        # damped correction (half) — guards against overfit corrections
        mae_half = (te["resid"].values - 0.5 * corr).__abs__().mean()
        print(f"\n{stat.upper()} residual-learnability (train<{SPLIT} n={len(tr):,}, "
              f"test>={SPLIT} n={len(te):,}):")
        print(f"  OOF MAE (uncorrected)        : {mae_base:.4f}")
        print(f"  OOF + pace/strength correction: {mae_corr:.4f}  "
              f"({(mae_base-mae_corr)/mae_base*100:+.2f}%)")
        print(f"  OOF + 0.5x correction (damped): {mae_half:.4f}  "
              f"({(mae_base-mae_half)/mae_base*100:+.2f}%)")
        # which features carry signal
        imp = bst.get_score(importance_type="gain")
        top = sorted(imp.items(), key=lambda kv: -kv[1])[:5]
        print(f"  top gain features: {', '.join(f'{k}={v:.0f}' for k,v in top)}")


if __name__ == "__main__":
    sys.exit(main())
