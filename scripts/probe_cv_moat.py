"""probe_cv_moat.py — honest assessment of the CV "moat" (READ-ONLY).

Question: are the broadcast-CV behavioral features (defender_distance, spacing,
fatigue, play_type, etc.) REAL, at usable SCALE, and do they add OUT-OF-SAMPLE
edge the sportsbook does not already price?

This script does NOT run the video pipeline, NOT touch models/serve/golive, and
NOT flip flags. It only reads existing CV feature data + the cached OOF corpus +
the historical odds lines, and reports:

  1. INVENTORY  — which CV features exist, on how many games / player-games with
                  REAL (non-null, non-zero) values, date range, coverage % of the
                  bettable corpus.
  2. OVERLAP    — how many pregame-OOF rows and historical-line rows fall on a
                  (player, date) for which the player has >=1 PRIOR CV game (the
                  model's actual last-N-before-cutoff recipe). This is the
                  testable N.
  3. SIGNAL     — leak-safe test: does the prior-CV feature vector explain the
                  OOF residual (actual - oof_pred) out-of-sample? If the 85-feature
                  model + market already price the behavior, residual corr ~ 0 and
                  an OLS of residual ~ CV features has ~0 held-out R^2.
  4. ROI        — grade the existing OOF predictions vs real closing lines on the
                  CV-covered subset (|odds| >= 100, temporal split) vs the
                  uncovered subset. Does the book-invisible signal change ROI?

Honest framing: if coverage is too thin to validate, say so and quantify the
games-needed + cost. No CV-edge claim without coverage + an OOS number.
"""
from __future__ import annotations

import glob
import json
import os
import sys
import unicodedata
from collections import defaultdict

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

OOF_PATH = os.path.join(PROJECT_DIR, "data", "cache", "pregame_oof.parquet")
LINES_2526 = os.path.join(
    PROJECT_DIR, "data", "external", "historical_lines", "regular_season_2025_26_oddsapi.csv")
LINES_2425 = os.path.join(
    PROJECT_DIR, "data", "external", "historical_lines", "regular_season_2024_25_oddsapi.csv")

KEY_BEHAVIORAL = [
    "avg_defender_distance", "avg_spacing", "avg_fatigue_proxy",
    "contested_shot_rate", "play_type_transition_pct", "play_type_isolation_pct",
    "play_type_drive_pct", "play_type_post_pct", "shot_zone_paint_pct",
    "shot_zone_3pt_pct", "possession_duration_avg", "shots_per_possession",
    "avg_closeout_speed", "avg_contest_arm_angle", "catch_shoot_pct",
    "avg_dribble_count", "second_chance_rate", "avg_shot_distance",
    "preshot_velocity_peak", "avg_shot_clock_at_shot",
]


# ──────────────────────────────────────────────────────────────────────────────
def _norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = s.strip().lower()
    for suf in (" jr.", " jr", " iii", " ii", " iv", " sr.", " sr"):
        if s.endswith(suf):
            s = s[: -len(suf)].strip()
    return s.replace(".", "").replace("'", "").replace("-", " ").strip()


def build_namemap():
    from nba_api.stats.static import players as _pl
    m = {}
    for p in _pl.get_players():
        m[_norm_name(p["full_name"])] = p["id"]
    return m


def build_gid_date():
    gd = {}
    for p in glob.glob(os.path.join(PROJECT_DIR, "data", "nba", "season_games_*.json")):
        try:
            sg = json.load(open(p, encoding="utf-8"))
            rows = sg.get("rows", sg) if isinstance(sg, dict) else sg
            for g in rows or []:
                gid = str(g.get("game_id", "")).zfill(10)
                d = str(g.get("game_date", ""))[:10]
                if gid and d:
                    gd[gid] = d
        except Exception:
            pass
    return gd


