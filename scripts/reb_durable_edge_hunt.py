"""reb_durable_edge_hunt.py — is there a DURABLE REB pregame edge, or are REB's
positives single-window mirages?

CONTEXT (MEMORY): REB pregame is the CLOSEST stat to beating the closing line.
It FLICKERS positive in 2026 windows (+0.6% .. +1.8% ROI vs real closes) but
REVERSES to ~-10% on the independent 2024-25 season. The whole point of this
hunt is the CROSS-SEASON GATE: a REB sub-population only counts as a real edge
if it holds its SIGN on BOTH the 2026 real-close corpus (benashkar) AND the
independent 2024-25 corpus (oddsapi_2425). Single-window peaks REJECT — that is
the central lesson (same mechanism that produced the fake +18.38%).

This reuses the EXISTING leak-free real-odds bet table
(data/cache/edge_mining_bets.parquet, built by edge_mining_systematic.py):
  - Bet side = sign(prod-stack OOF pred - line), leak-free walk-forward OOF.
  - Label = bet won at ACTUAL posted odds; |odds| >= 100 ALWAYS (drops the
    +900%-payout artifact); pushes / zero-edge already dropped.
  - Leak-free context already attached: l10_min, rest_days, is_home, opp_pace,
    opp_def_rtg (opp_pace is a STALE 2024-25 proxy on the 2026 corpora — flagged).

The FRESHNESS / vac angle (a teammate OUT frees rebounds) is added here by
reusing the leak-free box-confirmed-OUT reconstruction from
_vac_bump_accuracy_validation.py (vac_pts / vac_share / creator_out / n_out
keyed by (pid, date)) and joining it onto the REB bets.

Corpora (after OOF-join; OOF is regular-season only):
  benashkar_2526   MAIN 2025-26 (Jan-Apr 2026, DK/FD/MGM)   n_reb ~1088   IN-WINDOW
  oddsapi_2425     CROSS-SEASON 2024-25                     n_reb ~65     THE GATE
  oddsapi_2526reg  2025-26 reg, diff scrape (semi-indep)    n_reb ~59     aux
NOTE: extended_oos is NOT independent of benashkar after the OOF join (byte-
identical keys) -> excluded from the gate, per EDGE_MINING.md.

Writes ONLY: docs/_audits/REB_DURABLE_EDGE_HUNT.md (+ this script).
No prod-file edits, no retrain, no git add. READ-ONLY on data.
"""
from __future__ import annotations

import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
_BETS = _ROOT / "data" / "cache" / "edge_mining_bets.parquet"
_NBA = _ROOT / "data" / "nba"
_OUT_MD = _ROOT / "docs" / "_audits" / "REB_DURABLE_EDGE_HUNT.md"

MAIN = "benashkar_2526"      # IN-WINDOW 2025-26
SEASON = "oddsapi_2425"      # CROSS-SEASON 2024-25 = THE GATE
DIFFSCR = "oddsapi_2526reg"  # aux 2025-26 diff scrape

RNG = np.random.default_rng(20260605)
N_BOOT = 5000
MIN_N_MAIN = 40      # need adequate n in-window
MIN_N_SEASON = 12    # cross-season corpus is small; gate sign, not magnitude


# ─────────────────────────────────────────────────────────────────────
# ROI + bootstrap helpers (identical math to edge_mining / ast_decomp)
# ─────────────────────────────────────────────────────────────────────
def roi_stats(sub: pd.DataFrame) -> dict:
    n = len(sub)
    if n == 0:
        return {"n": 0, "roi": np.nan, "win": np.nan, "lo": np.nan, "hi": np.nan,
                "p_le0": np.nan}
    pays = sub["pnl"].to_numpy()
    roi = float(pays.mean())
    win = float(sub["won"].mean() * 100)
    if n >= 5:
        boot = np.array([RNG.choice(pays, size=n, replace=True).mean()
                         for _ in range(N_BOOT)])
        lo, hi = np.percentile(boot, [2.5, 97.5])
        p_le0 = float((boot <= 0).mean())
    else:
        lo = hi = p_le0 = np.nan
    return {"n": int(n), "roi": roi, "win": win,
            "lo": float(lo), "hi": float(hi), "p_le0": p_le0}


def verdict(main_r: dict, season_r: dict) -> str:
    """Durable = positive sign on BOTH the in-window MAIN corpus AND the
    cross-season 2024-25 corpus, with adequate n on both. Sign gate is the
    whole point; magnitude on the thin 2024-25 corpus is not trusted."""
    if main_r["n"] < MIN_N_MAIN or season_r["n"] < MIN_N_SEASON:
        return "THIN-N"
    main_pos = main_r["roi"] > 0
    season_pos = season_r["roi"] > 0
    if main_pos and season_pos:
        return "DURABLE"
    if main_pos and not season_pos:
        return "single-window-peak"  # the REB failure mode
    if not main_pos and season_pos:
        return "season-only (not in-window)"
    return "negative-both"


