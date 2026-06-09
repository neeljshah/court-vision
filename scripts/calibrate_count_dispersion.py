"""
calibrate_count_dispersion.py — empirically estimate count-stat dispersion (var/mean)
for REB/AST/STL/BLK from real player-game data, then re-price the WCF G7 count props
with the EMPIRICAL dispersions and run a NegBinom calibration reliability check.

Replaces the ASSUMED dispersion priors in scripts/count_prop_audit.py
(reb 1.35 / ast 1.45 / stl 1.20 / blk 1.55) with measured values.

Designed to run on RunPod (gamelogs in data/nba/gamelog_*_{season}.json) for the
dispersion + calibration parts, and locally for the re-pricing (reuses the same
intel cache CSVs as count_prop_audit.py).

Usage:
  python scripts/calibrate_count_dispersion.py --mode disp        # RunPod: dispersion + calibration
  python scripts/calibrate_count_dispersion.py --mode reprice     # local: re-price WCF props
  (default runs whichever parts have their inputs available)

Every number is from a real computation; n is always reported. No fabricated values.
"""
import json, glob, math, csv, argparse
from pathlib import Path
from collections import defaultdict

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
NBA = ROOT / "data" / "nba"
CACHE = ROOT / "data" / "cache" / "intel_game7"
SERIES = ROOT / "data" / "cache" / "intel_2026-05-26" / "wcf_player_series_avg_6g.csv"
OUT_JSON = CACHE / "count_dispersion_empirical.json"

STATS = ["reb", "ast", "stl", "blk"]
KEYMAP = {"reb": "REB", "ast": "AST", "stl": "STL", "blk": "BLK"}
ASSUMED = {"reb": 1.35, "ast": 1.45, "stl": 1.20, "blk": 1.55}
REG = 0.93  # same regression the original audit used

MIN_FLOOR = 8.0   # minutes floor: only games where the player was in the rotation
MIN_GAMES = 10    # only players with >=10 qualifying games contribute to dispersion

# player-mean buckets per stat (dispersion changes with the mean level)
BUCKETS = {
    "reb": [(0, 1), (1, 2), (2, 4), (4, 7), (7, 12), (12, 99)],
    "ast": [(0, 1), (1, 2), (2, 4), (4, 7), (7, 12), (12, 99)],
    "stl": [(0, 0.5), (0.5, 1.0), (1.0, 1.5), (1.5, 2.5), (2.5, 99)],
    "blk": [(0, 0.3), (0.3, 0.7), (0.7, 1.2), (1.2, 2.0), (2.0, 99)],
}


def bucket_of(stat, m):
    for lo, hi in BUCKETS[stat]:
        if lo <= m < hi:
            return (lo, hi)
    return BUCKETS[stat][-1]


# ---------------------------------------------------------------------------
# Sample assembly
# ---------------------------------------------------------------------------
def load_sample():
    files = sorted(glob.glob(str(NBA / "gamelog_*_2024-25.json")) +
                   glob.glob(str(NBA / "gamelog_*_2025-26.json")))
    by_player = defaultdict(lambda: defaultdict(list))  # pid -> stat -> [vals]
    n_total = n_kept = 0
    for fp in files:
        pid = Path(fp).name.split("gamelog_")[1].split("_")[0]
        try:
            rows = json.load(open(fp))
        except Exception:
            continue
        for g in rows:
            n_total += 1
            try:
                mn = float(g.get("MIN") or 0)
            except Exception:
                mn = 0.0
            if mn < MIN_FLOOR:
                continue
            n_kept += 1
            for stat in STATS:
                v = g.get(KEYMAP[stat])
                if v is None:
                    continue
                by_player[pid][stat].append(int(v))
    return files, by_player, n_total, n_kept


