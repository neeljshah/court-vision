"""scripts/improve_loop/scaffold.py -- generic probe scaffold.

A probe is a callable that, given a snapshot and a model, returns
{(pid, stat): projected_final}. The scaffold compares baseline vs treatment
on the 1508-game retro corpus, runs walk-forward 4-fold on PTS, and writes
a markdown report. Probes are ~30 LOC instead of 200.

Usage:
    from scripts.improve_loop.scaffold import run_endq3_probe, BASELINE
    def my_treatment(snap):
        # ... project endQ3 → {(pid, stat): final}
        return projs
    run_endq3_probe("110_demo", my_treatment, baseline=BASELINE)

Ship gate (configurable): WF 4/4 PTS folds <= 0 AND mean PTS delta <=
ship_pts AND >=ship_wins/7 stats with single-split delta <= ship_per_stat.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field, asdict
from typing import Callable, Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import retro_inplay_mae as v1  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

# Default endQ3 baseline = current production (live_engine post-cycle-110).
BASELINE_KIND = "live_engine_post_110"


def _mae(xs: List[float]) -> float:
    return (sum(xs) / len(xs)) if xs else float("nan")


def _live_engine_baseline(snap: dict) -> Dict[Tuple[int, str], float]:
    """Current production projection at endQ3 (includes all wired overrides:
    period_heads, learned_q4_minutes, quantile_bands). This is the baseline
    that cycle 110+ probes must beat."""
    from src.prediction.live_engine import project_from_snapshot
    rows = project_from_snapshot(snap)
    out: Dict[Tuple[int, str], float] = {}
    for r in rows:
        try:
            pid = int(r.get("player_id"))
        except (TypeError, ValueError):
            continue
        out[(pid, r["stat"])] = float(r["projected_final"])
    return out


def _cycle88_baseline(snap: dict) -> Dict[Tuple[int, str], float]:
    """Cycle-88 baseline (predict_in_game.project_snapshot without overrides).
    Use as a SANITY anchor only -- ship gate is against live_engine."""
    return v1.project_snapshot_to_finals(snap)


BASELINE = _live_engine_baseline
BASELINE_CYCLE88 = _cycle88_baseline


@dataclass
class ProbeResult:
    name: str
    n_games: int
    per_stat: List[Dict] = field(default_factory=list)  # [{stat,n,base,treat,delta}]
    wf_folds: List[Dict] = field(default_factory=list)  # [{fold,games,base,treat,delta}]
    ship: bool = False
    ship_reason: str = ""

    def to_md(self) -> str:
        lines = [f"# probe {self.name} -- improve_loop", "",
                 f"**Games:** {self.n_games}", ""]
        lines.append("## Single-split endQ3 MAE")
        lines.append("")
        lines.append("| stat | n | baseline | treat | delta | win |")
        lines.append("|------|---|----------|-------|-------|-----|")
        for r in self.per_stat:
            mark = "Y" if r["delta"] <= -0.005 else "."
            lines.append(f"| {r['stat']} | {r['n']} | {r['base']:.4f} | "
                         f"{r['treat']:.4f} | {r['delta']:+.4f} | {mark} |")
        lines.append("")
        lines.append("## Walk-forward 4-fold (PTS)")
        lines.append("")
        lines.append("| fold | games | base | treat | delta |")
        lines.append("|------|-------|------|-------|-------|")
        for f in self.wf_folds:
            lines.append(f"| {f['fold']} | {f['games']} | {f['base']:.4f} | "
                         f"{f['treat']:.4f} | {f['delta']:+.4f} |")
        lines.append("")
        lines.append("## Verdict")
        lines.append("")
        lines.append(f"- **{'SHIP' if self.ship else 'REJECT'}**: {self.ship_reason}")
        lines.append("")
        return "\n".join(lines) + "\n"


def run_endq3_probe(
    name: str,
    treatment: Callable[[dict], Dict[Tuple[int, str], float]],
    baseline: Callable[[dict], Dict[Tuple[int, str], float]] = BASELINE,
    max_games: Optional[int] = None,
    ship_pts: float = -0.005,
    ship_per_stat: float = -0.005,
    ship_wins: int = 4,
    output_md: Optional[str] = None,
    qstats_df=None,
    change_type: str = "model",
    clv_metrics: Optional[dict] = None,
) -> ProbeResult:
    """Run a probe on the endQ3 corpus and write a result markdown.

    Args:
        name: e.g. "113_learned_min_endq2"
        treatment: snap -> {(pid, stat): projected_final}
        baseline: snap -> {(pid, stat): projected_final}. Default = live_engine.
        ship_pts: SHIP iff WF mean PTS delta <= ship_pts.
        ship_per_stat: stat counts as a "win" if single-split delta <= here.
        ship_wins: SHIP needs >= ship_wins / 7 stats winning.
    """
    if qstats_df is None:
        qstats_df = v1.load_quarter_stats()
    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]

    err_b: Dict[str, Dict[str, List[float]]] = {gid: {s: [] for s in STATS} for gid in games}
    err_t: Dict[str, Dict[str, List[float]]] = {gid: {s: [] for s in STATS} for gid in games}

    for gid in games:
        snap = v1.build_snapshot(gid, "endQ3", qstats_df)
        if snap is None:
            continue
        actuals = v1.actuals_for_game(gid, qstats_df)
        b = baseline(snap)
        t = treatment(snap)
        for (pid, stat), bval in b.items():
            actual = actuals.get((pid, stat))
            tval = t.get((pid, stat))
            if actual is None or tval is None:
                continue
            err_b[gid][stat].append(abs(bval - actual))
            err_t[gid][stat].append(abs(tval - actual))

    per_stat = []
    n_wins = 0
    for s in STATS:
        b_all: List[float] = []
        t_all: List[float] = []
        for gid in games:
            b_all.extend(err_b[gid][s])
            t_all.extend(err_t[gid][s])
        bm, tm = _mae(b_all), _mae(t_all)
        d = tm - bm
        per_stat.append({"stat": s, "n": len(b_all), "base": bm, "treat": tm, "delta": d})
        if d <= ship_per_stat:
            n_wins += 1

    n = len(games)
    fold_size = max(1, n // 4)
    wf_folds = []
    for fi in range(4):
        lo = fi * fold_size
        hi = n if fi == 3 else (fi + 1) * fold_size
        fg = games[lo:hi]
        b_pts: List[float] = []
        t_pts: List[float] = []
        for gid in fg:
            b_pts.extend(err_b[gid]["pts"])
            t_pts.extend(err_t[gid]["pts"])
        bm, tm = _mae(b_pts), _mae(t_pts)
        wf_folds.append({"fold": fi + 1, "games": len(fg),
                         "base": bm, "treat": tm, "delta": tm - bm})

    pts_d = per_stat[0]["delta"]
    wf_mean = sum(f["delta"] for f in wf_folds) / 4.0
    wf_all_nonpos = all(f["delta"] <= 0 for f in wf_folds)

    ship = (wf_all_nonpos and wf_mean <= ship_pts and pts_d < 0
            and n_wins >= ship_wins)
    # --- R9 C8 CLV ship-gate composition (legacy probes pass through) ---
    from scripts.improve_loop.clv_gate import check_clv_gate, compose_with_mae
    _clv_ok, _clv_reason = check_clv_gate({"clv_metrics": clv_metrics or {}}, change_type)
    ship, _composed_reason = compose_with_mae(ship, "MAE gate", _clv_ok, _clv_reason, change_type)
    # --- end R9 C8 ---

    if ship:
        reason = (f"WF 4/4 OK, mean PTS {wf_mean:+.4f} <= {ship_pts}, "
                  f"{n_wins}/7 stats win, PTS strictly down")
    else:
        causes = []
        if not wf_all_nonpos:
            causes.append("WF not 4/4")
        if wf_mean > ship_pts:
            causes.append(f"WF mean PTS {wf_mean:+.4f} > {ship_pts}")
        if pts_d >= 0:
            causes.append(f"single-split PTS {pts_d:+.4f}")
        if n_wins < ship_wins:
            causes.append(f"only {n_wins}/7 stats win")
        if not _clv_ok:
            causes.append(f"CLV: {_clv_reason}")
        reason = "; ".join(causes) if causes else _composed_reason

    result = ProbeResult(
        name=name, n_games=len(games),
        per_stat=per_stat, wf_folds=wf_folds,
        ship=ship, ship_reason=reason,
    )

    out_dir = os.path.join(PROJECT_DIR, "scripts", "_results")
    os.makedirs(out_dir, exist_ok=True)
    md_path = output_md or os.path.join(out_dir, f"improve_{name}.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(result.to_md())

    json_path = os.path.splitext(md_path)[0] + ".json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(asdict(result), fh, indent=2)

    print(f"  [{name}] SHIP={ship}  PTS={pts_d:+.4f}  wins={n_wins}/7  "
          f"WF_mean={wf_mean:+.4f}")
    return result


def run_point_probe(
    point: str,
    name: str,
    treatment: Callable[[dict], Dict[Tuple[int, str], float]],
    baseline: Callable[[dict], Dict[Tuple[int, str], float]] = BASELINE,
    **kw,
) -> ProbeResult:
    """Same as run_endq3_probe but for endQ1 / endQ2 snapshots."""
    qstats_df = v1.load_quarter_stats()
    # Filter qstats_df scope is fine -- build_snapshot uses point arg.
    # We just need to wrap baseline/treatment to project at this point.
    games = sorted(qstats_df["game_id"].unique().tolist())
    max_games = kw.pop("max_games", None)
    if max_games:
        games = games[:max_games]
    err_b = {gid: {s: [] for s in STATS} for gid in games}
    err_t = {gid: {s: [] for s in STATS} for gid in games}
    for gid in games:
        snap = v1.build_snapshot(gid, point, qstats_df)
        if snap is None:
            continue
        actuals = v1.actuals_for_game(gid, qstats_df)
        b = baseline(snap)
        t = treatment(snap)
        for (pid, stat), bval in b.items():
            actual = actuals.get((pid, stat))
            tval = t.get((pid, stat))
            if actual is None or tval is None:
                continue
            err_b[gid][stat].append(abs(bval - actual))
            err_t[gid][stat].append(abs(tval - actual))
    # Reuse the rest of run_endq3_probe via a tiny helper -- just inline.
    per_stat = []
    n_wins = 0
    ship_per_stat = kw.get("ship_per_stat", -0.005)
    for s in STATS:
        b_all, t_all = [], []
        for gid in games:
            b_all.extend(err_b[gid][s])
            t_all.extend(err_t[gid][s])
        bm, tm = _mae(b_all), _mae(t_all)
        d = tm - bm
        per_stat.append({"stat": s, "n": len(b_all), "base": bm, "treat": tm, "delta": d})
        if d <= ship_per_stat:
            n_wins += 1
    n = len(games)
    fs = max(1, n // 4)
    wf_folds = []
    for fi in range(4):
        lo = fi * fs
        hi = n if fi == 3 else (fi + 1) * fs
        fg = games[lo:hi]
        b_pts, t_pts = [], []
        for gid in fg:
            b_pts.extend(err_b[gid]["pts"])
            t_pts.extend(err_t[gid]["pts"])
        bm, tm = _mae(b_pts), _mae(t_pts)
        wf_folds.append({"fold": fi + 1, "games": len(fg),
                         "base": bm, "treat": tm, "delta": tm - bm})
    pts_d = per_stat[0]["delta"]
    wf_mean = sum(f["delta"] for f in wf_folds) / 4.0
    wf_all_nonpos = all(f["delta"] <= 0 for f in wf_folds)
    ship_pts = kw.get("ship_pts", -0.005)
    ship_wins = kw.get("ship_wins", 4)
    ship = (wf_all_nonpos and wf_mean <= ship_pts and pts_d < 0
            and n_wins >= ship_wins)
    reason = (f"WF mean PTS {wf_mean:+.4f}, {n_wins}/7 wins"
              if ship else f"fail: WF={wf_all_nonpos}, mean={wf_mean:+.4f}, "
                          f"PTS={pts_d:+.4f}, wins={n_wins}")
    result = ProbeResult(name=name, n_games=len(games),
                         per_stat=per_stat, wf_folds=wf_folds,
                         ship=ship, ship_reason=reason)
    out_dir = os.path.join(PROJECT_DIR, "scripts", "_results")
    os.makedirs(out_dir, exist_ok=True)
    md_path = kw.get("output_md", os.path.join(out_dir, f"improve_{name}.md"))
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(result.to_md())
    json_path = os.path.splitext(md_path)[0] + ".json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(asdict(result), fh, indent=2)
    print(f"  [{name} @ {point}] SHIP={ship}  PTS={pts_d:+.4f}  "
          f"wins={n_wins}/7  WF_mean={wf_mean:+.4f}")
    return result