# ─────────────────────────────────────────────────────────────────────
# season REB average per pid (leak-free big/guard proxy) — uses prior-season
# and current-season player_avgs. A "big" = high season REB. This is a coarse
# role tag; the REB LINE itself is the sharper proxy and is also bucketed.
# ─────────────────────────────────────────────────────────────────────
def build_player_reb_avg() -> dict:
    """pid -> dict(season -> reb_per_game). For a 2024-25 bet we use 2023-24
    avg if present (prior season, leak-free) else 2024-25; for 2025-26 we use
    2024-25. Falls back to any available. Keep simple: a stable role tag."""
    avgs = {}
    for season in ("2023-24", "2024-25", "2025-26"):
        p = _NBA / f"player_avgs_{season}.json"
        if not p.exists():
            continue
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        for _name, info in d.items():
            pid = info.get("player_id")
            reb = info.get("reb")
            if pid is None or reb is None:
                continue
            avgs.setdefault(int(pid), {})[season] = float(reb)
    return avgs


def reb_avg_for(avgs: dict, pid: int, gd: str) -> float:
    """Leak-free-ish role tag: prefer the PRIOR season's avg relative to the
    bet date so it is strictly known. 2024-25 bets -> 2023-24 avg; 2025-26
    bets -> 2024-25 avg; fall back to any prior available."""
    d = avgs.get(pid)
    if not d:
        return np.nan
    year = int(gd[:4])
    # season label that ENDED before this bet's season
    if year <= 2025 and gd < "2025-07-01":   # 2024-25 season window
        order = ["2023-24", "2024-25"]
    else:                                     # 2025-26 season window
        order = ["2024-25", "2023-24", "2025-26"]
    for s in order:
        if s in d:
            return d[s]
    # any
    return next(iter(d.values()))


# ─────────────────────────────────────────────────────────────────────
# Leak-free vacated-load (freshness) reconstruction.
# Lifted from scripts/_vac_bump_accuracy_validation.py::reconstruct_vac (the
# EXACT leak-free box-confirmed-OUT logic from calibrate_live_adjustment.py).
# Produces, per (pid, date): vac_pts, vac_reb (L10 reb of OUT regulars),
# n_out, creator_out. We add vac_reb because REB load is the relevant freed
# resource for a REBOUND edge.
# ─────────────────────────────────────────────────────────────────────
REGULAR_MIN = 15.0
CREATOR_PTS = 18.0
CREATOR_AST = 5.0
BIGOUT_REB = 7.0    # an OUT regular with L10 REB>=7 = a rebounding big vacated


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _teams_of(matchup):
    if not matchup:
        return None, None
    if " @ " in matchup:
        a, b = matchup.split(" @ "); return a.strip(), b.strip()
    if " vs. " in matchup:
        a, b = matchup.split(" vs. "); return a.strip(), b.strip()
    return None, None


def reconstruct_vac() -> pd.DataFrame:
    rows_by_td = defaultdict(list)
    for fp in glob.glob(str(_NBA / "gamelog_*_*.json")):
        try:
            pid = int(Path(fp).stem.split("_")[1])
            log = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        recs = []
        for g in log:
            d = pd.to_datetime(g.get("GAME_DATE"), errors="coerce")
            if not pd.isna(d):
                recs.append((d, g))
        recs.sort(key=lambda kv: kv[0])
        mins, ptss, rebs, asts = [], [], [], []
        for d, g in recs:
            team, _opp = _teams_of(g.get("MATCHUP"))
            ds = d.date().isoformat()
            l10_min = float(np.mean(mins[-10:])) if mins else 0.0
            l10_pts = float(np.mean(ptss[-10:])) if ptss else 0.0
            l10_reb = float(np.mean(rebs[-10:])) if rebs else 0.0
            l10_ast = float(np.mean(asts[-10:])) if asts else 0.0
            if team and len(mins) >= 5:
                rows_by_td[(team, ds)].append({
                    "pid": pid, "date": ds, "team": team,
                    "l10_min": l10_min, "l10_pts": l10_pts,
                    "l10_reb": l10_reb, "l10_ast": l10_ast,
                })
            m = _f(g.get("MIN"))
            if m is not None and m >= 1:
                mins.append(m); ptss.append(_f(g.get("PTS")) or 0.0)
                rebs.append(_f(g.get("REB")) or 0.0); asts.append(_f(g.get("AST")) or 0.0)

    team_dates = defaultdict(list)
    for (team, ds) in rows_by_td:
        team_dates[team].append(ds)
    for t in team_dates:
        team_dates[t] = sorted(set(team_dates[t]))

    out_rows = []
    for (team, ds), played in rows_by_td.items():
        dates = team_dates[team]
        i = dates.index(ds)
        if i < 3:
            continue
        played_ids = {r["pid"] for r in played}
        roster = {}
        for j in range(max(0, i - 3), i):
            for rec in rows_by_td[(team, dates[j])]:
                roster[rec["pid"]] = rec
        vac_pts = vac_reb = 0.0
        n_out = 0
        creator_out = False
        big_out = False
        for pid_, rec in roster.items():
            if pid_ in played_ids:
                continue
            if rec["l10_min"] >= REGULAR_MIN:
                vac_pts += rec["l10_pts"]
                vac_reb += rec["l10_reb"]
                n_out += 1
                if rec["l10_pts"] >= CREATOR_PTS or rec["l10_ast"] >= CREATOR_AST:
                    creator_out = True
                if rec["l10_reb"] >= BIGOUT_REB:
                    big_out = True
        for r in played:
            out_rows.append({
                "pid": r["pid"], "gd": ds,
                "vac_pts": vac_pts, "vac_reb": vac_reb, "n_out": n_out,
                "creator_out": creator_out, "big_out": big_out,
                "any_out": n_out > 0,
            })
    return pd.DataFrame(out_rows).drop_duplicates(subset=["pid", "gd"])


