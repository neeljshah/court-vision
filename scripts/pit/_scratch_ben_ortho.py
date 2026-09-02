"""Beneficiary-specific vacated-load orthogonality screen (pre-screen, read-only).

Builds two strictly-as-of beneficiary-specific vacated-load signals from box logs
and tests whether either carries residual correlation BEYOND the team-total vac_pts
that calibration_frame_v2 already exposes (and the model lacks).

Definitions (all priors only => leak-free):
  Out-regulars per (team, date): roster = pids appearing (min>=1) in team's prior-3
  games; out = roster - appeared with as-of L10 min >= 15. (mirrors
  prop_pergame.build_vac_ast_lookup / validate_vac_load_feature.build_vac_load_lookup)

  team vac_min/vac_pts/n_out = sum of out-regulars' as-of L10 min/pts. (control)

  (a) MINUTES-SHARE weighted (usage-overlap proxy):
      ben_share = beneficiary's as-of L10 min / sum(as-of L10 min of appearing roster)
      ben_vac_min_share = ben_share * team_vac_min
      ben_vac_pts_share = ben_share * team_vac_pts
      Idea: a high-minute appearing player absorbs more of the vacated minutes/usage.

  (b) POSITION-matched:
      pos_vac_pts/min/n = sum over out-regulars whose coarse position bucket overlaps
      the beneficiary's (Guard/Forward/Center; hyphenated => both buckets).
      Idea: a guard benefits more when a guard sits.

We reconstruct OUR OWN team vac_pts from the same box pool (team_vac_pts) so the
beneficiary signals share a substrate; but the ORTHOGONALITY CONTROL uses the
frame's own vac_pts column (the exact thing the team-total retrain is testing), so
the verdict is "does ben add signal beyond the column the model would get".
"""
from __future__ import annotations
import glob, json, os, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

ROOT = Path(r"C:/Users/neelj/nba-ai-system")
CVFIX = ROOT / "data" / "cache" / "cv_fix"
NBA = ROOT / "data" / "nba"
CAL = ROOT / "data" / "cache" / "calibration_frame_v2.parquet"
PROFILE = ROOT / "data" / "cache" / "player_profile_features.parquet"


def _team_of_matchup(m):
    if not m:
        return None
    parts = str(m).split()
    return parts[0].upper() if parts else None


# ── position buckets (coarse) ──────────────────────────────────────────────────
def load_pos_buckets():
    df = pd.read_parquet(PROFILE)
    buck = {}
    for r in df.itertuples(index=False):
        pos = str(getattr(r, "position", "") or "")
        s = set()
        for token in pos.replace("-", " ").split():
            t = token.strip().lower()
            if t.startswith("guard"):
                s.add("G")
            elif t.startswith("forward"):
                s.add("F")
            elif t.startswith("center"):
                s.add("C")
        if s:
            buck[int(r.player_id)] = frozenset(s)
    return buck