# ---------------------------------------------------------------------------
# Dispersion estimation (within-player, pooled per mean-bucket)
# ---------------------------------------------------------------------------
def estimate_dispersion(by_player):
    agg = {s: defaultdict(lambda: {"ss": 0.0, "dof": 0.0, "wnum": 0.0,
                                   "wden": 0.0, "nplayers": 0, "ngames": 0})
           for s in STATS}
    raw_pool = {s: [] for s in STATS}  # (val) flat pool per stat for naive comparison
    for pid, sd in by_player.items():
        for stat in STATS:
            vals = sd.get(stat, [])
            n = len(vals)
            if n < MIN_GAMES:
                continue
            arr = np.asarray(vals, dtype=float)
            m = arr.mean()
            ss = float(((arr - m) ** 2).sum())
            b = bucket_of(stat, m)
            a = agg[stat][b]
            a["ss"] += ss
            a["dof"] += (n - 1)
            a["wnum"] += m * n
            a["wden"] += n
            a["nplayers"] += 1
            a["ngames"] += n
            raw_pool[stat].extend(vals)

    result = {"buckets": {}, "overall": {}}
    for stat in STATS:
        result["buckets"][stat] = []
        for (lo, hi), a in sorted(agg[stat].items()):
            if a["dof"] <= 0:
                continue
            pooled_var = a["ss"] / a["dof"]
            wmean = a["wnum"] / a["wden"]
            disp = pooled_var / wmean if wmean > 0 else float("nan")
            result["buckets"][stat].append({
                "lo": lo, "hi": (hi if hi < 90 else None),
                "wt_mean": round(wmean, 3), "pooled_var": round(pooled_var, 4),
                "disp": round(disp, 4), "nplayers": a["nplayers"], "ngames": a["ngames"]})
        # overall within-player
        tss = sum(a["ss"] for a in agg[stat].values())
        tdof = sum(a["dof"] for a in agg[stat].values())
        tgm = sum(a["ngames"] for a in agg[stat].values())
        wn = sum(a["wnum"] for a in agg[stat].values())
        wd = sum(a["wden"] for a in agg[stat].values())
        if tdof > 0 and wd > 0:
            pv = tss / tdof
            wm = wn / wd
            result["overall"][stat] = {"disp": round(pv / wm, 4), "assumed": ASSUMED[stat],
                                       "wt_mean": round(wm, 3), "ngames": tgm,
                                       "pooled_var": round(pv, 4)}
    return result, agg


def disp_lookup(disp_result, stat, mean):
    """Empirical dispersion for a given stat+mean from the bucket table; floor at 1.0."""
    best = None
    for b in disp_result["buckets"][stat]:
        lo = b["lo"]; hi = b["hi"] if b["hi"] is not None else 1e9
        if lo <= mean < hi:
            best = b["disp"]; break
    if best is None:
        best = disp_result["overall"][stat]["disp"]
    return max(best, 1.0)


# ---------------------------------------------------------------------------
# NegBinom under-CDF (same parameterization as count_prop_audit.py)
# ---------------------------------------------------------------------------
def nb_under(mean, line, disp):
    mean = max(mean, 0.05)
    var = disp * mean
    k = int(math.floor(line))
    if var <= mean * 1.001:
        return float(stats.poisson(mean).cdf(k))
    p = mean / var
    r = mean * p / (1 - p)
    return float(stats.nbinom(r, p).cdf(k))