def load_cv_long():
    """Return (long_df, player->sorted[(date, gid)] dict). long_df: player_id,
    game_id, game_date, feature_name, feature_value."""
    from src.data.db import get_connection
    gid_date = build_gid_date()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT player_id, game_id, feature_name, feature_value FROM cv_features")
    recs = []
    for pid, gid, fn, fv in cur.fetchall():
        gid = str(gid).zfill(10)
        d = gid_date.get(gid)
        recs.append((int(pid), gid, d, str(fn), float(fv) if fv is not None else np.nan))
    conn.close()
    df = pd.DataFrame(recs, columns=["player_id", "game_id", "game_date",
                                     "feature_name", "feature_value"])
    pl_games = defaultdict(list)
    for (pid, gid), grp in df.groupby(["player_id", "game_id"]):
        d = grp["game_date"].iloc[0]
        if d:
            pl_games[pid].append((d, gid))
    for pid in pl_games:
        pl_games[pid] = sorted(set(pl_games[pid]))
    return df, pl_games


# ──────────────────────────────────────────────────────────────────────────────
def main():
    out = {}
    print("=" * 70)
    print("CV MOAT PROBE — read-only")
    print("=" * 70)

    cv_long, pl_games = load_cv_long()
    n_games = cv_long["game_id"].nunique()
    n_players = cv_long["player_id"].nunique()
    n_pg = cv_long.groupby(["player_id", "game_id"]).ngroups
    dmin = cv_long["game_date"].dropna().min()
    dmax = cv_long["game_date"].dropna().max()
    print(f"\n[1] INVENTORY (DB cv_features table)")
    print(f"    games={n_games}  players(real NBA ids)={n_players}  "
          f"player-games={n_pg}  rows={len(cv_long)}")
    print(f"    date range: {dmin} -> {dmax}")
    # season split
    season_pref = cv_long.groupby(cv_long["game_id"].str[:5])["game_id"].nunique()
    print(f"    games by season-prefix: {season_pref.to_dict()}")
    # per-feature non-null/non-zero player-game coverage
    print(f"\n    Key behavioral feature coverage (player-games with non-null / non-zero):")
    feat_cov = {}
    for f in KEY_BEHAVIORAL:
        sub = cv_long[cv_long["feature_name"] == f]
        present = sub["feature_value"].notna().sum()
        nonzero = int((sub["feature_value"].fillna(0) != 0).sum())
        feat_cov[f] = {"present": int(present), "nonzero": nonzero}
        print(f"      {f:28s} present={present:4d}  nonzero={nonzero:4d}")
    out["inventory"] = {
        "games": int(n_games), "players": int(n_players), "player_games": int(n_pg),
        "rows": int(len(cv_long)), "date_min": dmin, "date_max": dmax,
        "games_by_season": {k: int(v) for k, v in season_pref.items()},
        "feature_coverage": feat_cov,
    }

    # wide per (player, game)
    wide = cv_long.pivot_table(index=["player_id", "game_id", "game_date"],
                               columns="feature_name", values="feature_value",
                               aggfunc="mean")
    wide = wide.reset_index()
    feat_cols = [c for c in KEY_BEHAVIORAL if c in wide.columns]

    # ── OVERLAP with pregame OOF ────────────────────────────────────────────
    print(f"\n[2] OVERLAP with bettable corpora (model recipe: >=1 PRIOR CV game)")
    oof = pd.read_parquet(OOF_PATH)
    oof["game_id"] = oof["game_id"].astype(str).str.zfill(10)
    oof["player_id"] = oof["player_id"].astype(int)
    oof["game_date"] = oof["game_date"].astype(str).str[:10]

    def prior_count(pid, d):
        gs = pl_games.get(pid)
        if not gs:
            return 0
        return sum(1 for (gd, _) in gs if gd < d)

    # compute prior CV mean-vector per OOF row (only for covered rows, vectorized-ish)
    oof_keys = oof[["player_id", "game_date"]].drop_duplicates()
    oof_keys["n_prior_cv"] = [prior_count(p, d) for p, d in
                             zip(oof_keys["player_id"], oof_keys["game_date"])]
    covered_keys = oof_keys[oof_keys["n_prior_cv"] > 0].copy()
    oof = oof.merge(oof_keys, on=["player_id", "game_date"], how="left")
    oof["covered"] = oof["n_prior_cv"] > 0
    n_cov_rows = int(oof["covered"].sum())
    print(f"    OOF corpus: {len(oof)} rows, {oof['game_id'].nunique()} games, "
          f"{oof.groupby(['player_id','game_id']).ngroups} player-games")
    print(f"    OOF rows with >=1 PRIOR CV game: {n_cov_rows} "
          f"({100*n_cov_rows/len(oof):.2f}% of corpus)")
    print(f"    covered player-date keys: {len(covered_keys)} "
          f"(date range {oof.loc[oof['covered'],'game_date'].min()} -> "
          f"{oof.loc[oof['covered'],'game_date'].max()})")
    out["overlap_oof"] = {
        "oof_rows": int(len(oof)), "covered_rows": n_cov_rows,
        "covered_pct": round(100 * n_cov_rows / len(oof), 3),
        "covered_keys": int(len(covered_keys)),
    }

    # ── SIGNAL: does prior-CV explain OOF residual out-of-sample? ───────────
    print(f"\n[3] SIGNAL — leak-safe: prior-CV mean-vector vs OOF residual "
          f"(actual - oof_pred)")
    # Build prior-CV mean vector per covered (player, game_date).
    # For each covered key, average the player's prior wide rows (date < cutoff).
    wide_by_pid = {pid: g.sort_values("game_date")
                   for pid, g in wide.groupby("player_id")}

    def prior_vec(pid, d, last_n=5):
        g = wide_by_pid.get(pid)
        if g is None:
            return None
        pri = g[g["game_date"] < d]
        if pri.empty:
            return None
        pri = pri.tail(last_n)
        return pri[feat_cols].mean(numeric_only=True)

    sig_rows = {}
    for stat in ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]:
        sub = oof[(oof["stat"] == stat) & (oof["covered"])].copy()
        if len(sub) < 50:
            sig_rows[stat] = {"n": int(len(sub)), "note": "too few covered rows"}
            continue
        feats = []
        keep = []
        for i, r in sub.iterrows():
            v = prior_vec(r["player_id"], r["game_date"])
            if v is None or v.isna().all():
                continue
            feats.append(v.fillna(0.0).values)
            keep.append(i)
        if len(keep) < 50:
            sig_rows[stat] = {"n": int(len(keep)), "note": "too few with prior vec"}
            continue
        X = np.array(feats, dtype=float)
        sub2 = sub.loc[keep]
        resid = (sub2["actual"] - sub2["oof_pred"]).values
        # temporal split: first 70% train, last 30% test (by game_date order)
        order = np.argsort(sub2["game_date"].values, kind="stable")
        X, resid = X[order], resid[order]
        cut = int(0.7 * len(X))
        Xtr, Xte = X[:cut], X[cut:]
        ytr, yte = resid[:cut], resid[cut:]
        # standardize on train
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
        Xtr = (Xtr - mu) / sd
        Xte = (Xte - mu) / sd
        from sklearn.linear_model import Ridge
        m = Ridge(alpha=10.0).fit(Xtr, ytr)
        pred = m.predict(Xte)
        ss_res = float(((yte - pred) ** 2).sum())
        ss_tot = float(((yte - yte.mean()) ** 2).sum()) + 1e-12
        r2 = 1 - ss_res / ss_tot
        # corr of predicted residual-adjustment with true residual
        corr = float(np.corrcoef(pred, yte)[0, 1]) if len(yte) > 2 else float("nan")
        sig_rows[stat] = {"n_train": int(len(Xtr)), "n_test": int(len(Xte)),
                          "heldout_R2": round(r2, 4), "pred_corr": round(corr, 4)}
        print(f"    {stat}: n_test={len(Xte):4d}  heldout R^2={r2:+.4f}  "
              f"pred_corr={corr:+.4f}")
    out["signal_residual"] = sig_rows

    # ── ROI on CV-covered lines vs uncovered ────────────────────────────────
    print(f"\n[4] ROI vs real closes (|odds|>=100, temporal split) on CV-covered subset")
    roi = roi_test(oof, pl_games)
    out["roi"] = roi

    # write doc
    write_doc(out)
    print("\n[done] wrote docs/_audits/CV_MOAT_PROBE.md")
    with open(os.path.join(PROJECT_DIR, "data", "output", "cv_moat_probe.json"),
              "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)


def _odds_to_profit(odds):
    o = float(odds)
    if o >= 100:
        return o / 100.0
    if o <= -100:
        return 100.0 / abs(o)
    return None


def roi_test(oof, pl_games):
    """Grade existing OOF point predictions vs real closing lines, on the
    CV-covered subset vs uncovered. Bet OVER if oof_pred>line else UNDER, at the
    posted odds, |odds|>=100. Temporal split is implicit (lines are a held-out
    real-close corpus distinct from the OOF training)."""
    namemap = build_namemap()
    results = {}
    for tag, path in [("2025_26", LINES_2526), ("2024_25", LINES_2425)]:
        if not os.path.exists(path):
            continue
        try:
            ln = pd.read_csv(path)
        except Exception as e:
            results[tag] = {"error": str(e)}
            continue
        ln["pid"] = ln["player"].map(lambda x: namemap.get(_norm_name(x)))
        ln = ln.dropna(subset=["pid"]).copy()
        ln["pid"] = ln["pid"].astype(int)
        ln["date"] = ln["date"].astype(str).str[:10]
        ln["stat"] = ln["stat"].astype(str).str.lower()
        # join to OOF predictions on (pid, date, stat)
        oo = oof[["player_id", "game_date", "stat", "oof_pred", "actual"]].copy()
        oo = oo.rename(columns={"player_id": "pid", "game_date": "date"})
        merged = ln.merge(oo, on=["pid", "date", "stat"], how="inner")
        if merged.empty:
            results[tag] = {"matched": 0, "note": "no OOF<->lines join"}
            continue

        def n_prior(pid, d):
            gs = pl_games.get(int(pid))
            return sum(1 for (gd, _) in gs if gd < d) if gs else 0

        merged["n_prior_cv"] = [n_prior(p, d) for p, d in zip(merged["pid"], merged["date"])]
        merged["covered"] = merged["n_prior_cv"] > 0
        merged["line"] = pd.to_numeric(merged["closing_line"], errors="coerce")
        merged["actual_v"] = pd.to_numeric(merged["actual_value"], errors="coerce")
        merged["over_odds"] = pd.to_numeric(merged["over_odds"], errors="coerce")
        merged["under_odds"] = pd.to_numeric(merged["under_odds"], errors="coerce")
        merged = merged.dropna(subset=["line", "actual_v", "oof_pred"])

        def grade(sub):
            bets = []
            for _, r in sub.iterrows():
                side = "over" if r["oof_pred"] > r["line"] else "under"
                odds = r["over_odds"] if side == "over" else r["under_odds"]
                prof = _odds_to_profit(odds) if pd.notna(odds) else None
                if prof is None:  # |odds|<100 invalid -> drop (the §1 artifact trap)
                    continue
                if r["actual_v"] == r["line"]:
                    continue  # push
                won = (r["actual_v"] > r["line"]) if side == "over" else (r["actual_v"] < r["line"])
                bets.append(prof if won else -1.0)
            n = len(bets)
            if n == 0:
                return {"n": 0}
            roi = float(np.mean(bets))
            wins = int(sum(1 for b in bets if b > 0))
            return {"n": n, "roi_pct": round(100 * roi, 2), "hit_pct": round(100 * wins / n, 2)}

        results[tag] = {
            "matched": int(len(merged)),
            "covered_rows": int(merged["covered"].sum()),
            "ALL": grade(merged),
            "CV_COVERED": grade(merged[merged["covered"]]),
            "UNCOVERED": grade(merged[~merged["covered"]]),
        }
        r = results[tag]
        print(f"    [{tag}] lines<->OOF matched={r['matched']}  "
              f"CV-covered={r['covered_rows']}")
        print(f"        ALL        : {r['ALL']}")
        print(f"        CV_COVERED : {r['CV_COVERED']}")
        print(f"        UNCOVERED  : {r['UNCOVERED']}")
    return results


def write_doc(out):
    inv = out["inventory"]
    ov = out["overlap_oof"]
    p = os.path.join(PROJECT_DIR, "docs", "_audits", "CV_MOAT_PROBE.md")
    lines = []
    lines.append("# CV Moat Probe — is the broadcast-CV behavioral edge real, at scale, and out-of-sample?\n")
    lines.append("_Read-only probe. No models/serve/golive touched, no flags flipped, "
                 "video pipeline NOT run. Generated by `scripts/probe_cv_moat.py`._\n")
    lines.append("## 1. Inventory — DB `cv_features` table (the table the prop model actually reads)\n")
    lines.append(f"- **{inv['games']} games**, **{inv['players']} players** (real NBA ids), "
                 f"**{inv['player_games']} player-games**, {inv['rows']} feature rows.")
    lines.append(f"- Date range **{inv['date_min']} → {inv['date_max']}**. "
                 f"Games by season prefix: `{inv['games_by_season']}`.")
    lines.append("- Key behavioral feature coverage (player-games with non-null / non-zero value):\n")
    lines.append("| feature | present | non-zero |")
    lines.append("|---|---|---|")
    for f, c in inv["feature_coverage"].items():
        lines.append(f"| {f} | {c['present']} | {c['nonzero']} |")
    lines.append("")
    lines.append("## 2. Overlap with the bettable corpus (model's last-N-before-cutoff recipe)\n")
    lines.append(f"- Pregame OOF corpus: **{ov['oof_rows']} rows**. Rows where the player has "
                 f"**≥1 prior CV game**: **{ov['covered_rows']} ({ov['covered_pct']}%)**, "
                 f"{ov['covered_keys']} player-date keys.")
    lines.append("")
    lines.append("## 3. Signal — does prior-CV explain OOF residual out-of-sample?\n")
    lines.append("Leak-safe Ridge of (actual − oof_pred) on the prior-CV mean-vector, "
                 "70/30 temporal split. Positive held-out R² ⇒ CV carries residual signal the "
                 "85-feature model does not already capture.\n")
    lines.append("| stat | n_test | held-out R² | pred_corr |")
    lines.append("|---|---|---|---|")
    for s, r in out["signal_residual"].items():
        if "heldout_R2" in r:
            lines.append(f"| {s} | {r['n_test']} | {r['heldout_R2']:+.4f} | {r['pred_corr']:+.4f} |")
        else:
            lines.append(f"| {s} | — | {r.get('note','')} | |")
    lines.append("")
    lines.append("## 4. ROI vs real closes on the CV-covered subset (|odds|≥100)\n")
    for tag, r in out["roi"].items():
        if "ALL" not in r:
            lines.append(f"- **{tag}**: {r}")
            continue
        lines.append(f"### {tag} (lines↔OOF matched={r['matched']}, CV-covered={r['covered_rows']})\n")
        lines.append("| subset | n bets | ROI % | hit % |")
        lines.append("|---|---|---|---|")
        for k in ["ALL", "CV_COVERED", "UNCOVERED"]:
            g = r[k]
            if g.get("n", 0):
                lines.append(f"| {k} | {g['n']} | {g['roi_pct']:+.2f} | {g['hit_pct']:.2f} |")
            else:
                lines.append(f"| {k} | 0 | — | — |")
        lines.append("")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