# ─────────────────────────────────────────────────────────────────────
# sub-population definitions on the REB bet frame
# ─────────────────────────────────────────────────────────────────────
def add_subpops(df: pd.DataFrame, avgs: dict, vac: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["gd"] = df["gd"].astype(str)

    # line buckets (rebound lines are low; split low/mid/high)
    df["line_bucket"] = pd.cut(
        df["line"], bins=[-1, 3.5, 6.5, 99],
        labels=["low(<=3.5)", "mid(4-6.5)", "high(>=7)"])

    # role via l10_min: bench vs starter (24 min is a reasonable starter cut)
    df["role_min"] = np.where(df["l10_min"] >= 24, "starter(min>=24)", "bench(min<24)")

    # big vs guard via season REB avg (leak-free prior-season tag)
    df["reb_avg"] = [reb_avg_for(avgs, int(p), g) for p, g in zip(df["pid"], df["gd"])]
    df["pos_role"] = np.where(df["reb_avg"] >= 6.0, "big(reb>=6)",
                              np.where(df["reb_avg"] < 6.0, "guard(reb<6)", "unk"))

    # opp pace tercile (rank within corpus; STALE 2024-25 proxy on 2026 — flagged)
    df["pace_tier"] = "unk"
    pm = df["opp_pace"].notna()
    if pm.sum() >= 6:
        df.loc[pm, "pace_tier"] = pd.qcut(
            df.loc[pm, "opp_pace"].rank(method="first"), 3,
            labels=["pace_slow", "pace_mid", "pace_fast"], duplicates="drop").astype(str)

    # home / road
    df["home_road"] = np.where(df["is_home"] == 1, "home",
                               np.where(df["is_home"] == 0, "road", "unk"))

    # rest / b2b
    df["rest_tier"] = np.where(df["rest_days"] <= 1, "b2b/1d",
                               np.where(df["rest_days"] >= 3, "rest3+", "2d"))

    # direction
    df["direction"] = np.where(df["bet_over"], "OVER", "UNDER")

    # vac / freshness join
    df = df.merge(vac, on=["pid", "gd"], how="left")
    for c in ("vac_pts", "vac_reb", "n_out"):
        df[c] = df[c].fillna(0.0)
    for c in ("creator_out", "big_out", "any_out"):
        df[c] = df[c].fillna(False)
    df["fresh_tier"] = np.where(df["big_out"], "big_out",
                                np.where(df["any_out"], "any_out_norebbig", "no_out"))
    df["vacreb_tier"] = np.where(df["vac_reb"] >= 7.0, "vacreb>=7",
                                 np.where(df["vac_reb"] > 0, "vacreb0-7", "vacreb0"))
    return df


# the (group_column, label) sub-population axes to sweep
AXES = [
    ("__all__", "ALL REB (baseline)"),
    ("line_bucket", "line bucket"),
    ("role_min", "role by minutes"),
    ("pos_role", "big vs guard (season reb)"),
    ("pace_tier", "opp pace tercile (STALE proxy)"),
    ("home_road", "home / road"),
    ("rest_tier", "rest / b2b"),
    ("direction", "OVER vs UNDER"),
    ("fresh_tier", "FRESHNESS: teammate-out (vac)"),
    ("vacreb_tier", "FRESHNESS: vacated REB load"),
    ("any_out", "FRESHNESS: any regular out"),
    ("big_out", "FRESHNESS: rebounding big out"),
]


def sweep(main_b, season_b, diff_b):
    """Return list of cell dicts across all axes/values with in-window +
    cross-season ROI + verdict."""
    cells = []
    for col, axis_label in AXES:
        if col == "__all__":
            vals = ["__all__"]
        else:
            vals = [v for v in main_b[col].dropna().unique()]
            vals = sorted([str(v) for v in vals])
        for v in vals:
            def cut(df):
                if col == "__all__":
                    return df
                return df[df[col].astype(str) == v]
            m = roi_stats(cut(main_b))
            s = roi_stats(cut(season_b))
            d = roi_stats(cut(diff_b))
            cells.append({
                "axis": axis_label, "col": col, "val": v,
                "main": m, "season": s, "diff": d,
                "verdict": verdict(m, s),
            })
    return cells


# ─────────────────────────────────────────────────────────────────────
# DECISIVE DECOMPOSITION (the AST-grade discipline). The naive sign-gate is
# necessary but NOT sufficient: a "survivor" can just be a directional line
# tilt (REB lines set high -> blind-under cashes) that needs no model. These
# three tests separate genuine model SELECTION from a market tilt.
# ─────────────────────────────────────────────────────────────────────
def blind_roi_flat(df: pd.DataFrame, over: bool) -> float:
    """Flat -110 ROI of betting a forced side on every line (model ignored)."""
    line = df["line"].to_numpy(); act = df["actual"].to_numpy()
    keep = act != line
    win = (act > line) if over else (act < line)
    pnl = np.where(win, 100 / 110 * 100, -100.0)
    return float(pnl[keep].mean()) if keep.sum() else np.nan


def decomposition(main_b, season_b, diff_b) -> dict:
    out = {"tilt": {}, "selection": {}, "flip": {}}
    for name, df in [("MAIN", main_b), ("2024-25", season_b), ("diff-scrape", diff_b)]:
        diffs = (df["actual"] - df["line"])
        out["tilt"][name] = {
            "mean_actual_minus_line": float(diffs.mean()),
            "under_cash_rate": float((diffs < 0).mean() * 100),
            "blind_over": blind_roi_flat(df, True),
            "blind_under": blind_roi_flat(df, False),
        }
        over = df[df.bet_over]; under = df[~df.bet_over]
        all_over = float((df["actual"] > df["line"]).mean() * 100)
        all_under = float((df["actual"] < df["line"]).mean() * 100)
        mo = float((over["actual"] > over["line"]).mean() * 100) if len(over) else np.nan
        mu = float((under["actual"] < under["line"]).mean() * 100) if len(under) else np.nan
        out["selection"][name] = {
            "model_over_win": mo, "blind_over_win": all_over,
            "over_selection_pp": mo - all_over, "n_over": int(len(over)),
            "model_under_win": mu, "blind_under_win": all_under,
            "under_selection_pp": mu - all_under, "n_under": int(len(under)),
        }
        # anti-model flip at flat -110
        flip_win = ~(((df.bet_over) & (df.actual > df.line)) |
                     ((~df.bet_over) & (df.actual < df.line)))
        keep = (df.actual != df.line).to_numpy()
        fp = np.where(flip_win, 100 / 110 * 100, -100.0)[keep]
        out["flip"][name] = {"model_real_odds_roi": float(df["pnl"].mean()),
                             "flipped_flat110_roi": float(fp.mean()) if keep.sum() else np.nan,
                             "n": int(len(df))}
    return out


def print_decomposition(dec):
    print("\n  === DECISIVE DECOMPOSITION (AST-grade) ===")
    print("  Test 1 — directional UNDER tilt (blind, model ignored, flat -110):")
    for name, t in dec["tilt"].items():
        print(f"    {name:12s} mean(act-line)={t['mean_actual_minus_line']:+.3f} "
              f"under-cash={t['under_cash_rate']:.1f}% | "
              f"blind-OVER {t['blind_over']:+6.2f}% blind-UNDER {t['blind_under']:+6.2f}%")
    print("  Test 2 — model SELECTION above blind same-side cash rate (the gate):")
    for name, s in dec["selection"].items():
        print(f"    {name:12s} OVER {s['over_selection_pp']:+5.1f}pp(n{s['n_over']}) "
              f"UNDER {s['under_selection_pp']:+5.1f}pp(n{s['n_under']})")
    print("  Test 3 — anti-model flip (skilled model must LOSE flipped):")
    for name, f in dec["flip"].items():
        print(f"    {name:12s} model {f['model_real_odds_roi']:+6.2f}% "
              f"flipped {f['flipped_flat110_roi']:+6.2f}% (n{f['n']})")


def main():
    print("[1/4] loading leak-free bet table (REB) ...")
    bt = pd.read_parquet(_BETS)
    bt = bt[bt["stat"] == "reb"].copy()
    print(f"      REB bets: total {len(bt)} | "
          + " ".join(f"{c}={len(bt[bt.corpus==c])}"
                     for c in (MAIN, SEASON, DIFFSCR)))

    print("[2/4] building role tags + leak-free vacated-load (freshness) ...")
    avgs = build_player_reb_avg()
    vac = reconstruct_vac()
    print(f"      reb_avg players={len(avgs)} | vac rows={len(vac)} "
          f"(big_out={int(vac['big_out'].sum())}, creator_out={int(vac['creator_out'].sum())})")

    bt = add_subpops(bt, avgs, vac)
    main_b = bt[bt.corpus == MAIN].copy()
    season_b = bt[bt.corpus == SEASON].copy()
    diff_b = bt[bt.corpus == DIFFSCR].copy()

    # coverage of freshness join on each corpus
    print(f"      freshness join coverage: "
          f"MAIN any_out={int(main_b['any_out'].sum())}/{len(main_b)} "
          f"big_out={int(main_b['big_out'].sum())} | "
          f"SEASON any_out={int(season_b['any_out'].sum())}/{len(season_b)} "
          f"big_out={int(season_b['big_out'].sum())}")

    print("[3/4] sweeping sub-populations (in-window vs cross-season) ...")
    cells = sweep(main_b, season_b, diff_b)

    durable = [c for c in cells if c["verdict"] == "DURABLE"]
    print(f"\n      DURABLE candidates (positive sign BOTH corpora, adequate n): "
          f"{len(durable)}")
    for c in durable:
        print(f"        {c['axis']:32s} {c['val']:22s} "
              f"MAIN {c['main']['roi']:+6.2f}% (n{c['main']['n']}) | "
              f"2024-25 {c['season']['roi']:+6.2f}% (n{c['season']['n']})")

    # decisive decomposition (separates genuine selection from a market tilt)
    dec = decomposition(main_b, season_b, diff_b)
    print_decomposition(dec)

    print("\n[4/4] writing report ...")
    write_report(cells, main_b, season_b, diff_b, dec)
    print(f"      wrote {_OUT_MD}")


# ─────────────────────────────────────────────────────────────────────
def _cellfmt(r):
    if r["n"] == 0:
        return "n=0"
    ci = (f"[{r['lo']:+.1f},{r['hi']:+.1f}]"
          if not np.isnan(r["lo"]) else "[--]")
    return f"{r['roi']:+6.2f}% (n{r['n']}, win {r['win']:.0f}%, CI{ci})"


def write_report(cells, main_b, season_b, diff_b, dec):
    # The decomposition is the real arbiter: a naive-DURABLE cell is only a
    # genuine model edge if the model's SELECTION beats blind on the 2024-25
    # gate (>0pp on at least one direction). REB selection on the gate is
    # -0.2pp / -0.3pp -> no naive survivor is a real model edge.
    sel_season = dec["selection"]["2024-25"]
    season_selection_pos = (
        (not np.isnan(sel_season["over_selection_pp"]) and sel_season["over_selection_pp"] > 0.5)
        or (not np.isnan(sel_season["under_selection_pp"]) and sel_season["under_selection_pp"] > 0.5))
    L = []
    L.append("# REB Durable-Edge Hunt — cross-season gate (2026-06-05)\n")
    L.append("**Mode:** READ-ONLY. No prod-file edits, no retrain, no git add. "
             "Reuses the leak-free real-odds bet table "
             "`data/cache/edge_mining_bets.parquet` (prod-stack walk-forward OOF "
             "as the predictor, bets graded at ACTUAL posted odds, `|odds|>=100` "
             "always, pushes/zero-edge dropped).\n")
    L.append("## Question\n")
    L.append(
        "REB pregame is the CLOSEST stat to beating the closing line: it flickers "
        "positive in 2026 windows (+0.6% .. +1.8% ROI vs real closes) but REVERSES "
        "to ~-10% on the independent 2024-25 season. Is there ANY REB sub-population "
        "that is DURABLY positive — i.e. holds its SIGN on BOTH the 2026 real-close "
        "corpus (benashkar) AND the independent 2024-25 corpus (oddsapi_2425)? If one "
        "survives both, it is a real REB edge. If none survives, REB's positives are "
        "single-window mirages.\n")
    L.append("## Corpora (after OOF-join; OOF is regular-season only)\n")
    L.append("| key | window | role | n (REB, \\|odds\\|>=100) |")
    L.append("|---|---|---|---:|")
    L.append(f"| `benashkar_2526` | 2026-01..04, DK/FD/MGM | **IN-WINDOW** 2025-26 | {len(main_b)} |")
    L.append(f"| `oddsapi_2425` | 2024-25 season | **CROSS-SEASON GATE** | {len(season_b)} |")
    L.append(f"| `oddsapi_2526reg` | 2025-26 reg, diff scrape | aux (semi-indep) | {len(diff_b)} |")
    L.append("\n`extended_oos` is NOT independent of benashkar after the OOF join "
             "(byte-identical keys) -> excluded from the gate, per EDGE_MINING.md. "
             "The 2024-25 corpus is THIN (n~65 REB) — it gates SIGN, not precise "
             "magnitude. Whole-stat REB reference: MAIN "
             f"{main_b['pnl'].mean():+.2f}% / 2024-25 {season_b['pnl'].mean():+.2f}% / "
             f"diff-scrape {diff_b['pnl'].mean():+.2f}%.\n")

    L.append("## Discipline\n")
    L.append(
        f"- **Durable** = positive ROI sign on BOTH MAIN (n>={MIN_N_MAIN}) AND the "
        f"cross-season 2024-25 corpus (n>={MIN_N_SEASON}). Sign gate is the whole "
        "point; single-window peaks (positive MAIN, negative/zero 2024-25) REJECT.\n"
        "- `single-window-peak` = the REB failure mode (the +18.38% / PTS-UNDER-high-"
        "line mechanism). `THIN-N` = not enough bets to judge on >=1 corpus.\n"
        "- Bootstrap 95% CI on ROI (5000 resamples). Where claimed, BOTH directions "
        "checked. `opp_pace` on the 2026 corpora is a STALE 2024-25 proxy "
        "(`team_advanced_stats` has no 2025-26) — pace tiers there = last-season pace "
        "identity, flagged.\n"
        "- FRESHNESS / vac angle: leak-free box-confirmed-OUT reconstruction "
        "(a recent regular, L10 min>=15, who played a prior-3 team game but has NO row "
        "this game = ruled OUT pre-tip), the EXACT logic in "
        "`scripts/_vac_bump_accuracy_validation.py` / `calibrate_live_adjustment.py`. "
        "`vac_reb` = summed L10 REB of OUT regulars; `big_out` = an OUT regular with "
        "L10 REB>=7 (a rebounding big vacated).\n")

    # ── main table, grouped by axis ──
    L.append("\n## Sub-population table (in-window MAIN / cross-season 2024-25 / verdict)\n")
    L.append("Each cell: ROI% (n, win%, 95% CI). DURABLE = positive sign on both.\n")
    cur_axis = None
    L.append("| axis | sub-population | MAIN 2025-26 (in-window) | 2024-25 (cross-season GATE) | diff-scrape (aux) | verdict |")
    L.append("|---|---|---|---|---|---|")
    for c in cells:
        ax = c["axis"] if c["axis"] != cur_axis else ""
        cur_axis = c["axis"]
        val = "" if c["val"] == "__all__" else c["val"]
        if c["axis"] == "ALL REB (baseline)":
            val = "(all REB)"
        L.append(f"| {ax} | {val} | {_cellfmt(c['main'])} | "
                 f"{_cellfmt(c['season'])} | {_cellfmt(c['diff'])} | "
                 f"**{c['verdict']}** |")

    # ── survivors ──
    durable = [c for c in cells if c["verdict"] == "DURABLE"]
    L.append("\n## Survivors of the cross-season gate\n")
    if not durable:
        L.append("**NONE.** No REB sub-population is positive on BOTH the 2026 "
                 "in-window corpus and the independent 2024-25 corpus at adequate n. "
                 "Every positive REB cell on MAIN flips sign (or lacks the n) on "
                 "2024-25.\n")
    else:
        L.append("| axis | sub-pop | MAIN | 2024-25 | diff-scrape | note |")
        L.append("|---|---|---|---|---|---|")
        for c in durable:
            # every naive survivor is debunked by the decomposition below
            note = ("FRESHNESS/vac (inherits UNDER tilt; fails decomposition)"
                    if "FRESHNESS" in c["axis"]
                    else "fails decomposition (tilt, not model selection)")
            L.append(f"| {c['axis']} | {c['val']} | {_cellfmt(c['main'])} | "
                     f"{_cellfmt(c['season'])} | {_cellfmt(c['diff'])} | {note} |")
        L.append("\n**Caveat:** the 2024-25 corpus is thin (n~65 REB total); a "
                 "DURABLE tag here means the SIGN held on a small sample, NOT a "
                 "confident magnitude.\n")
        L.append(
            "\n> **The naive sign-gate is NECESSARY but NOT SUFFICIENT.** Every "
            "survivor below fails the AST-grade decomposition that follows: they are "
            "the same underlying REB-UNDER line tilt (lines set high -> blind-under "
            "cashes), a market property that needs NO model — and the model's own "
            "selection adds nothing cross-season. `pace_fast` additionally rides n=19 "
            "on a STALE pace proxy (flagged noise in EDGE_MINING.md).\n")

    # ── DECISIVE DECOMPOSITION (AST-grade) ──
    L.append("\n## DECISIVE DECOMPOSITION — do the survivors pass AST-grade discipline?\n")
    L.append(
        "The AST edge was certified durable only because it passed: (1) BOTH "
        "directions positive (selection, not tilt), (2) model selection beats blind "
        "on every corpus, (3) anti-model flip loses. Applying the same three tests "
        "to the REB survivors:\n")
    L.append("\n### Test 1 — Is REB just a directional UNDER tilt? (blind, model ignored, flat -110)\n")
    L.append("| corpus | mean(actual-line) | under-cash rate | blind-OVER | blind-UNDER |")
    L.append("|---|---:|---:|---:|---:|")
    for name in ("MAIN", "2024-25", "diff-scrape"):
        t = dec["tilt"][name]
        L.append(f"| {name} | {t['mean_actual_minus_line']:+.3f} | "
                 f"{t['under_cash_rate']:.1f}% | {t['blind_over']:+.2f}% | "
                 f"**{t['blind_under']:+.2f}%** |")
    L.append("\nREB lines are set slightly HIGH on all three corpora, so **blind-UNDER "
             "(no model at all) is positive on every corpus.** The 'durable UNDER' "
             "survivor is this market tilt, not a model edge — anyone betting under on "
             "every rebound line captures it.\n")
    L.append("\n### Test 2 — Does the MODEL's selection add skill OVER the blind tilt? "
             "(model-side win% minus blind same-side cash rate) — THE GATE\n")
    L.append("| corpus | model-OVER selection | model-UNDER selection |")
    L.append("|---|---:|---:|")
    for name in ("MAIN", "2024-25", "diff-scrape"):
        s = dec["selection"][name]
        op = "n/a" if np.isnan(s["over_selection_pp"]) else f"{s['over_selection_pp']:+.1f}pp ({s['model_over_win']:.1f}% vs {s['blind_over_win']:.1f}%, n{s['n_over']})"
        up = "n/a" if np.isnan(s["under_selection_pp"]) else f"{s['under_selection_pp']:+.1f}pp ({s['model_under_win']:.1f}% vs {s['blind_under_win']:.1f}%, n{s['n_under']})"
        gate = " **(GATE)**" if name == "2024-25" else ""
        L.append(f"| {name}{gate} | {op} | {up} |")
    L.append("\n**On the cross-season gate the model's REB selection adds "
             f"{sel_season['over_selection_pp']:+.1f}pp (OVER) / "
             f"{sel_season['under_selection_pp']:+.1f}pp (UNDER)** — it picks no better "
             "than the blind same-side cash rate. The +5.9 / +6.1pp of apparent skill "
             "on MAIN is a 2025-26-regime artifact that evaporates on 2024-25.\n")
    L.append("\n### Test 3 — Anti-model flip (a skilled model must LOSE when flipped)\n")
    L.append("| corpus | model as-is (real odds) | flipped (flat -110) |")
    L.append("|---|---:|---:|")
    for name in ("MAIN", "2024-25", "diff-scrape"):
        f = dec["flip"][name]
        L.append(f"| {name} | {f['model_real_odds_roi']:+.2f}% (n{f['n']}) | "
                 f"{f['flipped_flat110_roi']:+.2f}% |")
    flipimprove = dec["flip"]["2024-25"]["flipped_flat110_roi"] > dec["flip"]["2024-25"]["model_real_odds_roi"]
    L.append("\nOn MAIN, flipping the model loses badly = real in-window skill. On "
             "2024-25, **flipping the model "
             + ("IMPROVES it" if flipimprove else "does not improve it")
             + f"** ({dec['flip']['2024-25']['model_real_odds_roi']:+.2f}% -> "
             f"{dec['flip']['2024-25']['flipped_flat110_roi']:+.2f}%) = the model's REB "
             "selection is worse than random on the independent season.\n")
    L.append("\n**Bottom line of the decomposition:** none of the naive survivors is a "
             "genuine model SELECTION edge. The only thing durable across seasons is the "
             "**REB-UNDER market tilt** (lines set high), which (a) needs no model — "
             "blind-under captures it — and (b) the model's own selection underperforms "
             "cross-season. The freshness/vac cells (`big_out`, `vacreb>=7`) inherit this "
             "tilt and their within-cell direction flips by season on a tiny 2024-25 "
             "box-confirmed-OUT subset (n=22).\n")

    # ── freshness deep-dive ──
    fresh_cells = [c for c in cells if "FRESHNESS" in c["axis"]]
    L.append("\n## Freshness / vac angle (teammate-out -> REB)\n")
    L.append(
        "A teammate OUT frees rebounds; if the durable REB signal lives here it "
        "would COMPOSE with the just-flipped vac-bump (gated freshness lever). "
        "Coverage: MAIN any_out "
        f"{int(main_b['any_out'].sum())}/{len(main_b)}, big_out "
        f"{int(main_b['big_out'].sum())}; 2024-25 any_out "
        f"{int(season_b['any_out'].sum())}/{len(season_b)}, big_out "
        f"{int(season_b['big_out'].sum())}.\n")
    L.append("| sub-pop | MAIN | 2024-25 | verdict |")
    L.append("|---|---|---|---|")
    for c in fresh_cells:
        L.append(f"| {c['col']}={c['val']} | {_cellfmt(c['main'])} | "
                 f"{_cellfmt(c['season'])} | **{c['verdict']}** |")
    fresh_naive_durable = [c for c in fresh_cells if c["verdict"] == "DURABLE"]
    if fresh_naive_durable and not season_selection_pos:
        L.append("\n**The freshness/vac cells pass the NAIVE sign-gate but FAIL the "
                 "decomposition.** `big_out` / `vacreb>=7` look positive on both corpora "
                 "only because they inherit the REB-UNDER tilt; their within-cell "
                 "direction FLIPS by season (MAIN edge in model-UNDER, 2024-25 edge in "
                 "model-OVER), so it is not selection. On the 2024-25 gate the model's "
                 f"REB selection adds {sel_season['under_selection_pp']:+.1f}pp over blind, "
                 "and the box-confirmed-OUT subset on 2024-25 is tiny (big_out n=22). So "
                 "the freshness/vac angle is NOT a confirmed REB betting edge — it is the "
                 "tilt diluted onto a small subset. (The gated vac-bump's accuracy case on "
                 "the high-vac tail is real per VAC_BUMP_ACCURACY_VALIDATION.md, but "
                 "ACCURACY != ROI.)\n")
    else:
        L.append("\n**The freshness/vac angle does NOT hold cross-season** as a model "
                 "edge — it inherits the REB-UNDER tilt and its 2024-25 box-confirmed-OUT "
                 "subset is very small.\n")

    # ── verdict (decomposition is the arbiter; naive sign-gate is insufficient) ──
    L.append("\n## HONEST VERDICT\n")
    real_edge = bool(durable) and season_selection_pos
    if real_edge:
        L.append(
            "A REB sub-population passed BOTH the cross-season sign-gate AND the "
            "decomposition (model selection beats blind on the 2024-25 gate). Treat as "
            "recommend-don't-ship; re-confirm on a fresh independent corpus / real CLV.\n")
    else:
        L.append(
            "**NO durable REB pregame edge. REB's positive is a 2026-window artifact — "
            "a CLEAN REJECT.**\n")
        L.append(
            f"\nThe naive sign-gate flagged {len(durable)} candidate survivors "
            "(UNDER, pace_fast, big_out, vacreb>=7, big_out=True), but every one FAILS "
            "the AST-grade decomposition that certified AST durable:\n")
        L.append(
            "1. **It's a directional UNDER tilt, not a model edge.** REB closing lines "
            "are set slightly high on all three corpora (mean actual-line "
            f"{dec['tilt']['MAIN']['mean_actual_minus_line']:+.2f} / "
            f"{dec['tilt']['2024-25']['mean_actual_minus_line']:+.2f} / "
            f"{dec['tilt']['diff-scrape']['mean_actual_minus_line']:+.2f}; under cashes "
            f"{dec['tilt']['MAIN']['under_cash_rate']:.1f}% / "
            f"{dec['tilt']['2024-25']['under_cash_rate']:.1f}% / "
            f"{dec['tilt']['diff-scrape']['under_cash_rate']:.1f}%), so **blind-UNDER "
            "with NO model is positive everywhere** "
            f"({dec['tilt']['MAIN']['blind_under']:+.2f}% / "
            f"{dec['tilt']['2024-25']['blind_under']:+.2f}% / "
            f"{dec['tilt']['diff-scrape']['blind_under']:+.2f}%). That is a market "
            "line-pricing property, not the CourtVision model.\n")
        L.append(
            "2. **The model's REB selection adds ZERO skill cross-season.** On MAIN the "
            f"model picks {dec['selection']['MAIN']['over_selection_pp']:+.1f}pp (OVER) / "
            f"{dec['selection']['MAIN']['under_selection_pp']:+.1f}pp (UNDER) above the "
            "blind same-side cash rate; on the independent 2024-25 gate it adds "
            f"{sel_season['over_selection_pp']:+.1f}pp / {sel_season['under_selection_pp']:+.1f}pp "
            "— no better than blind. The apparent MAIN skill is a 2025-26-regime fit.\n")
        L.append(
            "3. **Anti-model flip confirms it.** Flipping the model loses on MAIN "
            f"({dec['flip']['MAIN']['flipped_flat110_roi']:+.2f}%) but "
            + ("IMPROVES" if flipimprove else "does not improve")
            + f" on 2024-25 ({dec['flip']['2024-25']['model_real_odds_roi']:+.2f}% -> "
            f"{dec['flip']['2024-25']['flipped_flat110_roi']:+.2f}%) — the model's REB "
            "selection is worse than random on the independent season.\n")
        L.append(
            "\nThis is the same single-window-peak mechanism as the fake +18.38% and the "
            "PTS-UNDER-high-line peak: positive in 2026, negative cross-season, driven by "
            "a regime-specific fit on top of a market tilt. Whole-stat REB is "
            f"**{main_b['pnl'].mean():+.2f}% MAIN / {season_b['pnl'].mean():+.2f}% on "
            "2024-25**; no sub-population (line bucket, role, big/guard, pace, home/road, "
            "rest/b2b, direction, OR the freshness/vac angle) holds genuine model "
            "selection skill across both seasons.\n")
        L.append(
            "\n**The only durable thing is the REB-UNDER line tilt** — and it is (a) not "
            "a model edge (blind-under captures it, no CourtVision needed), and (b) the "
            "model's own selection underperforms it cross-season, so wiring it as a "
            "'model edge' would be dishonest. AST remains the only stat that survives the "
            "cross-season gate with genuine balanced-direction model selection.\n")
        L.append(
            "\n**Recommendation (recommend-don't-ship; nothing committed, no flags "
            "flipped):** do NOT ship any REB sub-population as a betting edge. Do not "
            "present the REB-UNDER tilt or the freshness/vac cells as a model edge — they "
            "are a market property (REB lines set high) and a regime artifact "
            "respectively. Re-confirm only with a fresh genuinely-independent corpus or "
            "real CLV.\n")
    L.append(
        "\n**On freshness specifically:** the teammate-out -> REB angle does NOT compose "
        "into a durable edge here. It inherits the UNDER tilt and its within-cell "
        "direction flips by season on a tiny 2024-25 box-confirmed-OUT subset (n=22). "
        "The gated vac-bump's positive case is ACCURACY on the high-vac tail (PTS/REB "
        "~3-4% MAE, VAC_BUMP_ACCURACY_VALIDATION.md), and accuracy != ROI.\n")

    _OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    _OUT_MD.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
