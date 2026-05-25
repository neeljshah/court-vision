"""probe_R1_D_per_player_quantile_variance.py -- improve_loop R1-D (loop 5).

CALIBRATION probe. Per-player variance-modulated quantile bands.
Treatment: half = base_sigma*scale*Z80 * global_rescale
           * sqrt(clip(std_l20/pop_mean_std, 0.6, 1.8))
Global rescale bisected so overall val-set coverage = 0.80.

Evaluation: bucket (pid, game) rows by std_l20 tercile, compute 80% empirical
coverage per (stat, bucket). Primary metric: avg across 7 stats of
(max_bucket_cov - min_bucket_cov) = "spread".

Ship gate: treat_spread <= base_spread - 0.03
           AND all stat overall coverage in [0.78, 0.82]
           AND no bucket worse than baseline overall coverage by > 0.05

JSON schema (scripts/_results/improve_R1_D_per_player_quantile_variance.json):
  name, n_games, global_rescale, base_spread, treat_spread, spread_delta,
  per_stat: [{stat, n, base_overall_cov, treat_overall_cov,
              base_buckets:{Low,Mid,High}, treat_buckets:{Low,Mid,High}}],
  ship, ship_reason

Run:
    python scripts/probe_R1_D_per_player_quantile_variance.py [--max-games N]
"""
from __future__ import annotations

