"""scripts.platformkit.proof_nba.totals_with_availability — does AVAILABILITY close the gap?

The biggest BEHIND number on the beat-the-close scoreboard is NBA totals: our as-of
possessions/efficiency model RMSE ~19.17 vs the devigged close ~18.11 (gap +1.06). W136/W138/
W140 attributed that gap to injury/lineup FRESHNESS the market prices and a box model cannot
see. This tests it DIRECTLY: add a leak-free AVAILABILITY feature (rotation players who are
absent from the target game) and re-measure the gap.

LEAK REASONING (the load-bearing argument, defended):
  NBA inactives are announced PRE-GAME (~hours before tip, on the official injury report). A
  player who records EXACTLY 0 minutes / is not in the box is a PRE-GAME-KNOWN scratch, NOT a
  game outcome -- it is precisely the freshness datum the market prices into the close. The
  feature uses only (a) WHO is absent (a 0-min scratch, pre-game-known) and (b) the absent
  players' PRIOR PPG from games BEFORE the target (never their this-game stats). The ONLY
  residual leak risk is an IN-GAME injury (a starter who tweaks an ankle and exits), but such a
  player records >0 minutes, so the strict 0-min/absent filter EXCLUDES them. A real-time
  inactive feed (forward) would supply exactly this WHO-is-out signal; the box-scratch is the
  backtest PROXY for it.

If availability narrows the gap, that CONFIRMS freshness is the gap and a forward inactive feed
would capture it. If it does not, that is an honest null worth logging. Totals graded RMSE+bias
(never MAE). INVARIANTS: never edit src/ or kernel/; <=300 LOC.
Run: python -m scripts.platformkit.proof_nba.totals_with_availability
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_NBA = _REPO / "data" / "domains" / "basketball_nba"
_ALPHA = 0.05            # EW step for pace/ppp state (matches asof_box_accuracy)
_MPG_MIN = 20.0          # rotation = averaging >= this MPG over the recent window
_WINDOW = 10             # over the player's last N appearances before the target game
_MIN_APP = 3             # need at least this many prior appearances to be "established"
_RECENT = 3              # absence counts only if the player played within the team's last N games
                         # -- a LONG-TERM injury is already absorbed into the team's as-of
                         #    efficiency state, so it is NOT fresh; we want the NEW scratch only
_INIT_PACE, _INIT_PPP = 100.5, 1.13


def _rmse_bias(pred: np.ndarray, truth: np.ndarray) -> Tuple[float, float]:
    e = pred - truth
    return float(np.sqrt(np.mean(e ** 2))), float(np.mean(e))


def load_player_box() -> pd.DataFrame:
    """Per-player per-game box, date-sorted, with home/away team identified per game.
    Self-contained: realized total = sum of player pts; abbrs already match the odds feed."""
    pb = pd.read_parquet(_NBA / "player_boxscores.parquet")
    pb["date"] = pd.to_datetime(pb["date"], errors="coerce")
    pb = pb.dropna(subset=["date"]).sort_values(["date", "game_id"]).reset_index(drop=True)
    pb["min"] = pb["min"].astype(float)
    pb["pts"] = pb["pts"].astype(float)
    return pb


def _team_games(pb: pd.DataFrame) -> pd.DataFrame:
    """One row per (game_id, team): pts/possession inputs + home flag + opponent, date-ordered."""
    agg = pb.groupby(["game_id", "team"]).agg(
        date=("date", "first"), opp=("opp", "first"), is_home=("is_home", "first"),
        pts=("pts", "sum"), fga=("fga", "sum"), fta=("fta", "sum"),
        oreb=("oreb", "sum"), tov=("tov", "sum"),
    ).reset_index()
    agg["poss"] = agg["fga"] + 0.44 * agg["fta"] - agg["oreb"] + agg["tov"]
    return agg.sort_values(["date", "game_id"]).reset_index(drop=True)


def _build_games(pb: pd.DataFrame) -> pd.DataFrame:
    """One row per game: home/away abbr, realized total, base as-of total, vacated scoring.
    Single chronological pass; per-game player rows are pre-grouped to avoid O(n^2) scans."""
    tg = _team_games(pb)
    # ---- as-of EW pace / off-ppp / def-ppp per team (leak-free, snapshot before update) ----
    pace: Dict[str, float] = {}; offp: Dict[str, float] = {}; defp: Dict[str, float] = {}
    # ---- rotation tracking, per player (id): recent minutes, recent pts, last team seen ----
    p_min: Dict[int, List[float]] = {}; p_pts: Dict[int, List[float]] = {}
    # ---- per team: set of player_ids that currently qualify as established rotation ----
    team_rot: Dict[str, set] = {}
    # ---- per team: count of games seen; per (team) the last team-game-index a player appeared ----
    team_gidx: Dict[str, int] = {}
    last_seen: Dict[str, Dict[int, int]] = {}    # team -> {pid: last team-game index played}

    # pre-group the player box once: game_id -> [(pid, team, min, pts), ...]
    by_game: Dict[object, List[tuple]] = {}
    for rec in pb[["game_id", "player_id", "team", "min", "pts"]].itertuples(index=False):
        by_game.setdefault(rec.game_id, []).append(
            (int(rec.player_id), str(rec.team), float(rec.min), float(rec.pts)))

    rows: List[Dict] = []
    for gid, gdf in tg.groupby("game_id", sort=False):
        if len(gdf) != 2:
            continue
        gdf = gdf.sort_values("is_home", ascending=False)   # home first
        home, away = gdf.iloc[0], gdf.iloc[1]
        ht, at = str(home["team"]), str(away["team"])
        for d, init in ((pace, _INIT_PACE), (offp, _INIT_PPP), (defp, _INIT_PPP)):
            d.setdefault(ht, init); d.setdefault(at, init)
        ppace = 0.5 * (pace[ht] + pace[at])
        base = ppace * (0.5 * (offp[ht] + defp[at]) + 0.5 * (offp[at] + defp[ht]))

        # ---- availability: established-rotation players for each team who are ABSENT ----
        recs = by_game.get(gid, [])
        present = {pid for pid, _t, mn, _p in recs if mn > 0.0}   # strict >0 min
        vac = 0.0
        for team in (ht, at):
            gi = team_gidx.get(team, 0)                          # this team's upcoming game index
            seen = last_seen.get(team, {})
            for pid in team_rot.get(team, ()):                   # rotation going INTO this game
                if pid not in present:
                    # only a RECENT absence is fresh (long-term injuries already absorbed)
                    if gi - seen.get(pid, -10**9) <= _RECENT:
                        hist = p_pts.get(pid)
                        if hist:
                            vac += float(np.mean(hist[-_WINDOW:]))   # absent player's prior PPG

        realized = float(home["pts"] + away["pts"])
        rows.append({"game_id": gid, "date": home["date"], "home_abbr": ht, "away_abbr": at,
                     "realized": realized, "base": base, "vacated": vac})

        # ---- update as-of pace/ppp state AFTER prediction (leak-free) ----
        for r, opp_pts in ((home, away["pts"]), (away, home["pts"])):
            t = str(r["team"]); p = float(r["poss"])
            if np.isfinite(p) and p > 50:
                pace[t] += _ALPHA * (p - pace[t])
                offp[t] += _ALPHA * (r["pts"] / p - offp[t])
                defp[t] += _ALPHA * (opp_pts / p - defp[t])
        # ---- advance each team's game index (this game just happened) ----
        for team in (ht, at):
            team_gidx[team] = team_gidx.get(team, 0) + 1
        # ---- update player rolling history AFTER, then refresh each team's rotation set ----
        for pid, team, mn, pp in recs:
            if mn > 0.0:
                p_min.setdefault(pid, []).append(mn)
                p_pts.setdefault(pid, []).append(pp)
                last_seen.setdefault(team, {})[pid] = team_gidx[team]   # team-game index just played
                hist = p_min[pid]
                rot = team_rot.setdefault(team, set())
                if len(hist) >= _MIN_APP and float(np.mean(hist[-_WINDOW:])) >= _MPG_MIN:
                    rot.add(pid)
                else:
                    rot.discard(pid)

    out = pd.DataFrame(rows)
    return out[(out["realized"] >= 150) & (out["realized"] <= 320)].reset_index(drop=True)


def load_close() -> pd.DataFrame:
    od = pd.read_parquet(_NBA / "odds.parquet").rename(
        columns={"home_team": "home_abbr", "away_team": "away_abbr"})
    od["date"] = pd.to_datetime(od["date"])
    return od[["date", "home_abbr", "away_abbr", "total"]].rename(columns={"total": "close_total"})


def _score(pred: np.ndarray, realized: np.ndarray, mid: int) -> Tuple[float, float]:
    """Leak-free affine recal fit on the FIRST half, RMSE+bias on the held-out SECOND half."""
    b, a = np.polyfit(pred[:mid], realized[:mid], 1)
    pc = a + b * pred
    return _rmse_bias(pc[mid:], realized[mid:])


def _perm_beats(base_recal: np.ndarray, vac: np.ndarray, realized: np.ndarray,
                mid: int, rmse_model: float, n_perm: int = 50) -> int:
    """Permutation control: shuffle the vacated feature, refit the shrink leak-free on the first
    half, count how many of n_perm shuffles beat model-only OOS. ~0 => no exploitable signal."""
    rng = np.random.default_rng(0)
    beats = 0
    for _ in range(n_perm):
        vp = rng.permutation(vac)
        fr, best = 0.0, float("inf")
        for f in np.linspace(0.0, 1.0, 41):
            rm = float(np.sqrt(np.mean((base_recal[:mid] - f * vp[:mid] - realized[:mid]) ** 2)))
            if rm < best:
                best, fr = rm, float(f)
        r, _b = _rmse_bias(base_recal[mid:] - fr * vp[mid:], realized[mid:])
        beats += int(r < rmse_model - 1e-9)
    return beats


def run() -> Dict:
    pbp = _NBA / "player_boxscores.parquet"
    if not pbp.is_file():
        return {"error": "player_boxscores.parquet missing"}
    pb = load_player_box()
    g = _build_games(pb)
    n = len(g)
    if n < 80:
        return {"status": "data_limited", "n": n}

    realized = g["realized"].to_numpy(float)
    base = g["base"].to_numpy(float)
    vac = g["vacated"].to_numpy(float)
    mid = n // 2

    # ---- fit the vacated-scoring shrink coefficient leak-free on the FIRST half ----
    # model_total = recal(base) - frac * vacated.  Pick frac minimizing FIRST-half prediction
    # RMSE (the honest criterion -- not a residual-slope, which over-fits noise).
    b0, a0 = np.polyfit(base[:mid], realized[:mid], 1)
    base_recal = a0 + b0 * base
    frac, best_rm = 0.0, float("inf")
    for f in np.linspace(0.0, 1.0, 101):
        rm = float(np.sqrt(np.mean((base_recal[:mid] - f * vac[:mid] - realized[:mid]) ** 2)))
        if rm < best_rm:
            best_rm, frac = rm, float(f)

    pred_model = base_recal
    pred_avail = base_recal - frac * vac

    rmse_model, bias_model = _rmse_bias(pred_model[mid:], realized[mid:])
    rmse_avail, bias_avail = _rmse_bias(pred_avail[mid:], realized[mid:])

    # ---- close comparison on the (date,home,away) overlap with odds ----
    close = load_close()
    m = g.merge(close, on=["date", "home_abbr", "away_abbr"], how="inner")
    m = m[m["close_total"].notna()].reset_index(drop=True)
    nc = len(m)
    if nc >= 20:
        cr = m["realized"].to_numpy(float)
        cmid = nc // 2
        rmse_close, bias_close = _rmse_bias(m["close_total"].to_numpy(float)[cmid:], cr[cmid:])
        # re-score our two models on the SAME overlap holdout for an apples-to-apples gap
        rm_mo, _ = _rmse_bias((a0 + b0 * m["base"].to_numpy(float))[cmid:], cr[cmid:])
        rm_av, _ = _rmse_bias((a0 + b0 * m["base"].to_numpy(float)
                               - frac * m["vacated"].to_numpy(float))[cmid:], cr[cmid:])
        rmse_model_ov, rmse_avail_ov = round(rm_mo, 3), round(rm_av, 3)
    else:
        rmse_close = bias_close = float("nan")
        rmse_model_ov = rmse_avail_ov = float("nan")

    gap_before = round(rmse_model_ov - rmse_close, 3) if nc >= 20 else None
    gap_after = round(rmse_avail_ov - rmse_close, 3) if nc >= 20 else None
    pct_closed = (round(100.0 * (gap_before - gap_after) / gap_before, 1)
                  if (gap_before and abs(gap_before) > 1e-6) else None)

    perm_beats = _perm_beats(base_recal, vac, realized, mid, rmse_model)
    avail_helps = rmse_avail < rmse_model - 1e-3
    if avail_helps and pct_closed is not None and pct_closed > 5 and nc >= 20:
        verdict = (f"availability CLOSES ~{pct_closed}% of the gap to the close "
                   f"(gap {gap_before:+}->{gap_after:+}); perm-control {perm_beats}/50")
    elif avail_helps:
        verdict = (f"availability narrows model RMSE ({rmse_model:.3f}->{rmse_avail:.3f}) "
                   f"but only ~{pct_closed}% of the close gap; perm-control {perm_beats}/50")
    else:
        verdict = (f"HONEST NULL: availability does NOT narrow the gap (model {rmse_model:.3f} "
                   f"vs +avail {rmse_avail:.3f}, fitted frac {frac:.3f}, perm-control "
                   f"{perm_beats}/50 shuffles beat model-only); box-scratch proxy adds no signal")

    return {
        "status": "ok", "n": n, "n_holdout": n - mid, "n_close_overlap": nc,
        "fitted_vacated_fraction": round(frac, 3), "perm_beats_model_of_50": perm_beats,
        "mean_vacated_ppg": round(float(np.mean(vac)), 2),
        "rmse_model_only": round(rmse_model, 3), "bias_model_only": round(bias_model, 3),
        "rmse_model_plus_avail": round(rmse_avail, 3), "bias_model_plus_avail": round(bias_avail, 3),
        "rmse_model_only_overlap": rmse_model_ov, "rmse_model_plus_avail_overlap": rmse_avail_ov,
        "rmse_close": round(rmse_close, 3) if nc >= 20 else None,
        "bias_close": round(bias_close, 3) if nc >= 20 else None,
        "gap_before": gap_before, "gap_after": gap_after, "pct_of_gap_closed": pct_closed,
        "availability_helps_model": bool(avail_helps),
        "verdict": verdict,
        "leak_reasoning": ("0-min/absent = pre-game-known scratch (not an outcome); absent "
                           "players' PRIOR PPG only; strict-0 excludes in-game injuries (>0 min). "
                           "See module docstring. Box-scratch = backtest proxy for an inactive feed."),
        "note": "Totals graded RMSE+bias (never MAE). No $ edge claimed.",
    }


def _main() -> int:
    rep = run()
    if "error" in rep:
        print(rep["error"]); return 1
    if rep.get("status") != "ok":
        print(f"{rep['status']}: n={rep.get('n')}"); return 0
    print(f"=== NBA totals: does AVAILABILITY close the gap to the close? "
          f"(n={rep['n']}, holdout={rep['n_holdout']}, close overlap={rep['n_close_overlap']}) ===")
    print(f"  fitted vacated fraction = {rep['fitted_vacated_fraction']}  "
          f"(mean vacated PPG = {rep['mean_vacated_ppg']})")
    print(f"  {'predictor':>22}  {'RMSE':>8} {'bias':>8}")
    print(f"  {'model only':>22}  {rep['rmse_model_only']:>8} {rep['bias_model_only']:>8}")
    print(f"  {'model + availability':>22}  {rep['rmse_model_plus_avail']:>8} "
          f"{rep['bias_model_plus_avail']:>8}")
    if rep["rmse_close"] is not None:
        print(f"  {'market close':>22}  {rep['rmse_close']:>8} {rep['bias_close']:>8}")
        print(f"  (on close overlap: model {rep['rmse_model_only_overlap']} -> "
              f"+avail {rep['rmse_model_plus_avail_overlap']} vs close {rep['rmse_close']})")
        print(f"  gap to close: {rep['gap_before']:+} -> {rep['gap_after']:+}  "
              f"({rep['pct_of_gap_closed']}% of the gap closed)")
    print(f"\nVERDICT: {rep['verdict']}")
    print(f"LEAK: {rep['leak_reasoning']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    sys.exit(_main())
