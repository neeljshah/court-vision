"""FRESHNESS / CLV -- the #1 documented money lane, GRADED for the first time on real open+close lines.

The EDGE_GATE corpora are single-snapshot, so CLV was "un-gradable offline". But `data/cache/spreads/*.json`
(ESPN scoreboard) carries OPEN and CLOSE game lines (spread/total/moneyline) + final scores for the full
2025-26 season -- the open/close pair the prop corpora lack. This grades the freshness thesis:
  - is the model AHEAD of the market (does its as-of margin predict the open->close move)? -> NO (corr ~0)
  - does the line MOVE carry real information (predict the outcome beyond the open)? -> YES (corr ~0.20)
  - what is the freshness CEILING (ATS hit of capturing the move at the open)? -> ~58% (64% on 3+pt moves)
Conclusion: the freshness/CLV edge is REAL and LARGE, but it is NOT the model's -- it requires the SAME-DAY
INFO (injuries/sharp money) that drives the move, plus speed to bet the opener. The model (net-rating) shares
the market's information so it cannot predict the move. This is exactly the documented prescription, quantified.

  python scripts/team_system/freshness_clv_analysis.py
"""
from __future__ import annotations
import glob, json, os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPREADS = os.path.join(ROOT, "data", "cache", "spreads")
TS = os.path.join(ROOT, "data", "cache", "team_system")


def _am(s):
    try:
        return float(str(s).replace("+", ""))
    except Exception:
        return None


def parse_lines():
    rows = []
    for f in sorted(glob.glob(os.path.join(SPREADS, "*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        for e in d.get("events", []):
            comp = e.get("competitions", [{}])[0]
            if not comp.get("status", {}).get("type", {}).get("completed"):
                continue
            cs = {c.get("homeAway"): c for c in comp.get("competitors", [])}
            if "home" not in cs or "away" not in cs:
                continue
            try:
                hs, as_ = float(cs["home"]["score"]), float(cs["away"]["score"])
            except Exception:
                continue
            odds = comp.get("odds", [])
            if not odds:
                continue
            hto = odds[0].get("homeTeamOdds", {})
            op = _am(hto.get("open", {}).get("pointSpread", {}).get("american"))
            cl = _am(hto.get("close", {}).get("pointSpread", {}).get("american"))
            if op is None or cl is None:
                continue
            rows.append(dict(date=os.path.basename(f)[:8], open_spread=op, close_spread=cl,
                             home_margin=hs - as_, total_pts=hs + as_))
    D = pd.DataFrame(rows)
    D["d"] = pd.to_datetime(D["date"], format="%Y%m%d").dt.strftime("%Y-%m-%d")
    D["m"] = D["home_margin"].round().astype(int)
    D["t"] = D["total_pts"].round().astype(int)
    return D


def main():
    gl = parse_lines()
    print(f"parsed {len(gl)} completed games with open+close spreads")
    print(f"  mean |line move| open->close: {(gl.close_spread - gl.open_spread).abs().mean():.2f} pts "
          f"({(gl.close_spread - gl.open_spread).abs().ge(1).mean()*100:.0f}%% move >=1pt)")
    # close sharper than open?
    eo = np.abs(-gl.open_spread - gl.home_margin).mean(); ec = np.abs(-gl.close_spread - gl.home_margin).mean()
    print(f"  margin pred error: OPEN {eo:.2f} vs CLOSE {ec:.2f} -> close is {'sharper' if ec < eo else 'not sharper'}")

    # join the model's leak-free as-of margin on (date, realized margin, total) -- unique game signature
    wf = pd.read_parquet(os.path.join(TS, "walkforward_league_preds.parquet"))
    wf["m"] = wf["margin"].round().astype(int); wf["t"] = wf["total"].round().astype(int)
    J = gl.merge(wf, left_on=["d", "m", "t"], right_on=["date", "m", "t"], how="inner",
                 suffixes=("", "_wf")).drop_duplicates(subset=["d", "m", "t"])
    J["open_implied"] = -J["open_spread"]; J["close_implied"] = -J["close_spread"]
    J["model_vs_open"] = J["m2_margin"] - J["open_implied"]
    J["line_move"] = J["close_implied"] - J["open_implied"]
    import scipy.stats as ss
    r1, p1 = ss.pearsonr(J.model_vs_open, J.line_move)
    r2, p2 = ss.pearsonr(J.line_move, J.m - J.open_implied)
    print(f"\njoined {len(J)} games (model as-of margin + open/close + outcome)")
    print(f"  corr(model-vs-open, line-move) = {r1:+.3f} (p={p1:.3f})  -> model {'AHEAD of' if p1 < 0.05 and r1 > 0 else 'NOT ahead of'} the market move")
    print(f"  corr(line-move, outcome-residual) = {r2:+.3f} (p={p2:.3f})  -> the move {'CARRIES real info' if p2 < 0.05 else 'is noise'}")

    # freshness CEILING: ATS hit of capturing the move-toward side at the OPEN spread
    M = J[(J.line_move.abs() >= 0.5) & (J.m != J.open_implied)].copy()
    M["win"] = np.where(M.line_move > 0, M.m > M.open_implied, M.m < M.open_implied)
    print(f"\nFRESHNESS CEILING (bet the move-toward side at the OPEN, n={len(M)}): "
          f"{M.win.mean()*100:.1f}%% ATS (break-even 52.4%%)")
    for lo, hi, lab in [(0.5, 1.5, "0.5-1.5"), (1.5, 3, "1.5-3"), (3, 99, "3+")]:
        s = M[(M.line_move.abs() >= lo) & (M.line_move.abs() < hi)]
        if len(s):
            print(f"    move {lab}pt (n={len(s)}): {s.win.mean()*100:.1f}%%")
    out = dict(n_games=int(len(gl)), n_joined=int(len(J)), corr_model_move=float(r1), p_model_move=float(p1),
               corr_move_outcome=float(r2), p_move_outcome=float(p2), freshness_ceiling_ats=float(M.win.mean()),
               note=("freshness/CLV is REAL+LARGE (move predicts outcome r=0.20, capturing it = ~58%% ATS) but "
                     "NOT the model's (model-vs-open does not predict the move) -> a same-day-info/speed edge, "
                     "not a pregame-model edge. Ceiling = hindsight move-following; realizing it needs the "
                     "injury/sharp-money feed that drives the move."))
    json.dump(out, open(os.path.join(TS, "freshness_clv.json"), "w"), indent=1)
    print("\nwrote freshness_clv.json")


if __name__ == "__main__":
    main()