import argparse, glob, json, os, sys, warnings
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (PROJECT_DIR, os.path.join(PROJECT_DIR, "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import retro_inplay_mae as rim  # noqa: E402
from src.prediction.live_quantile_bands import (  # noqa: E402
    ASYMMETRIC_STATS, _Z80, load_calibration,
)

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
SNAPSHOT_POINT = "endQ3"
_GAMELOG_GLOB = os.path.join(PROJECT_DIR, "data", "nba", "gamelog_*.json")
_OUT_DIR = os.path.join(PROJECT_DIR, "scripts", "_results")
_TERCILES = ("Low", "Mid", "High")
_TARGET_COV = 0.80
_L20 = 20


# ── gamelog helpers ────────────────────────────────────────────────────────────

def _iso(s) -> Optional[str]:
    try:
        return datetime.strptime(str(s), "%b %d, %Y").date().isoformat()
    except Exception:
        return None


def load_gamelogs() -> Dict[int, List[Tuple[str, Dict[str, float]]]]:
    """Return {pid: [(date_iso, {stat: value}), ...]} sorted chronologically."""
    out: Dict[int, List[Tuple[str, Dict[str, float]]]] = {}
    for fp in glob.glob(_GAMELOG_GLOB):
        parts = os.path.basename(fp).split("_")
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[1])
        except ValueError:
            continue
        try:
            rows = json.load(open(fp, encoding="utf-8")) or []
        except Exception:
            continue
        for row in rows:
            d = _iso(row.get("GAME_DATE"))
            if d is None:
                continue
            sv = {s: float(row.get(s.upper(), 0) or 0) for s in STATS}
            out.setdefault(pid, []).append((d, sv))
    for pid in out:
        out[pid].sort(key=lambda x: x[0])
    return out


def std_l20(pid: int, date: Optional[str], stat: str,
            idx: Dict[int, List[Tuple[str, Dict[str, float]]]]) -> Optional[float]:
    """Std of last 20 stat values STRICTLY BEFORE date (walk-forward safe)."""
    log = idx.get(pid, [])
    if not log:
        return None
    prior = [r[stat] for (d, r) in log if date is None or d < date][-_L20:]
    return float(np.std(prior, ddof=1)) if len(prior) >= 3 else None


def pop_mean_stds(idx: Dict[int, List[Tuple[str, Dict[str, float]]]]) -> Dict[str, float]:
    """Mean per-player std_l20 across the corpus (normaliser for modulation)."""
    acc: Dict[str, List[float]] = defaultdict(list)
    for pid, log in idx.items():
        for i in range(_L20, len(log), 5):
            d = log[i][0]
            for s in STATS:
                v = std_l20(pid, d, s, idx)
                if v is not None:
                    acc[s].append(v)
    return {s: float(np.mean(acc[s])) if acc[s] else 1.0 for s in STATS}


# ── band helpers ───────────────────────────────────────────────────────────────

def base_half(entry: dict) -> float:
    return float(entry.get("scale", 1.0)) * float(entry.get("sigma", 0.0)) * _Z80


def treat_half(entry: dict, raw_std: Optional[float],
               pop_std: float, rescale: float) -> float:
    ratio = float(np.clip(raw_std / pop_std, 0.6, 1.8)) if (
        raw_std is not None and pop_std > 0) else 1.0
    return base_half(entry) * rescale * float(np.sqrt(ratio))


def cov_rate(q50: np.ndarray, act: np.ndarray,
             half: np.ndarray, asym: bool) -> float:
    q10, q90 = q50 - half, q50 + half
    if asym:
        q10 = np.maximum(0.0, q10)
    return float(((act >= q10) & (act <= q90)).mean()) if len(act) else float("nan")


# ── corpus ─────────────────────────────────────────────────────────────────────

def collect(max_games: int, idx: dict) -> Tuple[
        Dict[str, np.ndarray], Dict[str, np.ndarray], Dict[str, List[Optional[float]]]]:
    from src.prediction.live_engine import project_from_snapshot
    qstats = rim.load_quarter_stats()
    gids = sorted(qstats["game_id"].unique().tolist())
    if max_games:
        gids = gids[:max_games]
    q50s: Dict[str, List[float]] = {s: [] for s in STATS}
    acts: Dict[str, List[float]] = {s: [] for s in STATS}
    stds: Dict[str, List[Optional[float]]] = {s: [] for s in STATS}
    n_ok = 0
    for gid in gids:
        snap = rim.build_snapshot(gid, SNAPSHOT_POINT, qstats)
        if snap is None:
            continue
        game_actuals = rim.actuals_for_game(gid, qstats)
        if not game_actuals:
            continue
        game_date = rim.find_game_date(gid, qstats)
        try:
            rows = project_from_snapshot(snap)
        except Exception:
            continue
        for r in rows:
            pid, stat = r.get("player_id"), r.get("stat")
            if pid is None or stat not in STATS:
                continue
            try:
                q50 = float(r.get("projected_final", 0.0) or 0.0)
            except (TypeError, ValueError):
                continue
            actual = game_actuals.get((int(pid), stat))
            if actual is None:
                continue
            q50s[stat].append(q50)
            acts[stat].append(float(actual))
            stds[stat].append(std_l20(int(pid), game_date, stat, idx))
        n_ok += 1
        if n_ok % 100 == 0:
            print(f"  [corpus] {n_ok}/{len(gids)}", flush=True)
    print(f"  [corpus] {n_ok} games, pts n={len(q50s['pts'])}", flush=True)
    return (
        {s: np.array(q50s[s], dtype=float) for s in STATS},
        {s: np.array(acts[s], dtype=float) for s in STATS},
        stds,
    )


# ── bisect global rescale ─────────────────────────────────────────────────────

def bisect_rescale(q50s, acts, stds, cal, pmstds, target=_TARGET_COV) -> float:
    lo, hi = 0.3, 3.0
    for _ in range(40):
        mid = (lo + hi) / 2.0
        covs = []
        for s in STATS:
            entry = cal.get(s, {})
            asym = bool(entry.get("asymmetric", s in ASYMMETRIC_STATS))
            h = np.array([treat_half(entry, v, pmstds[s], mid) for v in stds[s]])
            covs.append(cov_rate(q50s[s], acts[s], h, asym))
        (lo if np.mean(covs) < target else None, hi)[np.mean(covs) >= target]
        if np.mean(covs) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


# ── bucket coverage ───────────────────────────────────────────────────────────

def bucket_cov(q50: np.ndarray, act: np.ndarray, half: np.ndarray,
               imp_std: np.ndarray, asym: bool) -> Dict[str, float]:
    if len(imp_std) < 9:
        return {lbl: float("nan") for lbl in _TERCILES}
    t33, t67 = np.percentile(imp_std, 33.33), np.percentile(imp_std, 66.67)
    masks = {
        "Low":  imp_std <= t33,
        "Mid":  (imp_std > t33) & (imp_std <= t67),
        "High": imp_std > t67,
    }
    return {lbl: (cov_rate(q50[m], act[m], half[m], asym) if m.sum() else float("nan"))
            for lbl, m in masks.items()}


def _spread(bkt: Dict[str, float]) -> float:
    vs = [v for v in bkt.values() if v == v]
    return (max(vs) - min(vs)) if len(vs) >= 2 else float("nan")


# ── result schema ─────────────────────────────────────────────────────────────

@dataclass
class CalProbeResult:
    name: str
    n_games: int
    global_rescale: float
    base_spread: float
    treat_spread: float
    spread_delta: float
    per_stat: List[Dict] = field(default_factory=list)
    ship: bool = False
    ship_reason: str = ""

    def to_md(self) -> str:
        hdr = (f"# probe {self.name} -- improve_loop (CALIBRATION)\n\n"
               f"**Games:** {self.n_games}  **Rescale:** {self.global_rescale:.4f}\n\n"
               "## Spread\n\n| metric | baseline | treatment | delta |\n"
               "|--------|----------|-----------|-------|\n"
               f"| spread (avg max-min cov) | {self.base_spread:.4f} "
               f"| {self.treat_spread:.4f} | {self.spread_delta:+.4f} |\n\n"
               "## Per-stat bucket coverage\n\n"
               "| stat | base_all | treat_all | bLow | bMid | bHigh"
               " | tLow | tMid | tHigh |\n"
               "|------|----------|-----------|------|------|------|------|------|------|\n")
        rows = []
        for r in self.per_stat:
            bb, tb = r["base_buckets"], r["treat_buckets"]
            def f(v): return f"{v:.3f}" if (isinstance(v, float) and v==v) else "nan"
            rows.append(f"| {r['stat']} | {f(r['base_overall_cov'])} "
                        f"| {f(r['treat_overall_cov'])} "
                        f"| {f(bb.get('Low',float('nan')))} "
                        f"| {f(bb.get('Mid',float('nan')))} "
                        f"| {f(bb.get('High',float('nan')))} "
                        f"| {f(tb.get('Low',float('nan')))} "
                        f"| {f(tb.get('Mid',float('nan')))} "
                        f"| {f(tb.get('High',float('nan')))} |")
        verdict = (f"\n## Verdict\n\n"
                   f"- **{'SHIP' if self.ship else 'REJECT'}**: {self.ship_reason}\n")
        return hdr + "\n".join(rows) + verdict


# ── main ──────────────────────────────────────────────────────────────────────

def run_probe(max_games: int = 0) -> CalProbeResult:
    name = "R1_D_per_player_quantile_variance"
    print(f"[{name}] loading gamelogs...", flush=True)
    idx = load_gamelogs()
    print(f"[{name}] {len(idx)} players; computing pop_mean_stds...", flush=True)
    pmstds = pop_mean_stds(idx)
    print("  " + "  ".join(f"{s}={pmstds[s]:.3f}" for s in STATS), flush=True)

    q50s, acts, stds = collect(max_games, idx)
    cal = (load_calibration() or {}).get(SNAPSHOT_POINT, {})

    print(f"[{name}] bisecting rescale...", flush=True)
    rescale = bisect_rescale(q50s, acts, stds, cal, pmstds)
    print(f"[{name}] rescale={rescale:.4f}", flush=True)

    per_stat, b_spreads, t_spreads = [], [], []
    for s in STATS:
        entry = cal.get(s, {})
        asym = bool(entry.get("asymmetric", s in ASYMMETRIC_STATS))
        ps = pmstds[s]
        q50, act = q50s[s], acts[s]
        imp = np.array([v if v is not None else ps for v in stds[s]], dtype=float)

        bh = np.full(len(q50), base_half(entry))
        th = np.array([treat_half(entry, v, ps, rescale) for v in stds[s]])

        b_all = cov_rate(q50, act, bh, asym)
        t_all = cov_rate(q50, act, th, asym)
        bb = bucket_cov(q50, act, bh, imp, asym)
        tb = bucket_cov(q50, act, th, imp, asym)

        bs, ts = _spread(bb), _spread(tb)
        if bs == bs: b_spreads.append(bs)
        if ts == ts: t_spreads.append(ts)
        per_stat.append({"stat": s, "n": len(q50),
                         "base_overall_cov": b_all, "treat_overall_cov": t_all,
                         "base_spread": bs, "treat_spread": ts,
                         "base_buckets": bb, "treat_buckets": tb})

    avg_b = float(np.mean(b_spreads)) if b_spreads else float("nan")
    avg_t = float(np.mean(t_spreads)) if t_spreads else float("nan")
    delta = avg_t - avg_b

    spread_ok = avg_t <= avg_b - 0.03
    cov_ok = all(0.78 <= r["treat_overall_cov"] <= 0.82 for r in per_stat
                 if r["treat_overall_cov"] == r["treat_overall_cov"])
    no_bad = all(
        tb_v >= r["base_overall_cov"] - 0.05
        for r in per_stat
        for tb_v in r["treat_buckets"].values()
        if tb_v == tb_v
    )
    ship = spread_ok and cov_ok and no_bad

    causes = []
    if not spread_ok:
        causes.append(f"spread {avg_t:.4f} not <= {avg_b:.4f}-0.03")
    if not cov_ok:
        bad = [f"{r['stat']}={r['treat_overall_cov']:.3f}" for r in per_stat
               if not (0.78 <= r["treat_overall_cov"] <= 0.82)]
        causes.append(f"cov out of [0.78,0.82]: {','.join(bad)}")
    if not no_bad:
        causes.append("bucket degraded >0.05 vs baseline")
    ship_reason = (
        f"spread {avg_t:.4f}<={avg_b:.4f}-0.03; cov in range; no bad bucket"
        if ship else "; ".join(causes) or "gate not met"
    )

    result = CalProbeResult(
        name=name, n_games=len(q50s["pts"]) // 6,
        global_rescale=round(rescale, 6),
        base_spread=round(avg_b, 6), treat_spread=round(avg_t, 6),
        spread_delta=round(delta, 6),
        per_stat=per_stat, ship=ship, ship_reason=ship_reason,
    )
    print(f"  [{name}] SHIP={ship}  base_spread={avg_b:.4f}  "
          f"treat_spread={avg_t:.4f}  delta={delta:+.4f}", flush=True)

    os.makedirs(_OUT_DIR, exist_ok=True)
    md_path = os.path.join(_OUT_DIR, f"improve_{name}.md")
    json_path = os.path.join(_OUT_DIR, f"improve_{name}.json")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(result.to_md())

    def _clean(o):
        if isinstance(o, float) and o != o: return None
        if isinstance(o, dict): return {k: _clean(v) for k, v in o.items()}
        if isinstance(o, list): return [_clean(v) for v in o]
        return o

    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(_clean(asdict(result)), fh, indent=2)
    print(f"  wrote {md_path}", flush=True)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Calibration probe: per-player variance-modulated quantile bands")
    ap.add_argument("--max-games", type=int, default=0)
    args = ap.parse_args()
    warnings.filterwarnings("ignore")
    run_probe(max_games=args.max_games)
    return 0


if __name__ == "__main__":
    sys.exit(main())
