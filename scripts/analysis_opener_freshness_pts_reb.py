"""analysis_opener_freshness_pts_reb.py  (NEW, read-only analysis — touches no prod files)

MISSION: Is model-vs-OPENER positive for PTS/REB (the freshness/CLV lever), and does
applying the FRESH availability vac-bump before grading move it? Brutally honest, leak-free,
no in-sample threshold tuning, no model retrain.

WHAT THIS DOES
--------------
1. Builds the opener (and where available close) bet corpus for PTS and REB *separately*,
   reusing the proven join + settle logic from scripts/measure_opener_vs_close.py
   (pregame.json model preds x timestamped lines x gamelog actuals), but ALSO grading
   opener-only games (e.g. 316) so no PTS/REB bet is dropped for lack of a close.
2. For PTS and REB separately: ROI@opener, ROI@close (same bets), CLV (line-points and
   beat_close%), and a bootstrap CI on opener ROI.
3. Re-grades after applying the FRESH vac-bump (src.prediction.live_adjustment.adjust_projection
   with the same gating the freshly-flipped flags use: vac_min_share + vac_stats={pts,reb}),
   computed leak-free from that date's confirmed-OUT injury feed.

LEAK-FREE: model preds = the deployed pregame.json (computed pre-tip, never sees the line or
the box score). vac_share uses only that date's confirmed-inactives feed + pre-date gamelogs
(availability.py is leak-safe by construction). No thresholds are fit on the outcomes.
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# Reuse the proven, audited helpers from the existing harness.
from scripts.measure_opener_vs_close import (  # noqa: E402
    _normalize_name, settle_bet, clv_points, _load_id_name_map,
    load_pregame_preds, load_actuals, load_snapshot_lines,
    load_raw_lines_for_game, _read_lines_csv, GRADEABLE_STATS, LINES_DIR,
)
from src.prediction import availability as _availability  # noqa: E402
from src.prediction import live_adjustment as _live_adjust  # noqa: E402

STATS = ["pts", "reb"]
RNG = np.random.default_rng(20260605)


def _boot_ci(rois, n_boot=10000, alpha=0.05):
    """Bootstrap CI on mean ROI. rois = list of per-bet roi floats."""
    a = np.asarray([r for r in rois if r is not None], dtype=float)
    if len(a) == 0:
        return (float("nan"), float("nan"), float("nan"))
    means = a[RNG.integers(0, len(a), size=(n_boot, len(a)))].mean(axis=1)
    return (float(a.mean()), float(np.quantile(means, alpha / 2)),
            float(np.quantile(means, 1 - alpha / 2)))


def _date_for_gid(gid: str) -> str:
    """Slate date (game date) for known playoff gids. Used only to locate the injury feed."""
    return {"0042500315": "2026-05-26", "0042500316": "2026-05-28"}.get(gid, "")


def _resolve_pid_factory(name_to_id):
    def _resolve(nm):
        return name_to_id.get(_normalize_name(nm))
    return _resolve


def _vac_share_for_player(pid, player_name, gid, name_to_id, vac_cache):
    """Leak-free vac_share for one player on the game's date (confirmed-OUT feed only)."""
    date = _date_for_gid(gid)
    if not date:
        return 0.0
    if date not in vac_cache:
        # Enable the parquet fallback so the scraper-written nba_injuries_<date>.parquet
        # is read when injuries_<date>.json is absent (mirrors the freshly-flipped flag).
        os.environ["CV_AVAIL_PARQUET_FALLBACK"] = "1"
        try:
            vac_cache[date] = _availability.team_vacated_map(
                date, _resolve_pid_factory(name_to_id), season="2025-26")
        except Exception as exc:
            print(f"  [vac] {date}: feed unavailable ({exc})")
            vac_cache[date] = {}
    vac_map = vac_cache[date]
    team = _availability.player_team(int(pid), "2025-26")
    # player's own L10 pts for the share denominator
    l10m, l10p = _availability._l10_min_pts(int(pid), "2025-26", date)
    rec = _availability.player_vacated(l10p, team, vac_map)
    return float(rec.get("vac_share", 0.0)), rec.get("n_out", 0), team