# ---------------------------------------------------------------------------
# Calibration reliability: predicted P(X<=line) vs realized hit rate
# ---------------------------------------------------------------------------
def calibration_check(by_player, disp_result):
    """For each stat, at several integer-ish lines, compare mean predicted P(X<=line)
    (NegBinom with each player's own mean + empirical disp) to the realized frequency
    across all qualifying player-games."""
    out = {}
    test_lines = {"reb": [3.5, 5.5, 7.5, 9.5], "ast": [1.5, 3.5, 5.5, 7.5],
                  "stl": [0.5, 1.5, 2.5], "blk": [0.5, 1.5, 2.5]}
    for stat in STATS:
        rows = []
        for line in test_lines[stat]:
            pred_sum = 0.0
            n_obs = 0
            hits = 0  # X <= line
            for pid, sd in by_player.items():
                vals = sd.get(stat, [])
                if len(vals) < MIN_GAMES:
                    continue
                arr = np.asarray(vals, dtype=float)
                m = arr.mean()
                disp = disp_lookup(disp_result, stat, m)
                p_under = nb_under(m, line, disp)
                # each game is an observation; predicted prob is per player-mean
                for v in vals:
                    pred_sum += p_under
                    hits += 1 if v <= math.floor(line) else 0
                    n_obs += 1
            if n_obs == 0:
                continue
            pred = pred_sum / n_obs
            actual = hits / n_obs
            rows.append({"line": line, "n": n_obs, "pred_p_under": round(pred, 4),
                         "actual_p_under": round(actual, 4), "diff": round(pred - actual, 4)})
        out[stat] = rows
    return out


# ---------------------------------------------------------------------------
# Re-price WCF props with empirical dispersion
# ---------------------------------------------------------------------------
def name_key(n):
    return n.strip().lower().replace("’", "'")