# ── unified box pool: (date, team, pid, min, pts, reb, ast) ─────────────────────
def build_box_rows():
    rows = []
    # 2025-26 parquets (carry PLAYER_ID)
    for fn in ("leaguegamelog_regular_season.parquet", "leaguegamelog_playoffs.parquet"):
        p = CVFIX / fn
        if not p.is_file():
            continue
        df = pd.read_parquet(p)
        for r in df.itertuples(index=False):
            d = pd.to_datetime(getattr(r, "GAME_DATE", None), errors="coerce")
            if pd.isna(d):
                continue
            try:
                mn = float(r.MIN) if pd.notna(r.MIN) else None
            except (TypeError, ValueError):
                mn = None
            def fv(x):
                try:
                    return float(x or 0.0)
                except (TypeError, ValueError):
                    return 0.0
            rows.append((d.normalize(), str(r.TEAM_ABBREVIATION).upper(), int(r.PLAYER_ID),
                         mn, fv(r.PTS), fv(r.REB), fv(r.AST)))
    # per-player jsons (pid from filename); cover 2023-24, 2024-25, 2025-26
    for season in ("2023-24", "2024-25", "2025-26"):
        for fp in glob.glob(str(NBA / f"gamelog_*_{season}.json")):
            base = os.path.basename(fp)
            try:
                pid = int(base.split("_")[1])
            except (IndexError, ValueError):
                continue
            try:
                log = json.load(open(fp, encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(log, list):
                continue
            for g in log:
                d = pd.to_datetime(g.get("GAME_DATE"), errors="coerce")
                team = _team_of_matchup(g.get("MATCHUP"))
                if pd.isna(d) or team is None:
                    continue
                try:
                    mn = float(g.get("MIN")) if g.get("MIN") is not None else None
                except (TypeError, ValueError):
                    mn = None
                def gv(k):
                    try:
                        return float(g.get(k) or 0.0)
                    except (TypeError, ValueError):
                        return 0.0
                rows.append((d.normalize(), team, pid, mn, gv("PTS"), gv("REB"), gv("AST")))
    return rows


def build_signals():
    rows = build_box_rows()
    pos_buck = load_pos_buckets()
    print(f"box rows={len(rows)}  pos buckets={len(pos_buck)}", flush=True)

    by_player = defaultdict(list)     # pid -> [(date, min, pts, reb, ast)]
    team_games = defaultdict(set)     # (team,date) -> {pid appeared min>=1}
    team_dates = defaultdict(set)
    # dedup identical (date,team,pid) — parquet+json overlap on 2025-26
    seen = set()
    for d, team, pid, mn, pts, reb, ast in rows:
        key = (d, team, pid)
        if key in seen:
            continue
        seen.add(key)
        by_player[pid].append((d, mn, pts, reb, ast))
        if mn is not None and mn >= 1:
            team_games[(team, d)].add(pid)
            team_dates[team].add(d)
    for pid in by_player:
        by_player[pid].sort()

    def asof_l10(pid, d):
        hist = [(mn, pts) for (dd, mn, pts, rb, a) in by_player.get(pid, [])
                if dd < d and mn is not None and mn >= 1]
        if not hist:
            return 0.0, 0.0
        h = hist[-10:]
        return float(np.mean([x[0] for x in h])), float(np.mean([x[1] for x in h]))

    out = {}  # (pid, 'YYYY-MM-DD') -> signal dict
    for (team, d), appeared in team_games.items():
        tdates = sorted(team_dates[team])
        i = tdates.index(d)
        if i < 3:
            continue
        prior3 = tdates[max(0, i - 3):i]
        roster = set()
        for pdte in prior3:
            roster |= team_games[(team, pdte)]

        # out-regulars + their as-of L10 load and position bucket
        out_regs = []  # (pid, l10_min, l10_pts, posset)
        team_vac_min = team_vac_pts = 0.0
        n_out = 0
        for pid in roster:
            if pid in appeared:
                continue
            lm, lp = asof_l10(pid, d)
            if lm >= 15:
                team_vac_min += lm
                team_vac_pts += lp
                n_out += 1
                out_regs.append((pid, lm, lp, pos_buck.get(pid)))

        # appearing roster as-of L10 minute mass (share denominator)
        appear_min = {}
        tot_appear_min = 0.0
        for pid in appeared:
            lm, _ = asof_l10(pid, d)
            appear_min[pid] = lm
            tot_appear_min += lm

        ds = d.date().isoformat()
        for pid in appeared:
            share = (appear_min[pid] / tot_appear_min) if tot_appear_min > 1e-9 else 0.0
            ben_vac_min_share = share * team_vac_min
            ben_vac_pts_share = share * team_vac_pts
            # position-matched vac from out-regulars overlapping this player's bucket
            mine = pos_buck.get(pid)
            pos_vac_min = pos_vac_pts = 0.0
            pos_n_out = 0
            if mine:
                for (opid, olm, olp, oposs) in out_regs:
                    if oposs and (mine & oposs):
                        pos_vac_min += olm
                        pos_vac_pts += olp
                        pos_n_out += 1
            out[(int(pid), ds)] = {
                "team_vac_min": team_vac_min, "team_vac_pts": team_vac_pts, "team_n_out": float(n_out),
                "ben_share": share,
                "ben_vac_min_share": ben_vac_min_share, "ben_vac_pts_share": ben_vac_pts_share,
                "pos_vac_min": pos_vac_min, "pos_vac_pts": pos_vac_pts, "pos_n_out": float(pos_n_out),
                "has_pos": 1.0 if mine else 0.0,
            }
    return out


def partial_corr(x, z, r):
    """corr( resid_of(x~z), resid_of(r~z) ) — partial corr of x with r controlling z."""
    m = np.isfinite(x) & np.isfinite(z) & np.isfinite(r)
    x, z, r = x[m], z[m], r[m]
    if len(x) < 200 or np.std(x) < 1e-9:
        return np.nan, len(x)
    def resid(a, b):
        if np.std(b) < 1e-9:
            return a - a.mean()
        beta = np.cov(a, b, bias=True)[0, 1] / np.var(b)
        return a - (a.mean() + beta * (b - b.mean()))
    rx = resid(x, z)
    rr = resid(r, z)
    if np.std(rx) < 1e-9 or np.std(rr) < 1e-9:
        return np.nan, len(x)
    return float(np.corrcoef(rx, rr)[0, 1]), len(x)


def simple_corr(x, r):
    m = np.isfinite(x) & np.isfinite(r)
    if m.sum() < 200 or np.std(x[m]) < 1e-9:
        return np.nan, int(m.sum())
    return float(np.corrcoef(x[m], r[m])[0, 1]), int(m.sum())


def main():
    sig = build_signals()
    print(f"signal keys={len(sig)}", flush=True)

    cal = pd.read_parquet(CAL)
    cal["resid"] = cal["actual"] - cal["pred"]

    # attach beneficiary signals (default 0 where no out-regulars/no match)
    SIGCOLS = ["ben_vac_pts_share", "ben_vac_min_share", "ben_share",
               "pos_vac_pts", "pos_vac_min", "pos_n_out",
               "team_vac_pts", "team_vac_min", "team_n_out", "has_pos"]
    arrs = {c: np.zeros(len(cal)) for c in SIGCOLS}
    matched = 0
    pids = cal["player_id"].to_numpy()
    dates = cal["date"].astype(str).to_numpy()
    for idx in range(len(cal)):
        rec = sig.get((int(pids[idx]), dates[idx][:10]))
        if rec is None:
            continue
        matched += 1
        for c in SIGCOLS:
            arrs[c][idx] = rec[c]
    for c in SIGCOLS:
        cal[c] = arrs[c]
    print(f"cal rows matched to my box-signal: {matched}/{len(cal)} "
          f"({100*matched/len(cal):.1f}%)", flush=True)

    # sanity: does my reconstructed team_vac_pts agree with the frame's vac_pts?
    sub = cal[(cal["team_vac_pts"] > 0) & (cal["vac_pts"] > 0)]
    if len(sub) > 100:
        cc = np.corrcoef(sub["team_vac_pts"], sub["vac_pts"])[0, 1]
        print(f"sanity corr(my team_vac_pts, frame vac_pts) on overlap n={len(sub)}: {cc:+.3f}")

    STATS = ["pts", "reb", "ast"]
    BENS = ["ben_vac_pts_share", "ben_vac_min_share", "pos_vac_pts", "pos_vac_min", "pos_n_out"]
    CONTROL = "vac_pts"  # the frame's own team-total vac_pts (what the retrain adds)

    print("\n" + "=" * 96)
    print("ORTHOGONALITY: corr(ben, resid)  and  PARTIAL corr(ben, resid | frame vac_pts)")
    print(f"  control = frame '{CONTROL}' (team-total). matched-only rows (out-regulars present).")
    print("=" * 96)
    results = []
    for stat in STATS:
        s = cal[cal["stat"] == stat].copy()
        # restrict to rows where my construction actually applied (matched, has any out-regs)
        s = s[s["team_n_out"] >= 0]  # all matched rows; ben=0 informative (no benefit)
        r = s["resid"].to_numpy(float)
        z = pd.to_numeric(s[CONTROL], errors="coerce").to_numpy(float)
        print(f"\n--- stat={stat}  n={len(s)} ---")
        print(f"  {'signal':22s} {'corr(ben,resid)':>17s} {'partial(|vac_pts)':>19s} {'n':>8s}")
        for b in BENS:
            x = pd.to_numeric(s[b], errors="coerce").to_numpy(float)
            c0, n0 = simple_corr(x, r)
            cp, np_ = partial_corr(x, z, r)
            flag = "  <-- candidate" if (np.isfinite(cp) and abs(cp) >= 0.05) else ""
            print(f"  {b:22s} {c0:>+17.4f} {cp:>+19.4f} {n0:>8d}{flag}")
            results.append((stat, b, c0, cp, n0))

    # also: on the subset where there is actually vacated load (team_n_out>=1) — the
    # population where a beneficiary signal can matter at all.
    print("\n" + "=" * 96)
    print("SUBSET team_n_out>=1 (only games with >=1 out-regular):")
    print("=" * 96)
    for stat in STATS:
        s = cal[(cal["stat"] == stat) & (cal["team_n_out"] >= 1)].copy()
        if len(s) < 200:
            print(f"  stat={stat}: n={len(s)} <200 skip"); continue
        r = s["resid"].to_numpy(float)
        z = pd.to_numeric(s[CONTROL], errors="coerce").to_numpy(float)
        print(f"\n--- stat={stat}  n={len(s)} (out-regular present) ---")
        print(f"  {'signal':22s} {'corr(ben,resid)':>17s} {'partial(|vac_pts)':>19s} {'n':>8s}")
        for b in BENS:
            x = pd.to_numeric(s[b], errors="coerce").to_numpy(float)
            c0, n0 = simple_corr(x, r)
            cp, np_ = partial_corr(x, z, r)
            flag = "  <-- candidate" if (np.isfinite(cp) and abs(cp) >= 0.05) else ""
            print(f"  {b:22s} {c0:>+17.4f} {cp:>+19.4f} {n0:>8d}{flag}")

    # Reference: the team-total vac_pts own residual corr (what we're competing past)
    print("\n" + "=" * 96)
    print("REFERENCE — frame team-total vac_pts simple corr with resid (the bar to beat):")
    for stat in STATS:
        s = cal[cal["stat"] == stat]
        c0, n0 = simple_corr(pd.to_numeric(s["vac_pts"], errors="coerce").to_numpy(float),
                             s["resid"].to_numpy(float))
        print(f"  {stat}: corr(vac_pts,resid)={c0:+.4f}  n={n0}")


if __name__ == "__main__":
    main()