def build_corpus():
    """Return long DataFrame of PTS/REB bets across all (pregame, lines, actuals) games,
    including opener-only games. Columns include vac_share + bumped preds."""
    id_to_name = _load_id_name_map()
    name_to_id = {_normalize_name(v): k for k, v in id_to_name.items()}
    preds = load_pregame_preds()
    actuals = load_actuals()

    rows = []
    vac_cache = {}
    for gid, player_preds in preds.items():
        gid_act = actuals[actuals["game_id"] == gid]
        if len(gid_act) == 0:
            print(f"  [skip] {gid}: no actuals")
            continue
        act_lookup = {}
        for _, r in gid_act.iterrows():
            act_lookup[_normalize_name(r["player_name"])] = {s: float(r[s]) for s in GRADEABLE_STATS}

        # line source: snapshot (opener->close) preferred; else raw csv (opener only)
        snap = load_snapshot_lines(gid)
        line_df, src, game_start = None, None, None
        if snap is not None:
            st = pd.to_datetime(snap.get("start_time"), utc=True, errors="coerce").dropna()
            game_start = st.iloc[0].to_pydatetime() if len(st) else None
            snap_names = set(snap["player_name_norm"].unique())
            pred_names = {_normalize_name(id_to_name.get(pid, "")): pid for pid in player_preds}
            if len(set(pred_names) & snap_names) >= 3:
                line_df, src = snap, "snapshot"
        if line_df is None:
            # raw csv fallback (opener-only) — find files whose start_time matches this game.
            raw = _find_raw_lines_for_gid(gid)
            if raw is not None:
                line_df, src = raw, "raw_csv"
                st = pd.to_datetime(raw.get("start_time"), utc=True, errors="coerce").dropna()
                game_start = st.iloc[0].to_pydatetime() if len(st) else None
        if line_df is None:
            print(f"  [skip] {gid}: no usable line file")
            continue

        for pid, stat_vals in player_preds.items():
            pname = id_to_name.get(pid)
            if not pname:
                continue
            pnorm = _normalize_name(pname)
            if pnorm not in act_lookup:
                continue
            vac_share, n_out, team = _vac_share_for_player(pid, pname, gid, name_to_id, vac_cache)
            for stat in STATS:
                if stat not in stat_vals or stat not in act_lookup[pnorm]:
                    continue
                model_pred = float(stat_vals[stat])
                actual = act_lookup[pnorm][stat]
                oc = _extract_opener_close(line_df, pnorm, stat, game_start)
                if oc is None:
                    continue
                ol, oo, ou, cl, co, cu = oc
                bs_o, roi_o = settle_bet(model_pred, ol, oo, ou, actual)
                if bs_o is None:
                    continue
                roi_c = clv = beat = None
                if cl is not None:
                    bs_c, roi_c = settle_bet(model_pred, cl, co, cu, actual)
                    if bs_c is not None:
                        clv = clv_points(bs_o, ol, cl)
                        beat = clv > 0
                    else:
                        roi_c = None
                # FRESH vac-bump applied to the model pred BEFORE choosing the side.
                bumped = _live_adjust.adjust_projection(
                    {stat: model_pred}, vac_share=vac_share,
                    vac_min_share=0.0, vac_stats=frozenset({"pts", "reb"}))[stat]
                bs_ob, roi_ob = settle_bet(bumped, ol, oo, ou, actual)
                rows.append(dict(
                    gid=gid, player=pnorm, team=team, stat=stat, model_pred=model_pred,
                    bumped_pred=bumped, vac_share=round(vac_share, 4), n_out=n_out,
                    open_line=ol, close_line=cl, bet_side=bs_o, actual=actual,
                    roi_open=roi_o, roi_close=roi_c, clv_pts=clv, beat_close=beat,
                    bumped_bet_side=bs_ob, roi_open_bumped=roi_ob, src=src,
                ))
    return pd.DataFrame(rows)


def _find_raw_lines_for_gid(gid):
    """Best-effort raw-CSV opener loader for an opener-only game (316).
    316 = OKC@SAS G2, tip 2026-05-29 00:40 UTC. Its OPENER lines were captured 2026-05-27."""
    target_start_prefix = {"0042500316": "2026-05-29 00:"}.get(gid)
    if not target_start_prefix:
        return None
    dfs = []
    for f in sorted(LINES_DIR.glob("2026-05-27_*.csv")) + sorted(LINES_DIR.glob("2026-05-28_*.csv")):
        if "inplay" in f.name or "mainline" in f.name:
            continue
        df = _read_lines_csv(f)
        if df is None or "start_time" not in df.columns:
            continue
        st = pd.to_datetime(df["start_time"], utc=True, errors="coerce")
        m = st.dt.strftime("%Y-%m-%d %H:%M").fillna("").str.startswith("2026-05-29 00:")
        sub = df[m]
        if len(sub):
            dfs.append(sub)
    if not dfs:
        return None
    out = pd.concat(dfs, ignore_index=True)
    # keep ONLY pre-tip captures (opener); drop in-play
    ca = pd.to_datetime(out["captured_at"], utc=True, errors="coerce")
    tip = pd.Timestamp("2026-05-29 00:40", tz="UTC")
    return out[ca < tip].copy()


# A capture only counts as a real CLOSE if it lands within this many hours of tip.
# 316's "latest" capture is still ~31h pre-tip (a second opener read, not a close) —
# without this guard it would be mislabelled a close and pollute the close comparison.
_CLOSE_MAX_HOURS_BEFORE_TIP = 12.0