def reprice(disp_result):
    series = {}
    with open(SERIES, newline="") as f:
        for r in csv.DictReader(f):
            series[name_key(r["player_name"])] = {
                "reb": float(r["reb_pg"]), "ast": float(r["ast_pg"]),
                "stl": float(r["stl_pg"]), "blk": float(r["blk_pg"])}

    def b_from_odds(o):
        o = float(o)
        return o / 100.0 if o > 0 else 100.0 / abs(o)

    rows = []
    with open(CACHE / "prop_ev_best.csv", newline="") as f:
        for r in csv.DictReader(f):
            stat = r["stat"]
            if stat not in STATS or r["book"] == "fanatics":
                continue
            s = series.get(name_key(r["player"]))
            if not s:
                continue
            line = float(r["line"]); side = r["side"]
            odds = float(r["odds"]); board_p = float(r["p_win"])
            mean = s[stat] * REG
            disp_emp = disp_lookup(disp_result, stat, mean)
            disp_old = ASSUMED[stat]
            p_under_emp = nb_under(mean, line, disp_emp)
            p_under_old = nb_under(mean, line, disp_old)
            honest_emp = p_under_emp if side == "UNDER" else 1 - p_under_emp
            honest_old = p_under_old if side == "UNDER" else 1 - p_under_old
            b = b_from_odds(odds)
            ev_emp = honest_emp * b - (1 - honest_emp)
            rows.append({
                "player": r["player"], "stat": stat, "side": side, "line": line,
                "series_avg": round(s[stat], 2), "model_mean": round(mean, 2),
                "disp_assumed": disp_old, "disp_empirical": round(disp_emp, 3),
                "board_p": round(board_p, 3),
                "honest_p_assumed": round(honest_old, 3),
                "honest_p_empirical": round(honest_emp, 3),
                "delta_vs_board_assumed": round(honest_old - board_p, 3),
                "delta_vs_board_empirical": round(honest_emp - board_p, 3),
                "shift_emp_minus_assumed": round(honest_emp - honest_old, 3),
                "odds": int(odds), "honest_ev_empirical": round(ev_emp, 3), "book": r["book"]})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["disp", "reprice", "all"], default="all")
    args = ap.parse_args()

    out = {}
    disp_result = None

    have_gamelogs = len(glob.glob(str(NBA / "gamelog_*_2024-25.json"))) > 0
    if args.mode in ("disp", "all") and have_gamelogs:
        files, by_player, n_total, n_kept = load_sample()
        disp_result, agg = estimate_dispersion(by_player)
        disp_result["sample"] = {"n_gamelog_files": len(files), "rows_total": n_total,
                                 "rows_kept": n_kept, "min_minutes": MIN_FLOOR,
                                 "min_games_per_player": MIN_GAMES,
                                 "seasons": ["2024-25", "2025-26"]}
        disp_result["assumed_disp"] = ASSUMED
        out["dispersion"] = disp_result

        print(f"SAMPLE: files={len(files)} rows_total={n_total} rows_kept={n_kept}")
        print("\n=== EMPIRICAL DISPERSION (within-player var/mean) by mean-bucket ===")
        for stat in STATS:
            print(f"\n-- {stat.upper()}  (assumed {ASSUMED[stat]}) --")
            print(f"{'bucket':>12s} {'wt_mean':>8s} {'var':>8s} {'disp':>7s} {'nplyr':>6s} {'ngames':>7s}")
            for b in disp_result["buckets"][stat]:
                bk = f"[{b['lo']},{b['hi']})"
                print(f"{bk:>12s} {b['wt_mean']:8.2f} {b['pooled_var']:8.3f} "
                      f"{b['disp']:7.3f} {b['nplayers']:6d} {b['ngames']:7d}")
            ov = disp_result["overall"][stat]
            print(f"  OVERALL disp={ov['disp']:.3f} vs assumed {ov['assumed']} "
                  f"(wt_mean={ov['wt_mean']}, ngames={ov['ngames']})")

        cal = calibration_check(by_player, disp_result)
        out["calibration"] = cal
        print("\n=== CALIBRATION RELIABILITY (predicted vs actual P(X<=line)) ===")
        for stat in STATS:
            print(f"\n-- {stat.upper()} --")
            print(f"{'line':>5s} {'n':>7s} {'pred':>7s} {'actual':>7s} {'diff':>7s}")
            for r in cal[stat]:
                print(f"{r['line']:5} {r['n']:7d} {r['pred_p_under']:7.3f} "
                      f"{r['actual_p_under']:7.3f} {r['diff']:+7.3f}")

    have_props = (CACHE / "prop_ev_best.csv").exists() and SERIES.exists()
    if args.mode in ("reprice", "all") and have_props:
        if disp_result is None and OUT_JSON.exists():
            disp_result = json.load(open(OUT_JSON)).get("dispersion")
        if disp_result is not None:
            rows = reprice(disp_result)
            out["reprice"] = rows
            flagged_assumed = [r for r in rows if abs(r["delta_vs_board_assumed"]) > 0.10]
            flagged_emp = [r for r in rows if abs(r["delta_vs_board_empirical"]) > 0.10]
            out["reprice_summary"] = {
                "n_props": len(rows),
                "n_flagged_assumed": len(flagged_assumed),
                "n_flagged_empirical": len(flagged_emp)}
            print(f"\n=== RE-PRICE: {len(rows)} props | flags assumed={len(flagged_assumed)} "
                  f"empirical={len(flagged_emp)} ===")
            print(f"{'bet':38s} {'disp_a':>6s} {'disp_e':>6s} {'h_assum':>7s} "
                  f"{'h_emp':>6s} {'shift':>6s} {'flag_a':>6s} {'flag_e':>6s}")
            for r in sorted(rows, key=lambda x: abs(x["shift_emp_minus_assumed"]), reverse=True):
                nm = f"{r['player']} {r['stat'].upper()} {r['side']} {r['line']}"
                fa = "Y" if abs(r["delta_vs_board_assumed"]) > 0.10 else "."
                fe = "Y" if abs(r["delta_vs_board_empirical"]) > 0.10 else "."
                print(f"{nm:38.38s} {r['disp_assumed']:6.2f} {r['disp_empirical']:6.2f} "
                      f"{r['honest_p_assumed']:7.3f} {r['honest_p_empirical']:6.3f} "
                      f"{r['shift_emp_minus_assumed']:+6.3f} {fa:>6s} {fe:>6s}")
        else:
            print("No dispersion result available for re-pricing.")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(OUT_JSON, "w"), indent=2)
    print(f"\nWROTE {OUT_JSON}")


if __name__ == "__main__":
    main()
