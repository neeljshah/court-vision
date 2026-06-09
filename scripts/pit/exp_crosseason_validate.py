"""exp_crosseason_validate.py — DECISIVE cross-season / regime validation of the
two surviving prediction levers, on INDEPENDENT data, via leak-free rolling-origin
retraining where the cached pred substrate is missing.

THE TWO LEVERS (both currently 2025-26-PEAK):
  L1. vac_ast x gated-AST — size UP gated AST (edge>=0.75, line<=7.5) when a creator
      is confirmed OUT (vac_ast >= 3). Family A +15.6% directional; C n=9.
  L2. blowout starter-UNDER — model-UNDER & starter (asof L10 min>=28) & hi-blowout
      (|exp_margin| top-quartile). Family A +17.35% n=254 P=0.001; C n=3 (power-starved).

INDEPENDENT corpora delivered here (the substrate ends 2026-04-12, so playoff
corpora need rolling-origin retraining; the 2024 playoff corpora are NOT in
build_pergame_dataset and so are NOT gradeable — documented):
  * playoffs_2025_26_oddsapi.csv  — SAME season, PLAYOFF regime  (rolling-origin retrain)
  * regular_season_2024_25_oddsapi.csv — DIFFERENT season, reg regime (crosstime OOF)

PART A: rolling-origin leak-free preds (AST + PTS) for the 2025-26 playoff window.
PART B: re-grade BOTH levers on the now-joinable independent corpora (intel_grade
        discipline: drop |odds|<100, coherence guard, bootstrap CI). Regime caveats.
PART C: vac_ast as an AST MODEL FEATURE — rolling-origin retrain WITH vac_ast added,
        measure MAE + ROI vs the current (no-vac_ast) model.

DISJOINT WRITE: this file + scratch under scripts/_tmp_pred/ + the audit md + the
pred parquets under data/cache/pit/. No production code, no vault, no git commit.

Run (each phase is gated by a CLI subcommand so the heavy retrains can run detached):
  conda run -n basketball_ai python scripts/pit/exp_crosseason_validate.py genpreds
  conda run -n basketball_ai python scripts/pit/exp_crosseason_validate.py vacfeat
  conda run -n basketball_ai python scripts/pit/exp_crosseason_validate.py grade
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import unicodedata
import warnings
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "pit"))
import intel_grade as ig  # noqa: E402

OUT_DIR = ROOT / "data" / "cache" / "pit"
LINES = ROOT / "data" / "external" / "historical_lines"
NBA = ROOT / "data" / "nba"
CVFIX = ROOT / "data" / "cache" / "cv_fix"

EDGE_MIN, LINE_CAP = 0.75, 7.5     # the shipped gated-AST set
STARTER_MIN = 28.0
HCA = 2.5
VAC_AST_THR = 3.0                  # "creator confirmed out" gate
RNG = np.random.default_rng(20260601)


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", "", s.lower())).strip()


# ════════════════════════════════════════════════════════════════════════════
# PART A — leak-free rolling-origin preds for corpora the substrate misses
# ════════════════════════════════════════════════════════════════════════════
def _name_pid_map():
    from nba_api.stats.static import players as P
    nm = {}
    for p in P.get_players():
        nm.setdefault(norm(p["full_name"]), p["id"])
    return nm


def _load_corpus_df(corpus, stat):
    """Robust ragged-CSV load (csv module) -> filtered DataFrame for one stat."""
    import csv
    rows = []
    with open(LINES / corpus, encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh):
            if (r.get("stat") or "").strip().lower() != stat:
                continue
            try:
                line = float(r["closing_line"]); oo = float(r["over_odds"])
                uo = float(r["under_odds"]); act = float(r["actual_value"])
            except (TypeError, ValueError, KeyError):
                continue
            if abs(oo) < 100 or abs(uo) < 100:
                continue
            rows.append({"date": (r.get("date") or "").strip(), "player": (r.get("player") or "").strip(),
                         "closing_line": line, "over_odds": oo, "under_odds": uo, "actual_value": act})
    return pd.DataFrame(rows)


def gen_rolling_preds(corpus, stat, out_tag):
    """Mirror build_crosstime_oof: per-month rolling-origin, train strictly on the
    past, +/-1d actual-disambiguated match. Saves data/cache/pit/crosstime_oof_<stat>_<tag>.parquet."""
    from src.prediction.prop_pergame import build_pergame_dataset, feature_columns
    from scripts.cache_pergame_oof import _train_and_predict_stat

    nm = _name_pid_map()
    print(f"\n[genpreds] corpus={corpus} stat={stat} -> tag={out_tag}", flush=True)
    print("  building dataset ...", flush=True)
    rows, _ = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    fc = feature_columns(stat=stat)
    by_key = {(int(r.get("player_id", 0)), str(r["date"])[:10]): r for r in rows}
    dates_all = [str(r["date"])[:10] for r in rows]
    print(f"  dataset rows={len(rows)} features={len(fc)}", flush=True)

    df = _load_corpus_df(corpus, stat)
    df["pid"] = df["player"].map(lambda x: nm.get(norm(x)))
    df = df.dropna(subset=["pid"]); df["pid"] = df["pid"].astype(int)
    df["date2"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    print(f"  corpus {stat} rows after odds/name filter: {len(df)}", flush=True)

    recs = []
    for r in df.itertuples(index=False):
        cands = []
        for k in (-1, 0, 1):
            dd = (datetime.fromisoformat(r.date2) + timedelta(days=k)).strftime("%Y-%m-%d")
            dr = by_key.get((int(r.pid), dd))
            if dr is not None and abs(float(dr[f"target_{stat}"]) - float(r.actual_value)) < 0.5:
                cands.append((dd, dr))
        if not cands or len({c[0] for c in cands}) > 1:
            continue
        td, dr = cands[0]
        recs.append({"date": td, "pid": int(r.pid), "line": float(r.closing_line),
                     "over_odds": float(r.over_odds), "under_odds": float(r.under_odds),
                     "actual": float(r.actual_value), "row": dr})
    print(f"  matched to dataset rows: n={len(recs)}", flush=True)
    if not recs:
        print("  !! 0 matched (corpus window not in build_pergame_dataset) -> SKIP", flush=True)
        return None

    months = sorted({r["date"][:7] for r in recs})
    cut_for = {m: min(r["date"] for r in recs if r["date"][:7] == m) for m in months}
    for m in months:
        cutoff = cut_for[m]
        bucket = [r for r in recs if r["date"][:7] == m]
        tr_idx = [i for i, d in enumerate(dates_all) if d < cutoff]
        if len(tr_idx) < 2000:
            for r in bucket:
                r["pred"] = None
            continue
        n_tr = len(tr_idx); va = int(n_tr * 0.85)
        tr_rows = [rows[i] for i in tr_idx[:va]]; va_rows = [rows[i] for i in tr_idx[va:]]
        X_tr = np.array([[rr[c] for c in fc] for rr in tr_rows], float)
        X_val = np.array([[rr[c] for c in fc] for rr in va_rows], float)
        y_tr = np.array([rr[f"target_{stat}"] for rr in tr_rows], float)
        y_val = np.array([rr[f"target_{stat}"] for rr in va_rows], float)
        X_ho = np.array([[r["row"][c] for c in fc] for r in bucket], float)
        td = [datetime.fromisoformat(rr["date"][:10]) for rr in tr_rows]
        sw = np.exp(-0.5 * np.array([(max(td) - d).days / 365.0 for d in td]))
        preds = _train_and_predict_stat(stat, X_tr, y_tr, X_val, y_val, X_ho, sw)
        for r, p in zip(bucket, preds):
            r["pred"] = float(p)
        mae = np.mean([abs(r["pred"] - r["actual"]) for r in bucket if r.get("pred") is not None])
        print(f"    [{m}] train_n={n_tr} bucket_n={len(bucket)} ho_mae={mae:.3f}", flush=True)

    graded = [r for r in recs if r.get("pred") is not None]
    cond_keys = ["rest_days", "is_b2b", "is_home", "l10_min", "std_min"]
    out_rows = []
    for r in graded:
        d = {"date": r["date"], "pid": r["pid"], "stat": stat, "line": r["line"],
             "over_odds": r["over_odds"], "under_odds": r["under_odds"],
             "actual": r["actual"], "pred": r["pred"]}
        for k in cond_keys:
            d[k] = r["row"].get(k, np.nan)
        out_rows.append(d)
    outp = OUT_DIR / f"crosstime_oof_{stat}_{out_tag}.parquet"
    pd.DataFrame(out_rows).to_parquet(outp, index=False)
    print(f"  saved {len(out_rows)} graded rows -> {outp.name}", flush=True)
    return outp


def cmd_genpreds():
    # 2025-26 playoffs (same season, playoff regime) — AST + PTS
    gen_rolling_preds("playoffs_2025_26_oddsapi.csv", "ast", "playoffs_2025_26_oddsapi")
    gen_rolling_preds("playoffs_2025_26_oddsapi.csv", "pts", "playoffs_2025_26_oddsapi")
    # 2024-25 reg PTS (AST crosstime already exists) — for the blowout-PTS cross-season leg
    gen_rolling_preds("regular_season_2024_25_oddsapi.csv", "pts", "regular_season_2024_25_oddsapi")
    # 2024-25 reg AST already cached; regenerate only if missing
    if not (OUT_DIR / "crosstime_oof_ast_regular_season_2024_25_oddsapi.parquet").exists():
        gen_rolling_preds("regular_season_2024_25_oddsapi.csv", "ast", "regular_season_2024_25_oddsapi")
    # 2024 PLAYOFFS: documented blocker (not in build_pergame_dataset) — prove it
    gen_rolling_preds("playoffs_2024_canonical.csv", "ast", "playoffs_2024_canonical")


# ════════════════════════════════════════════════════════════════════════════
# LEAK-FREE SIGNAL BUILDERS (work on reg + playoff windows)
# ════════════════════════════════════════════════════════════════════════════
def _team_of(matchup):
    m = (matchup or "").strip()
    if " @ " in m:
        return m.split(" @ ")[0].strip().upper()
    if " vs. " in m:
        return m.split(" vs. ")[0].strip().upper()
    return None


def build_vac_ast_from_lglog(scope):
    """Leak-free vac_ast / vac_pts / n_out per (pid, date) from the league box log.
    scope='2025-26' pools reg+playoff parquets; '2024-25' uses per-player gamelog JSONs.
    For each (team,date): absent regulars = recent-roster (played >=1 of prev 3
    team-games, as-of L10 min>=15) NOT appearing -> sum their as-of L10 ast/pts.
    Returns {(pid,'YYYY-MM-DD'): {vac_ast, vac_pts, n_out}}. Every L10 is prior-only."""
    rows = []  # (date_ts, team, pid, ast, pts, minutes)
    if scope == "2025-26":
        frames = []
        for p in [CVFIX / "leaguegamelog_regular_season.parquet",
                  CVFIX / "leaguegamelog_playoffs.parquet"]:
            if p.exists():
                frames.append(pd.read_parquet(p))
        df = pd.concat(frames, ignore_index=True)
        for r in df.itertuples(index=False):
            d = pd.to_datetime(r.GAME_DATE, errors="coerce")
            if pd.isna(d):
                continue
            try:
                mn = float(r.MIN) if pd.notna(r.MIN) else None
            except (TypeError, ValueError):
                mn = None
            rows.append((d.normalize(), str(r.TEAM_ABBREVIATION).upper(), int(r.PLAYER_ID),
                         float(r.AST or 0), float(r.PTS or 0), mn))
    else:  # 2024-25: per-player gamelog JSONs
        for fp in glob.glob(str(NBA / "gamelog_*_2024-25.json")):
            m = re.match(r"gamelog_(\d+)_2024-25\.json$", os.path.basename(fp))
            if not m:
                continue
            pid = int(m.group(1))
            try:
                log = json.load(open(fp, encoding="utf-8"))
            except Exception:
                continue
            for g in log:
                d = pd.to_datetime(g.get("GAME_DATE"), errors="coerce")
                team = _team_of(g.get("MATCHUP"))
                if pd.isna(d) or team is None:
                    continue
                try:
                    mn = float(g.get("MIN")) if g.get("MIN") is not None else None
                except (TypeError, ValueError):
                    mn = None
                rows.append((d.normalize(), team, pid, float(g.get("AST") or 0),
                             float(g.get("PTS") or 0), mn))

    by_player = defaultdict(list)        # pid -> sorted [(date, ast, pts, min)]
    team_games = defaultdict(set)        # (team,date) -> pids who appeared (min>=1)
    team_dates = defaultdict(set)
    played_rows = defaultdict(list)      # (team,date) -> records that played
    for d, team, pid, ast, pts, mn in rows:
        by_player[pid].append((d, ast, pts, mn))
        if mn is not None and mn >= 1:
            team_games[(team, d)].add(pid)
            team_dates[team].add(d)
            played_rows[(team, d)].append((pid,))
    for pid in by_player:
        by_player[pid].sort()

    def asof_l10(pid, d):
        hist = [(a, p, mn) for (dd, a, p, mn) in by_player.get(pid, [])
                if dd < d and mn is not None and mn >= 1]
        if not hist:
            return 0.0, 0.0, 0.0
        h = hist[-10:]
        return (float(np.mean([x[0] for x in h])), float(np.mean([x[1] for x in h])),
                float(np.mean([x[2] for x in h])))

    out = {}
    for (team, d), appeared in team_games.items():
        tdates = sorted(team_dates[team])
        i = tdates.index(d)
        if i < 3:
            continue
        prior3 = tdates[max(0, i - 3):i]
        roster = set()
        for pd_ in prior3:
            roster |= team_games[(team, pd_)]
        vac_ast = vac_pts = 0.0; n_out = 0
        for pid in roster:
            if pid in appeared:
                continue
            la, lp, lm = asof_l10(pid, d)
            if lm >= 15:
                vac_ast += la; vac_pts += lp; n_out += 1
        ds = d.date().isoformat()
        for pid in appeared:
            out[(pid, ds)] = {"vac_ast": vac_ast, "vac_pts": vac_pts, "n_out": float(n_out)}
    return out


def _build_asof_srs(scope):
    """Leak-free as-of team SRS for blowout |exp_margin|.
    scope='2025-26': realized-margin SRS pooled over reg+playoff leaguegamelog
       (strictly prior games). Also returns pid->{date->team} from the same log.
    scope='2024-25': season_games_2024-25 as-of srs + schedule team-inference fn."""
    if scope == "2025-26":
        frames = []
        for p in [CVFIX / "leaguegamelog_regular_season.parquet",
                  CVFIX / "leaguegamelog_playoffs.parquet"]:
            if p.exists():
                frames.append(pd.read_parquet(p))
        df = pd.concat(frames, ignore_index=True)
        df["d"] = pd.to_datetime(df["GAME_DATE"]).dt.normalize()
        tg = df.groupby(["GAME_ID", "d", "TEAM_ABBREVIATION"], as_index=False)["PTS"].sum()
        g = tg.merge(tg, on="GAME_ID", suffixes=("", "_opp"))
        g = g[g["TEAM_ABBREVIATION"] != g["TEAM_ABBREVIATION_opp"]].copy()
        g["margin"] = g["PTS"] - g["PTS_opp"]
        g = g.sort_values(["d", "GAME_ID"]).reset_index(drop=True)
        games = list(g.itertuples(index=False))
        team_hist = defaultdict(list); asof_mov = {}
        for r in games:
            prior = team_hist[r.TEAM_ABBREVIATION]
            asof_mov[(r.GAME_ID, r.TEAM_ABBREVIATION)] = float(np.mean(prior)) if prior else 0.0
            team_hist[r.TEAM_ABBREVIATION].append(r.margin)
        opp_hist = defaultdict(list); asof_sos = {}
        for r in games:
            prior = opp_hist[r.TEAM_ABBREVIATION]
            asof_sos[(r.GAME_ID, r.TEAM_ABBREVIATION)] = float(np.mean(prior)) if prior else 0.0
            opp_hist[r.TEAM_ABBREVIATION].append(asof_mov.get((r.GAME_ID, r.TEAM_ABBREVIATION_opp), 0.0))
        team_date = defaultdict(list)
        for r in games:
            srs = asof_mov[(r.GAME_ID, r.TEAM_ABBREVIATION)] + 0.5 * asof_sos[(r.GAME_ID, r.TEAM_ABBREVIATION)]
            team_date[r.TEAM_ABBREVIATION].append((r.d, srs))
        for t in team_date:
            team_date[t].sort()

        def asof_srs(team, date):
            arr = team_date.get(team)
            if not arr:
                return None
            val = None
            for dd, s in arr:
                if dd < date:
                    val = s
                else:
                    break
            return val

        pid_team_date = defaultdict(dict)
        for r in df.itertuples(index=False):
            pid_team_date[int(r.PLAYER_ID)][pd.Timestamp(r.d).normalize()] = str(r.TEAM_ABBREVIATION).upper()
        return asof_srs, pid_team_date, None
    else:
        rows = json.load(open(NBA / "season_games_2024-25.json", encoding="utf-8"))["rows"]
        team_date = defaultdict(list); games_by_date = defaultdict(list)
        for r in rows:
            if "home_team" not in r or "home_srs" not in r:
                continue
            d = pd.Timestamp(r["game_date"]).normalize()
            team_date[r["home_team"]].append((d, float(r["home_srs"])))
            team_date[r["away_team"]].append((d, float(r["away_srs"])))
            games_by_date[d].append((r["home_team"], r["away_team"]))
        for t in team_date:
            team_date[t].sort()

        def asof_srs(team, date):
            arr = team_date.get(team)
            if not arr:
                return None
            val = None
            for dd, s in arr:
                if dd <= date:
                    val = s
                if dd > date:
                    break
            return val

        def player_team(opp, venue, date):
            for h, a in games_by_date.get(date, []):
                if h == opp:
                    return a
                if a == opp:
                    return h
            return None
        return asof_srs, None, player_team


# ════════════════════════════════════════════════════════════════════════════
# Grading utilities (settle/ROI/coherence reused from intel_grade)
# ════════════════════════════════════════════════════════════════════════════
def _payout(odds, win):
    if not win:
        return -100.0
    return (100.0 / abs(odds) * 100.0) if odds < 0 else (odds / 100.0 * 100.0)


def _bet_pnl(b, predictor="pred"):
    """Return per-bet pnl (settle semantics: dir=pred>line; push->None)."""
    pred = b.get(predictor)
    if pred is None or (isinstance(pred, float) and np.isnan(pred)):
        return None
    line = b["line"]; actual = b["actual"]
    if abs(pred - line) < 1e-9 or abs(actual - line) < 1e-9:
        return None
    bet_over = pred > line
    won = (bet_over and actual > line) or (not bet_over and actual < line)
    odds = b["over_odds"] if bet_over else b["under_odds"]
    return _payout(odds, won), bool(won)


def roi_list(bets, predictor="pred", under_only=False):
    pnls = []
    for b in bets:
        pred = b.get(predictor)
        if pred is None or (isinstance(pred, float) and np.isnan(pred)):
            continue
        if under_only and not (pred < b["line"]):
            continue
        r = _bet_pnl(b, predictor)
        if r is None:
            continue
        pnls.append(r[0])
    if not pnls:
        return {"n": 0, "roi_pct": 0.0, "win_pct": 0.0, "pnls": []}
    pnls = np.array(pnls, float)
    return {"n": len(pnls), "roi_pct": float(pnls.mean()),
            "win_pct": float(100 * (pnls > 0).mean()), "pnls": pnls}


def boot_ci(pnls, n_boot=5000, lo=5, hi=95):
    if len(pnls) < 5:
        return (np.nan, np.nan, np.nan)
    pnls = np.asarray(pnls, float)
    means = np.array([RNG.choice(pnls, len(pnls), replace=True).mean() for _ in range(n_boot)])
    p_le0 = float((means <= 0).mean())
    return (float(np.percentile(means, lo)), float(np.percentile(means, hi)), p_le0)


def coherence_pnl(bets):
    """blind-over + blind-under ROI sum; must be negative (coherent market)."""
    def blind(side):
        ps = []
        for b in bets:
            if abs(b["actual"] - b["line"]) < 1e-9:
                continue
            over = side == "over"
            won = (over and b["actual"] > b["line"]) or (not over and b["actual"] < b["line"])
            odds = b["over_odds"] if over else b["under_odds"]
            ps.append(_payout(odds, won))
        return float(np.mean(ps)) if ps else 0.0
    o, u = blind("over"), blind("under")
    return o, u, o + u


# ════════════════════════════════════════════════════════════════════════════
# Load a pred parquet into bet dicts (+ corpus odds already inside the parquet)
# ════════════════════════════════════════════════════════════════════════════
def bets_from_parquet(tag, stat):
    p = OUT_DIR / f"crosstime_oof_{stat}_{tag}.parquet"
    if not p.exists():
        return []
    df = pd.read_parquet(p)
    bets = []
    for r in df.itertuples(index=False):
        bets.append({"pid": int(r.pid), "stat": stat,
                     "gdate": pd.Timestamp(r.date).normalize(),
                     "line": float(r.line), "over_odds": float(r.over_odds),
                     "under_odds": float(r.under_odds), "actual": float(r.actual),
                     "pred": float(r.pred),
                     "l10_min": float(getattr(r, "l10_min", np.nan)),
                     "is_home": float(getattr(r, "is_home", np.nan))})
    bets.sort(key=lambda b: b["gdate"])
    return bets


def bets_from_substrate(corpus, stat):
    """Reg-season corpora that DO join the cached substrate (Family A path)."""
    bets = ig.prepare(corpus)
    bets = [b for b in bets if b["stat"] == stat]
    return bets


# ════════════════════════════════════════════════════════════════════════════
# LEVER 1 — vac_ast x gated-AST
# ════════════════════════════════════════════════════════════════════════════
def attach_vac(bets, scope):
    vac = build_vac_ast_from_lglog(scope)
    cov = 0
    for b in bets:
        ds = b["gdate"].date().isoformat()
        m = vac.get((b["pid"], ds))
        if m is not None:
            b.update(m); cov += 1
        else:
            b.setdefault("vac_ast", np.nan)
    return cov


def grade_lever1(label, bets, scope):
    """vac_ast x gated-AST. Reports: gated-AST base ROI+CI, and the vac_ast>=3 subset
    (size-up gate) ROI+CI, on this independent corpus."""
    print(f"\n  [LEVER 1: vac_ast x gated-AST]  {label}")
    cov = attach_vac(bets, scope)
    gated = [b for b in bets if abs(b["pred"] - b["line"]) >= EDGE_MIN and b["line"] <= LINE_CAP]
    base = roi_list(gated, "pred")
    bci = boot_ci(base["pnls"])
    print(f"    AST bets n={len(bets)}  vac coverage {cov}/{len(bets)}")
    print(f"    gated-AST BASE       n={base['n']:4d} ROI={base['roi_pct']:+7.2f}% win={base['win_pct']:.1f}% "
          f"CI[{bci[0]:+.1f},{bci[1]:+.1f}] P<=0={bci[2]:.3f}")
    sub = [b for b in gated if np.isfinite(b.get("vac_ast", np.nan)) and b["vac_ast"] >= VAC_AST_THR]
    rest = [b for b in gated if np.isfinite(b.get("vac_ast", np.nan)) and b["vac_ast"] < VAC_AST_THR]
    rs = roi_list(sub, "pred"); rr = roi_list(rest, "pred")
    sci = boot_ci(rs["pnls"])
    print(f"    gated-AST vac_ast>=3 n={rs['n']:4d} ROI={rs['roi_pct']:+7.2f}% win={rs['win_pct']:.1f}% "
          f"CI[{sci[0]:+.1f},{sci[1]:+.1f}] P<=0={sci[2]:.3f}")
    print(f"    gated-AST vac_ast<3  n={rr['n']:4d} ROI={rr['roi_pct']:+7.2f}% win={rr['win_pct']:.1f}%")
    # ungated AST (the durable-edge baseline) for context
    ung = roi_list(bets, "pred")
    print(f"    (context) ungated AST n={ung['n']} ROI={ung['roi_pct']:+.2f}%")
    return {"base": base, "vac_hi": rs, "vac_lo": rr, "base_ci": bci, "vac_ci": sci}


# ════════════════════════════════════════════════════════════════════════════
# LEVER 2 — blowout starter-UNDER
# ════════════════════════════════════════════════════════════════════════════
def attach_blowout(bets, asof_srs, pid_team_date=None, player_team_fn=None, corpus_for_opp=None):
    """Attach exp_margin/blowout/role. Needs opp+venue; pull from corpus if parquet-sourced."""
    # parquet-sourced bets lack opp/venue -> attach from the raw corpus by (pid,date)
    if corpus_for_opp is not None:
        opp_map = {}
        import csv
        n2p = ig.name_to_pid()
        with open(LINES / corpus_for_opp, encoding="utf-8", errors="replace") as fh:
            for r in csv.DictReader(fh):
                nm = (r.get("player") or "").strip().lower()
                pid = n2p.get(nm)
                gd = ig._parse_date(r.get("date"))
                if pid is None or gd is None:
                    continue
                opp_map[(pid, gd)] = ((r.get("opp") or "").strip().upper(),
                                      (r.get("venue") or "").strip())
        for b in bets:
            o = opp_map.get((b["pid"], b["gdate"]))
            if o:
                b["opp"], b["venue"] = o
    n = 0
    for b in bets:
        pt = None
        if pid_team_date is not None:
            pt = pid_team_date.get(b["pid"], {}).get(b["gdate"])
        if pt is None and player_team_fn is not None and b.get("opp"):
            pt = player_team_fn(b["opp"], b.get("venue", ""), b["gdate"])
        if pt is None or not b.get("opp"):
            continue
        s_team = asof_srs(pt, b["gdate"]); s_opp = asof_srs(b["opp"], b["gdate"])
        if s_team is None or s_opp is None:
            continue
        hca = HCA if b.get("is_home") == 1 else -HCA
        em = s_team - s_opp + hca
        b["_blowout"] = abs(em)
        l10 = b.get("l10_min", np.nan)
        b["_starter"] = 1 if (np.isfinite(l10) and l10 >= STARTER_MIN) else 0
        n += 1
    return n


def grade_lever2(label, bets_by_stat, asof_srs, *, pid_team_date=None, player_team_fn=None,
                 corpus_for_opp=None, thr_q=75):
    """blowout starter-UNDER per stat (esp PTS). model-UNDER & starter & hi-blowout."""
    print(f"\n  [LEVER 2: blowout starter-UNDER]  {label}")
    out = {}
    for stat, bets in bets_by_stat.items():
        nat = attach_blowout(bets, asof_srs, pid_team_date, player_team_fn, corpus_for_opp)
        starters = [b for b in bets if b.get("_starter") == 1 and np.isfinite(b.get("_blowout", np.nan))]
        if len(starters) < 10:
            print(f"    {stat}: starter-with-signal n={len(starters)} (<10) — power-starved, skip")
            out[stat] = None
            continue
        thr = np.nanpercentile([b["_blowout"] for b in starters], thr_q)
        # model-UNDER starter pool
        und_all = [b for b in starters if b["pred"] < b["line"]]
        und_hi = [b for b in und_all if b["_blowout"] >= thr]
        ra = roi_list(und_all, "pred"); rh = roi_list(und_hi, "pred")
        hci = boot_ci(rh["pnls"])
        print(f"    {stat}: signal-attached {nat}/{len(bets)} | starters n={len(starters)} thr(q{thr_q})={thr:.2f}")
        print(f"       model-UNDER-starter ALL   n={ra['n']:3d} ROI={ra['roi_pct']:+7.2f}% win={ra['win_pct']:.1f}%")
        print(f"       + hi-blowout filter       n={rh['n']:3d} ROI={rh['roi_pct']:+7.2f}% win={rh['win_pct']:.1f}% "
              f"CI[{hci[0]:+.1f},{hci[1]:+.1f}] P<=0={hci[2]:.3f}")
        out[stat] = {"all": ra, "hi": rh, "hi_ci": hci, "thr": float(thr)}
    return out


# ════════════════════════════════════════════════════════════════════════════
# PART B dispatch — grade both levers on independent corpora
# ════════════════════════════════════════════════════════════════════════════
def cmd_grade():
    print("=" * 78)
    print(" PART B — re-grade BOTH levers on INDEPENDENT corpora")
    print("=" * 78)

    # ---------- INDEPENDENT CORPUS 1: 2025-26 PLAYOFFS (same season, playoff regime) ----------
    print("\n" + "#" * 78)
    print("# CORPUS: playoffs_2025_26_oddsapi  (SAME season, PLAYOFF regime)")
    print("#   NOTE: AST documented to BREAK in playoffs; blowouts rarer/rotations tighter.")
    print("#" * 78)
    po_ast = bets_from_parquet("playoffs_2025_26_oddsapi", "ast")
    po_pts = bets_from_parquet("playoffs_2025_26_oddsapi", "pts")
    if po_ast:
        o, u, s = coherence_pnl(po_ast + po_pts)
        print(f"  coherence (ast+pts) blind-O {o:+.2f}% + blind-U {u:+.2f}% = {s:+.2f}% "
              f"({'OK' if s < 0 else 'CORRUPT'})")
        grade_lever1("playoffs_2025_26", po_ast, "2025-26")
        asof_srs, ptd, _ = _build_asof_srs("2025-26")
        grade_lever2("playoffs_2025_26", {"pts": po_pts, "ast": po_ast}, asof_srs,
                     pid_team_date=ptd, corpus_for_opp="playoffs_2025_26_oddsapi.csv")
    else:
        print("  !! no playoff AST preds parquet — run `genpreds` first")

    # ---------- INDEPENDENT CORPUS 2: 2024-25 REG (different season, reg regime) ----------
    print("\n" + "#" * 78)
    print("# CORPUS: regular_season_2024_25_oddsapi  (DIFFERENT season, reg regime)")
    print("#" * 78)
    rs_ast = bets_from_parquet("regular_season_2024_25_oddsapi", "ast")
    rs_pts = bets_from_parquet("regular_season_2024_25_oddsapi", "pts")
    if rs_ast:
        o, u, s = coherence_pnl(rs_ast + rs_pts)
        print(f"  coherence (ast+pts) blind-O {o:+.2f}% + blind-U {u:+.2f}% = {s:+.2f}% "
              f"({'OK' if s < 0 else 'CORRUPT'})")
        grade_lever1("reg_2024_25", rs_ast, "2024-25")
        asof_srs, _, ptf = _build_asof_srs("2024-25")
        grade_lever2("reg_2024_25", {"pts": rs_pts, "ast": rs_ast}, asof_srs,
                     player_team_fn=ptf, corpus_for_opp="regular_season_2024_25_oddsapi.csv")
    else:
        print("  !! no 2024-25 reg PTS preds — run `genpreds` first")

    # ---------- FAMILY A REFERENCE (2025-26 reg, the in-window PEAK) ----------
    print("\n" + "#" * 78)
    print("# REFERENCE: extended_oos (Family A, 2025-26 reg) — the in-window PEAK both levers were tuned on")
    print("#" * 78)
    fa_ast = bets_from_substrate("extended_oos_canonical.csv", "ast")
    fa_pts = bets_from_substrate("extended_oos_canonical.csv", "pts")
    grade_lever1("extended_oos(FamA)", fa_ast, "2025-26")
    asof_srs, ptd, _ = _build_asof_srs("2025-26")
    # Family A bets already have opp/venue from ig.prepare
    grade_lever2("extended_oos(FamA)", {"pts": fa_pts, "ast": fa_ast}, asof_srs,
                 pid_team_date=ptd, corpus_for_opp=None)


# ════════════════════════════════════════════════════════════════════════════
# PART C — vac_ast as an AST MODEL FEATURE (rolling-origin, leak-free)
# ════════════════════════════════════════════════════════════════════════════
def cmd_vacfeat():
    """Retrain AST WITH vac_ast appended as a feature, rolling-origin, leak-free.
    Compare held-out MAE + bet ROI vs the SAME stack WITHOUT vac_ast (apples-to-apples,
    same folds/seed). Graded on Family A reg-season held-out AST + the 2025-26 playoffs."""
    from src.prediction.prop_pergame import build_pergame_dataset, feature_columns
    from scripts.cache_pergame_oof import _train_and_predict_stat

    print("=" * 78)
    print(" PART C — vac_ast AS AN AST MODEL FEATURE (rolling-origin, leak-free)")
    print("=" * 78)
    print(" building dataset + leak-free vac_ast per (pid,date) ...", flush=True)
    rows, _ = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    fc = feature_columns(stat="ast")
    dates_all = [str(r["date"])[:10] for r in rows]

    # leak-free vac_ast keyed (pid, 'YYYY-MM-DD'), built from BOTH seasons' box logs
    vac = {}
    for scope in ("2025-26", "2024-25"):
        vac.update(build_vac_ast_from_lglog(scope))
    # also 2023-24 from per-player JSON if present (extends train coverage)
    def vac_of(pid, dstr):
        m = vac.get((int(pid), dstr))
        return float(m["vac_ast"]) if m else 0.0

    cov = sum(1 for r in rows if (int(r.get("player_id", 0)), str(r["date"])[:10]) in vac)
    print(f"  dataset rows={len(rows)}  vac_ast coverage on dataset rows={cov} ({100*cov/len(rows):.0f}%)", flush=True)

    # Feature matrices: base fc, and fc + vac_ast column
    def Xrow(r, with_vac):
        base = [r[c] for c in fc]
        if with_vac:
            base = base + [vac_of(r.get("player_id", 0), str(r["date"])[:10])]
        return base

    # ---- Build held-out evaluation sets ----
    # (1) Family A reg-season held-out AST bets (use the cached corpus to get lines/odds),
    #     predicted by rolling-origin so BOTH models see identical leak-free training.
    # (2) 2025-26 playoffs AST bets.
    nm = _name_pid_map()

    def corpus_targets(corpus, window_lo, window_hi):
        df = _load_corpus_df(corpus, "ast")
        df["pid"] = df["player"].map(lambda x: nm.get(norm(x)))
        df = df.dropna(subset=["pid"]); df["pid"] = df["pid"].astype(int)
        df["date2"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        by_key = {(int(r.get("player_id", 0)), str(r["date"])[:10]): r for r in rows}
        recs = []
        for r in df.itertuples(index=False):
            if not (window_lo <= r.date2 <= window_hi):
                continue
            cands = []
            for k in (-1, 0, 1):
                dd = (datetime.fromisoformat(r.date2) + timedelta(days=k)).strftime("%Y-%m-%d")
                dr = by_key.get((int(r.pid), dd))
                if dr is not None and abs(float(dr["target_ast"]) - float(r.actual_value)) < 0.5:
                    cands.append((dd, dr))
            if not cands or len({c[0] for c in cands}) > 1:
                continue
            td, dr = cands[0]
            recs.append({"date": td, "pid": int(r.pid), "line": float(r.closing_line),
                         "over_odds": float(r.over_odds), "under_odds": float(r.under_odds),
                         "actual": float(r.actual_value), "row": dr})
        return recs

    # benashkar window = 2026-01-28..05-11 (reg part joins; we restrict to <=2026-04-12)
    famA = corpus_targets("benashkar_2026_canonical.csv", "2026-01-28", "2026-04-12")
    po = corpus_targets("playoffs_2025_26_oddsapi.csv", "2026-04-20", "2026-05-31")
    print(f"  eval sets: Family-A reg AST n={len(famA)}  |  2025-26 playoff AST n={len(po)}", flush=True)

    def rolling_predict(recs, with_vac):
        months = sorted({r["date"][:7] for r in recs})
        cut_for = {m: min(r["date"] for r in recs if r["date"][:7] == m) for m in months}
        for m in months:
            cutoff = cut_for[m]
            bucket = [r for r in recs if r["date"][:7] == m]
            tr_idx = [i for i, d in enumerate(dates_all) if d < cutoff]
            if len(tr_idx) < 2000:
                for r in bucket:
                    r[f"pred_{int(with_vac)}"] = None
                continue
            n_tr = len(tr_idx); va = int(n_tr * 0.85)
            tr_rows = [rows[i] for i in tr_idx[:va]]; va_rows = [rows[i] for i in tr_idx[va:]]
            X_tr = np.array([Xrow(rr, with_vac) for rr in tr_rows], float)
            X_val = np.array([Xrow(rr, with_vac) for rr in va_rows], float)
            y_tr = np.array([rr["target_ast"] for rr in tr_rows], float)
            y_val = np.array([rr["target_ast"] for rr in va_rows], float)
            X_ho = np.array([Xrow(r["row"], with_vac) for r in bucket], float)
            td = [datetime.fromisoformat(rr["date"][:10]) for rr in tr_rows]
            sw = np.exp(-0.5 * np.array([(max(td) - d).days / 365.0 for d in td]))
            preds = _train_and_predict_stat("ast", X_tr, y_tr, X_val, y_val, X_ho, sw)
            for r, p in zip(bucket, preds):
                r[f"pred_{int(with_vac)}"] = float(p)

    for tag, recs in [("FamilyA-reg", famA), ("2025-26-playoffs", po)]:
        if not recs:
            print(f"\n  [{tag}] 0 eval rows — skip")
            continue
        print(f"\n  [{tag}] rolling-origin WITHOUT vac_ast ...", flush=True)
        rolling_predict(recs, False)
        print(f"  [{tag}] rolling-origin WITH vac_ast ...", flush=True)
        rolling_predict(recs, True)
        graded = [r for r in recs if r.get("pred_0") is not None and r.get("pred_1") is not None]
        if not graded:
            print(f"  [{tag}] no graded rows"); continue
        ae0 = np.array([abs(r["pred_0"] - r["actual"]) for r in graded], float)
        ae1 = np.array([abs(r["pred_1"] - r["actual"]) for r in graded], float)
        mae0 = float(ae0.mean()); mae1 = float(ae1.mean())
        # paired bootstrap on the per-row MAE improvement (mae0-mae1 > 0 => with-vac better)
        dmae = ae0 - ae1
        bm = np.array([RNG.choice(dmae, len(dmae), replace=True).mean() for _ in range(5000)])
        p_mae_better = float((bm > 0).mean())
        # persist per-row for any follow-up
        pd.DataFrame([{"date": r["date"], "pid": r["pid"], "line": r["line"], "actual": r["actual"],
                       "pred_novac": r["pred_0"], "pred_vac": r["pred_1"],
                       "over_odds": r["over_odds"], "under_odds": r["under_odds"]} for r in graded]
                     ).to_parquet(OUT_DIR / f"vacfeat_rows_{tag}.parquet", index=False)
        # ROI: build bet dicts
        def mk(r, key):
            return {"pred": r[key], "line": r["line"], "actual": r["actual"],
                    "over_odds": r["over_odds"], "under_odds": r["under_odds"]}
        b0 = [mk(r, "pred_0") for r in graded]; b1 = [mk(r, "pred_1") for r in graded]
        # gated subset (the bettable book)
        def gated(bs):
            return [b for b in bs if abs(b["pred"] - b["line"]) >= EDGE_MIN and b["line"] <= LINE_CAP]
        r0 = roi_list(b0, "pred"); r1 = roi_list(b1, "pred")
        g0 = roi_list(gated(b0), "pred"); g1 = roi_list(gated(b1), "pred")
        print(f"  [{tag}] n={len(graded)}")
        print(f"     MAE  no-vac={mae0:.4f}  with-vac={mae1:.4f}  delta={mae1-mae0:+.4f} "
              f"({'IMPROVES' if mae1 < mae0 - 1e-4 else 'no MAE gain'})  "
              f"P(with-vac better, paired boot)={p_mae_better:.3f}")
        print(f"     ungated ROI  no-vac={r0['roi_pct']:+.2f}%(n{r0['n']})  with-vac={r1['roi_pct']:+.2f}%(n{r1['n']})")
        print(f"     gated   ROI  no-vac={g0['roi_pct']:+.2f}%(n{g0['n']})  with-vac={g1['roi_pct']:+.2f}%(n{g1['n']})  "
              f"lift={g1['roi_pct']-g0['roi_pct']:+.2f}pp")
        # how often did the vac feature change the bet direction?
        flips = sum(1 for r in graded if (r["pred_0"] > r["line"]) != (r["pred_1"] > r["line"]))
        print(f"     direction flips from adding vac_ast: {flips}/{len(graded)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["genpreds", "grade", "vacfeat"])
    args = ap.parse_args()
    if args.cmd == "genpreds":
        cmd_genpreds()
    elif args.cmd == "grade":
        cmd_grade()
    elif args.cmd == "vacfeat":
        cmd_vacfeat()


if __name__ == "__main__":
    main()
