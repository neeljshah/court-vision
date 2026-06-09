"""Go through every game and extract deep per-player MATCHUP / SCHEME / SITUATIONAL
intelligence, recorded to the Obsidian vault + a durable JSON cache.

"The box score lies; basketball tells the truth." This mines the dated game data
for the detail the season-average box score hides:

  1. HEAD-TO-HEAD (coverage_faced_matrix, 2024-25): when player X is guarded by
     defender Y, how X actually scores (pts / possession faced, FG%, 3P%) vs his
     own baseline -> who SHUTS HIM DOWN and who he FEASTS on.
  2. AS A DEFENDER (coverage_faced + defender_matchups 24-25 & 25-26): who X
     guards, how much he allows, switch rate -> a defensive scouting report.
  3. vs OPPONENT TEAMS (gamelogs, 3 seasons): per-team PTS/REB/AST splits, best
     and worst opponents, home/away.
  4. SCHEME SPLITS (atlas_player_vs_scheme_splits): best/worst defensive scheme.
  5. QUARTER SHAPE (player_quarter_stats): Q1..Q4 scoring distribution + Q4 fade.

Output (read-only except these):
  - data/cache/intel/player_<pid>.json   (durable structured intelligence)
  - vault/Intelligence/Matchups/Players/<pid>_<slug>.md   (base scouting note)

Deterministic + accurate; parallel agents enrich these with narrative synthesis.
Run: python scripts/intel/build_matchup_intelligence.py [--limit N] [--pids p1 p2]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
from collections import defaultdict

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(ROOT, "data", "cache")
NBA = os.path.join(ROOT, "data", "nba")
OUT_JSON = os.path.join(CACHE, "intel")
OUT_VAULT = os.path.join(ROOT, "vault", "Intelligence", "Matchups", "Players")

STAT_KEYS = ["PTS", "REB", "AST", "FG3M", "STL", "BLK", "TOV", "MIN"]


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


def _name_map():
    m = {}
    for season in ("2023-24", "2024-25", "2025-26"):
        p = os.path.join(NBA, f"player_avgs_{season}.json")
        if os.path.exists(p):
            for nm, info in json.load(open(p, encoding="utf-8")).items():
                pid = info.get("player_id")
                if pid is not None:
                    m[int(pid)] = nm.title()
    return m


def _matchup_opp(m):
    mm = re.match(r"^[A-Z]{2,4}\s*(@|vs\.?)\s*([A-Z]{2,4})", str(m).strip())
    return mm.group(2) if mm else None


def load_gamelogs(pid):
    """All games across seasons for a player: list of dicts with parsed fields."""
    rows = []
    for season in ("2023-24", "2024-25", "2025-26"):
        p = os.path.join(NBA, f"gamelog_{pid}_{season}.json")
        if not os.path.exists(p):
            continue
        try:
            for r in json.load(open(p, encoding="utf-8")):
                opp = _matchup_opp(r.get("MATCHUP", ""))
                home = "vs" in str(r.get("MATCHUP", ""))
                rec = {"season": season, "opp": opp, "home": home}
                for k in STAT_KEYS:
                    try:
                        rec[k] = float(r.get(k)) if r.get(k) is not None else np.nan
                    except (TypeError, ValueError):
                        rec[k] = np.nan
                rows.append(rec)
        except Exception:
            continue
    return rows


def vs_opponent_splits(gl):
    df = pd.DataFrame(gl)
    if df.empty or "opp" not in df:
        return {}
    out = {}
    g = df.dropna(subset=["opp"]).groupby("opp")
    for opp, sub in g:
        if len(sub) < 1:
            continue
        out[opp] = {"n": int(len(sub)),
                    "pts": round(float(sub["PTS"].mean()), 1),
                    "reb": round(float(sub["REB"].mean()), 1),
                    "ast": round(float(sub["AST"].mean()), 1),
                    "min": round(float(sub["MIN"].mean()), 1)}
    return out


def h2h_offense(cf, pid, base_ppp):
    """coverage_faced rows where this player is the OFFENSE. Classify each defender."""
    sub = cf[cf.off_player_id == pid].copy()
    if sub.empty:
        return []
    sub = sub[sub.partial_possessions >= 15]  # enough sample
    out = []
    for r in sub.sort_values("partial_possessions", ascending=False).head(15).itertuples(index=False):
        poss = float(r.partial_possessions)
        ppp = float(r.off_points) / poss if poss > 0 else np.nan
        rel = ppp / base_ppp if base_ppp and np.isfinite(ppp) else np.nan
        out.append({
            "defender": r.def_player_name, "def_id": int(r.def_player_id),
            "n_games": int(r.n_games_matched), "poss": round(poss, 1),
            "pts": int(r.off_points), "fga": int(r.off_fga),
            "fg_pct": round(float(r.off_fg_pct), 3) if pd.notna(r.off_fg_pct) else None,
            "fg3_pct": round(float(r.off_fg3_pct), 3) if pd.notna(r.off_fg3_pct) else None,
            "ppp": round(ppp, 2) if np.isfinite(ppp) else None,
            "rel_to_self": round(rel, 2) if np.isfinite(rel) else None,
            "verdict": ("tough" if rel < 0.85 else "feasts" if rel > 1.15 else "neutral") if np.isfinite(rel) else "na",
        })
    return out


def h2h_defense(cf, pid):
    """coverage_faced rows where this player is the DEFENDER: who he guards + allows."""
    sub = cf[cf.def_player_id == pid].copy()
    if sub.empty:
        return []
    sub = sub[sub.partial_possessions >= 15]
    out = []
    for r in sub.sort_values("partial_possessions", ascending=False).head(12).itertuples(index=False):
        poss = float(r.partial_possessions)
        ppp = float(r.off_points) / poss if poss > 0 else np.nan
        out.append({
            "guarded": r.off_player_name, "off_id": int(r.off_player_id),
            "n_games": int(r.n_games_matched), "poss": round(poss, 1),
            "pts_allowed": int(r.off_points), "fga": int(r.off_fga),
            "fg_pct_allowed": round(float(r.off_fg_pct), 3) if pd.notna(r.off_fg_pct) else None,
            "ppp_allowed": round(ppp, 2) if np.isfinite(ppp) else None,
        })
    return out


def defender_scouting(dm_by_pid, pid):
    """defender_matchups season aggregate: allowed pts/fg%, switch rate, volume."""
    out = {}
    for season, dmg in dm_by_pid.items():
        rows = dmg.get(pid)
        if rows is None or rows.empty:
            continue
        poss = float(rows.partial_possessions.sum())
        out[season] = {
            "games": int(rows.game_id.nunique()),
            "matchup_min_total": round(float(rows.matchup_minutes_total.sum()), 1),
            "pts_allowed_per_game": round(float(rows.points_allowed.sum()) / max(rows.game_id.nunique(), 1), 1),
            "fg_pct_allowed": round(float(rows.fg_made_allowed.sum()) / max(float(rows.fg_attempted_allowed.sum()), 1.0), 3),
            "fg3_pct_allowed": round(float(rows.fg3_made_allowed.sum()) / max(float(rows.fg3_attempted_allowed.sum()), 1.0), 3),
            "switches_per_game": round(float(rows.switches_on.sum()) / max(rows.game_id.nunique(), 1), 1),
            "blocks_per_game": round(float(rows.blocks_matchup.sum()) / max(rows.game_id.nunique(), 1), 2),
        }
    return out


def quarter_shape(qs_by_pid, pid):
    rows = qs_by_pid.get(pid)
    if rows is None or rows.empty:
        return {}
    by_p = rows.groupby("period").agg(pts=("pts", "mean"), mn=("pts", "mean")).reset_index()
    dist = {int(r.period): round(float(r.pts), 2) for r in by_p.itertuples(index=False) if 1 <= int(r.period) <= 4}
    q1 = dist.get(1, 0.0)
    q4 = dist.get(4, 0.0)
    fade = round(q4 - q1, 2)
    return {"pts_by_quarter": dist, "q4_minus_q1": fade,
            "q4_fade_flag": fade < -1.0}


def scheme_split(vs_scheme, pid):
    sub = vs_scheme[vs_scheme.player_id == pid]
    if sub.empty:
        return {}
    r = sub.iloc[0]
    return {"best_scheme": r.get("best_scheme"), "worst_scheme": r.get("worst_scheme"),
            "ts_best_minus_worst": round(float(r.get("scheme_ts_pct_best_minus_worst", 0) or 0), 3),
            "n_games": int(r.get("n_games_total", 0) or 0)}


def write_note(pid, name, intel):
    os.makedirs(OUT_VAULT, exist_ok=True)
    fp = os.path.join(OUT_VAULT, f"{pid}_{slug(name)}.md")
    L = []
    L.append("<!-- MATCHUP-INTEL v1 (deterministic base; agents enrich) -->")
    L.append(f"# {name} — Matchup & Scheme Intelligence")
    L.append(f"**player_id:** {pid}  ·  *generated from game data*")
    L.append("")
    # H2H offense
    off = intel.get("h2h_as_offense", [])
    if off:
        L.append("## Head-to-Head — guarded by (2024-25, ≥15 poss)")
        L.append("How he scores vs specific defenders, relative to his own baseline PPP.")
        L.append("")
        L.append("| Defender | G | Poss | Pts | FG% | 3P% | PPP | vs self | read |")
        L.append("|---|--|--|--|--|--|--|--|--|")
        for d in off:
            L.append(f"| {d['defender']} | {d['n_games']} | {d['poss']} | {d['pts']} | "
                     f"{'' if d['fg_pct'] is None else int(d['fg_pct']*100)} | "
                     f"{'' if d['fg3_pct'] is None else int(d['fg3_pct']*100)} | "
                     f"{d['ppp']} | {d['rel_to_self']} | **{d['verdict']}** |")
        tough = [d['defender'] for d in off if d['verdict'] == 'tough']
        feast = [d['defender'] for d in off if d['verdict'] == 'feasts']
        if tough:
            L.append(f"\n- **Toughest matchups (held below 85% of baseline):** {', '.join(tough[:6])}")
        if feast:
            L.append(f"- **Feasts on (above 115% of baseline):** {', '.join(feast[:6])}")
        L.append("")
    # As defender
    dfn = intel.get("h2h_as_defender", [])
    if dfn:
        L.append("## As a Defender — who he guards (2024-25, ≥15 poss)")
        L.append("| Assignment | G | Poss | Pts allowed | FG% allowed | PPP allowed |")
        L.append("|---|--|--|--|--|--|")
        for d in dfn:
            L.append(f"| {d['guarded']} | {d['n_games']} | {d['poss']} | {d['pts_allowed']} | "
                     f"{'' if d['fg_pct_allowed'] is None else int(d['fg_pct_allowed']*100)} | {d['ppp_allowed']} |")
        L.append("")
    # Defender scouting
    sc = intel.get("defender_scouting", {})
    if sc:
        L.append("## Defensive Scouting (defender_matchups)")
        for season, s in sorted(sc.items()):
            L.append(f"- **{season}:** {s['games']}g, {s['pts_allowed_per_game']} pts allowed/g, "
                     f"FG% allowed {int(s['fg_pct_allowed']*100)}, 3P% allowed {int(s['fg3_pct_allowed']*100)}, "
                     f"{s['switches_per_game']} switches/g, {s['blocks_per_game']} blk/g")
        L.append("")
    # vs opponents
    vso = intel.get("vs_opponents", {})
    if vso:
        items = sorted(vso.items(), key=lambda kv: -kv[1]["pts"])
        L.append("## vs Opponent Teams (career, all seasons)")
        best = items[0]; worst = items[-1]
        L.append(f"- **Best scoring vs:** {best[0]} ({best[1]['pts']} pts, n={best[1]['n']})  ·  "
                 f"**Worst vs:** {worst[0]} ({worst[1]['pts']} pts, n={worst[1]['n']})")
        L.append("")
        L.append("| Opp | G | PTS | REB | AST | MIN |")
        L.append("|---|--|--|--|--|--|")
        for opp, s in sorted(vso.items()):
            L.append(f"| [[{opp}]] | {s['n']} | {s['pts']} | {s['reb']} | {s['ast']} | {s['min']} |")
        L.append("")
    # scheme
    ss = intel.get("scheme_split", {})
    if ss and ss.get("best_scheme"):
        L.append("## Scheme Splits (vs defensive scheme)")
        L.append(f"- **Best vs:** [[Schemes/{ss['best_scheme']}]]  ·  **Worst vs:** [[Schemes/{ss['worst_scheme']}]]  "
                 f"·  TS% best−worst = {ss['ts_best_minus_worst']} (n={ss['n_games']})")
        L.append("")
    # quarter
    q = intel.get("quarter_shape", {})
    if q and q.get("pts_by_quarter"):
        L.append("## Quarter Shape / Fatigue")
        pq = q["pts_by_quarter"]
        L.append(f"- **Pts by quarter:** Q1 {pq.get(1,'–')} · Q2 {pq.get(2,'–')} · Q3 {pq.get(3,'–')} · Q4 {pq.get(4,'–')}  "
                 f"(Q4−Q1 = {q['q4_minus_q1']}{' — **fades late**' if q.get('q4_fade_flag') else ''})")
        L.append("")
    L.append(f"\n> Links: [[Players/{pid}_{slug(name)}]] (playstyle) · base note — agents append narrative below this line.")
    open(fp, "w", encoding="utf-8").write("\n".join(L))
    return fp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--pids", type=int, nargs="*")
    args = ap.parse_args()

    os.makedirs(OUT_JSON, exist_ok=True)
    names = _name_map()
    print("loading sources ...", flush=True)
    cf = pd.read_parquet(os.path.join(CACHE, "coverage_faced_matrix.parquet"))
    vs_scheme = pd.read_parquet(os.path.join(ROOT, "data", "cache", "atlas_player_vs_scheme_splits.parquet")) \
        if os.path.exists(os.path.join(CACHE, "atlas_player_vs_scheme_splits.parquet")) else pd.DataFrame(columns=["player_id"])
    dm_by_pid = {}
    for season, fname in [("2024-25", "defender_matchups_2024-25.parquet"),
                          ("2025-26", "defender_matchups_2025-26.parquet")]:
        p = os.path.join(ROOT, "data", fname)
        if os.path.exists(p):
            d = pd.read_parquet(p)
            dm_by_pid[season] = {pid: sub for pid, sub in d.groupby("def_player_id")}
    qs_by_pid = {}
    qp = os.path.join(ROOT, "data", "player_quarter_stats.parquet")
    if os.path.exists(qp):
        q = pd.read_parquet(qp)
        qs_by_pid = {pid: sub for pid, sub in q.groupby("player_id")}

    # candidate players: union of coverage offense + defender_matchups + gamelogs
    pids = set(cf.off_player_id.unique()) | set(cf.def_player_id.unique())
    for s in dm_by_pid.values():
        pids |= set(s.keys())
    if args.pids:
        pids = set(args.pids)
    pids = sorted(int(p) for p in pids if not pd.isna(p))
    if args.limit:
        pids = pids[:args.limit]
    print(f"processing {len(pids)} players ...", flush=True)

    written = 0
    for i, pid in enumerate(pids):
        name = names.get(pid)
        gl = load_gamelogs(pid)
        if not name:
            # try coverage name
            row = cf[cf.off_player_id == pid].head(1)
            name = (row.off_player_name.iloc[0] if not row.empty else f"Player {pid}")
        # baseline PPP from gamelog (pts per ~ possession proxy: pts / (fga+0.44fta) unavailable -> use pts/min*... )
        df = pd.DataFrame(gl)
        base_ppp = None
        if not df.empty and df["PTS"].notna().any():
            # crude PPP baseline: season pts per (poss faced ~ proportional); use pts/ (0.9*min) scaled. We
            # instead use the coverage matrix's own implied baseline: mean off_points/poss across all his rows.
            mine = cf[cf.off_player_id == pid]
            tot_poss = float(mine.partial_possessions.sum())
            base_ppp = (float(mine.off_points.sum()) / tot_poss) if tot_poss > 0 else None
        intel = {
            "player_id": pid, "name": name,
            "h2h_as_offense": h2h_offense(cf, pid, base_ppp) if base_ppp else [],
            "h2h_as_defender": h2h_defense(cf, pid),
            "defender_scouting": defender_scouting(dm_by_pid, pid),
            "vs_opponents": vs_opponent_splits(gl),
            "scheme_split": scheme_split(vs_scheme, pid),
            "quarter_shape": quarter_shape(qs_by_pid, pid),
            "baseline_ppp_2024_25": round(base_ppp, 3) if base_ppp else None,
        }
        # only write if there's meaningful content
        has = (intel["h2h_as_offense"] or intel["h2h_as_defender"]
               or intel["defender_scouting"] or len(intel["vs_opponents"]) >= 3)
        if not has:
            continue
        json.dump(intel, open(os.path.join(OUT_JSON, f"player_{pid}.json"), "w", encoding="utf-8"), indent=1)
        write_note(pid, name, intel)
        written += 1
        if written % 50 == 0:
            print(f"  {written} notes written ({i+1}/{len(pids)})", flush=True)
    print(f"DONE: {written} player matchup-intelligence notes -> {OUT_VAULT}", flush=True)
    print(f"      + structured JSON -> {OUT_JSON}", flush=True)


if __name__ == "__main__":
    main()