def _extract_opener_close(df, pnorm, stat, game_start):
    mask = (df["player_name_norm"] == pnorm) & (df["stat"] == stat)
    sub = df[mask].dropna(subset=["line", "over_price", "under_price"]).sort_values("captured_at")
    if len(sub) == 0:
        return None
    op = sub.iloc[0]
    cl_row = None
    if game_start is not None:
        gs = pd.Timestamp(game_start)
        if gs.tzinfo is None:
            gs = gs.tz_localize("UTC")
        pre = sub[pd.to_datetime(sub["captured_at"], utc=True) < gs]
        if len(pre):
            cand = pre.iloc[-1]
            hrs = (gs - pd.to_datetime(cand["captured_at"], utc=True)).total_seconds() / 3600.0
            if hrs <= _CLOSE_MAX_HOURS_BEFORE_TIP:
                cl_row = cand
    else:
        cl_row = sub.iloc[-1] if len(sub) > 1 else None
    has_close = cl_row is not None and cl_row["captured_at"] != op["captured_at"]
    return (float(op["line"]), float(op["over_price"]), float(op["under_price"]),
            float(cl_row["line"]) if has_close else None,
            float(cl_row["over_price"]) if has_close else None,
            float(cl_row["under_price"]) if has_close else None)


def report(df):
    print("\n" + "=" * 78)
    print("OPENER FRESHNESS GRADE — PTS / REB (model-vs-opener, leak-free)")
    print("=" * 78)
    print(f"games={df['gid'].nunique()}  total PTS/REB bets={len(df)}  "
          f"with-close={df['roi_close'].notna().sum()}  src={sorted(df['src'].unique())}")
    print(f"any non-zero vac_share? max={df['vac_share'].max():.3f}  "
          f"n_out>0 rows={int((df['n_out']>0).sum())}  "
          f"bumped!=base rows={int((df['bumped_pred']!=df['model_pred']).sum())}")

    hdr = (f"{'stat':<5}{'n':>4}{'open_ROI':>11}{'95% CI':>22}"
           f"{'close_ROI':>11}{'delta':>9}{'CLV_pts':>9}{'beat%':>7}{'hit%':>7}")
    print("\n" + hdr); print("-" * len(hdr))
    for stat in STATS + ["ALL"]:
        sub = df if stat == "ALL" else df[df["stat"] == stat]
        if len(sub) == 0:
            continue
        m, lo, hi = _boot_ci(sub["roi_open"].tolist())
        sc = sub[sub["roi_close"].notna()]
        croi = sc["roi_close"].mean() if len(sc) else float("nan")
        oroi_onclose = sc["roi_open"].mean() if len(sc) else float("nan")
        delta = (oroi_onclose - croi) if len(sc) else float("nan")
        clv = sc["clv_pts"].mean() if len(sc) else float("nan")
        beat = sc["beat_close"].mean() * 100 if len(sc) else float("nan")
        hit = (sub["roi_open"] > 0).mean() * 100
        print(f"{stat.upper():<5}{len(sub):>4}{m*100:>+10.1f}%"
              f"   [{lo*100:+6.1f}%,{hi*100:+6.1f}%]"
              f"{croi*100:>+10.1f}%{delta*100:>+8.1f}p{clv:>+9.2f}{beat:>6.0f}%{hit:>6.0f}%")

    # Freshness (vac-bump) effect
    print("\n--- FRESHNESS (vac-bump applied to model pred before grading) ---")
    hdr2 = f"{'stat':<5}{'n':>4}{'open_ROI_base':>15}{'open_ROI_bumped':>17}{'delta':>9}{'n_changed':>11}"
    print(hdr2); print("-" * len(hdr2))
    for stat in STATS + ["ALL"]:
        sub = df if stat == "ALL" else df[df["stat"] == stat]
        if len(sub) == 0:
            continue
        base = sub["roi_open"].mean() * 100
        bump = sub["roi_open_bumped"].mean() * 100
        nch = int((sub["bumped_pred"] != sub["model_pred"]).sum())
        print(f"{stat.upper():<5}{len(sub):>4}{base:>+14.1f}%{bump:>+16.1f}%{bump-base:>+8.1f}p{nch:>11}")

    print("\n--- per-game ---")
    for gid, g in df.groupby("gid"):
        gc = g[g["roi_close"].notna()]
        print(f"  {gid}: n={len(g)} open_ROI={g['roi_open'].mean()*100:+.1f}% "
              f"close_ROI={(gc['roi_close'].mean()*100 if len(gc) else float('nan')):+.1f}% "
              f"(n_close={len(gc)}) src={g['src'].iloc[0]}")


if __name__ == "__main__":
    df = build_corpus()
    if len(df) == 0:
        print("No PTS/REB bets graded.")
        sys.exit(0)
    report(df)
    out = REPO / "data" / "cache" / "opener_freshness_pts_reb.csv"
    df.to_csv(out, index=False)
    print(f"\nSaved {out}")
