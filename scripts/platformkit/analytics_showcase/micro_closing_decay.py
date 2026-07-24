"""Market microstructure: how much sharper is the CLOSE than earlier prices?

"Freshness is the moat," quantified. Per game we take the consensus devigged
market P(home win) at four pre-start horizons -- T-24h/T-6h/T-1h/close -- and
score each horizon's Brier + log-loss vs the settled outcome. A Brier that
falls toward tip-off is the pre-game information gap (freshness), measured.

DATA (READ-ONLY, gitignored -- absent from a fresh clone):
  data/cache/line_history/<sport>/*.jsonl (captured_at, commence_time, side,
  devigged_prob, game_id=ESPN id), joined by ESPN event_id to:
  wnba -> data/domains/wnba/espn_scoreboard.parquet (home_win);
  soccer_intl -> data/domains/soccer_intl/espn_finals.parquet (scores). Only
  these two reconcile to an on-disk ESPN-keyed outcome table over the window;
  the rest are reported not_joinable with a reason, never faked.

HONESTY (binding): calibration-only. edge_claimed=False. No $/ROI. Small
per-bucket n is labelled underpowered; an honest not_joinable is a SUCCESS.

Usage: python -m scripts.platformkit.analytics_showcase.micro_closing_decay [--check]
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from scripts.platformkit.analytics_showcase._clone_safe import verify_recorded_artifact
except ImportError:
    from _clone_safe import verify_recorded_artifact

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
LH_DIR = os.path.join(REPO_ROOT, "data", "cache", "line_history")
OUT_JSON = os.path.join(REPO_ROOT, "scripts", "platformkit", "analytics_showcase", "out", "micro_closing_decay.json")
OUT_PNG = os.path.join(REPO_ROOT, "docs", "img", "micro_closing_decay.png")

# (label, target hours-before-start, accept window [lo, hi) in hours).
ANCHORS: Tuple[Tuple[str, float, Tuple[float, float]], ...] = (
    ("T-24h", 24.0, (12.0, 48.0)),
    ("T-6h", 6.0, (3.0, 12.0)),
    ("T-1h", 1.0, (0.5, 3.0)),
    ("close", 0.0, (0.0, 0.5)),
)
_ANCHOR_LABELS = [a[0] for a in ANCHORS]
MAX_HORIZON_H = 72.0   # ignore snapshots captured >3 days out (stale/opening noise)
MIN_N_POWERED = 20     # per-bucket floor below which the bucket is 'underpowered'

# sport -> (outcome parquet, mode). mode 'home_win' reads that column;
# 'scores' derives home_win from home_score>away_score (completed rows only).
JOINABLE: Dict[str, Tuple[str, str]] = {
    "wnba": (os.path.join(REPO_ROOT, "data", "domains", "wnba", "espn_scoreboard.parquet"), "home_win"),
    "soccer_intl": (os.path.join(REPO_ROOT, "data", "domains", "soccer_intl", "espn_finals.parquet"), "scores"),
}
NOT_JOINABLE: Dict[str, str] = {
    "nba": "line_history covers the 2026 window; no ESPN-keyed NBA outcome table on disk spans it (games.parquet uses NBA-stats ids).",
    "mlb": "line_history uses ESPN/odds-api ids; games.parquet uses date-team keys (20100404-BOS-NYY-1) -- 0 direct joins.",
    "soccer": "club-league feed with only ~20 games and no on-disk ESPN-keyed outcome table.",
    "tennis": "player-hashed match ids; no ESPN-keyed match-outcome table on disk.",
    "kbo": "line_history rows carry no commence_time (game_id=0) -- hours-to-start is undefined.",
    "npb": "line_history rows carry no commence_time (game_id=0) -- hours-to-start is undefined.",
}

def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s or not isinstance(s, str):
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None

def load_home_snapshots(sport: str) -> Tuple[Dict[str, List[Tuple[float, float]]], Optional[str], Dict[str, Any]]:
    """Return {game_id: [(horizon_hours, devigged_home_prob), ...]} for pregame
    home-side moneyline snapshots, the max captured-at date seen (as_of), and the
    observation window (min/max captured_at actually read from line_history)."""
    by_game: Dict[str, List[Tuple[float, float]]] = {}
    max_cap: Optional[datetime] = None
    min_cap: Optional[datetime] = None
    n_files = 0
    for path in glob.glob(os.path.join(LH_DIR, sport, "*.jsonl")):
        n_files += 1
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                if d.get("market_type") != "moneyline" or d.get("side") != "home":
                    continue
                p = d.get("devigged_prob")
                gid = d.get("game_id")
                if p is None or gid in (None, "", "0"):
                    continue
                ct = _parse_dt(d.get("commence_time"))
                cap = _parse_dt(d.get("captured_at"))
                if ct is None or cap is None:
                    continue
                if max_cap is None or cap > max_cap:
                    max_cap = cap
                if min_cap is None or cap < min_cap:
                    min_cap = cap
                horizon = (ct - cap).total_seconds() / 3600.0
                if horizon < 0.0 or horizon > MAX_HORIZON_H:
                    continue
                by_game.setdefault(str(gid), []).append((horizon, float(p)))
    as_of = max_cap.date().isoformat() if max_cap else None
    window: Dict[str, Any] = {
        "source": "data/cache/line_history/%s/*.jsonl (captured_at of every snapshot read)" % sport,
        "first_captured_at": min_cap.date().isoformat() if min_cap else None,
        "last_captured_at": as_of,
        "span_days": (round((max_cap - min_cap).total_seconds() / 86400.0, 1)
                      if (min_cap and max_cap) else None),
        "n_daily_files": n_files,
        "note": ("This is the FULL local capture window, not a season. Counts below are large "
                 "because capture is dense (many books x many ticks per game), not because the "
                 "history is long."),
    }
    return by_game, as_of, window

def load_outcomes(sport: str) -> Dict[str, int]:
    """{ESPN event_id (str): home_win 0/1} for the sport's outcome table."""
    import pandas as pd
    path, mode = JOINABLE[sport]
    df = pd.read_parquet(path)
    out: Dict[str, int] = {}
    for _, r in df.iterrows():
        eid = str(r["event_id"])
        if mode == "home_win":
            hw = r.get("home_win")
            if hw is None or (isinstance(hw, float) and math.isnan(hw)):
                continue
            out[eid] = int(hw)
        else:  # scores
            if not bool(r.get("completed", True)):
                continue
            hs, as_ = r.get("home_score"), r.get("away_score")
            if hs is None or as_ is None or (isinstance(hs, float) and math.isnan(hs)):
                continue
            out[eid] = int(hs > as_)  # binary event "home team wins" (draw -> 0)
    return out

def bucket_prob(snaps: List[Tuple[float, float]], window: Tuple[float, float]) -> Optional[float]:
    """Consensus (median) devigged home prob among snapshots whose horizon falls
    in [lo, hi); None if the game has no snapshot in that window."""
    lo, hi = window
    ps = [p for h, p in snaps if lo <= h < hi]
    return statistics.median(ps) if ps else None

def score_bucket(pairs: List[Tuple[float, int]]) -> Dict[str, Any]:
    n = len(pairs)
    if n == 0:
        return {"n": 0}
    brier = sum((p - y) ** 2 for p, y in pairs) / n
    ll = 0.0
    for p, y in pairs:
        pc = min(max(p, 1e-6), 1.0 - 1e-6)
        ll += -(y * math.log(pc) + (1 - y) * math.log(1.0 - pc))
    return {
        "n": n,
        "brier": round(brier, 6),
        "logloss": round(ll / n, 6),
        "mean_prob": round(sum(p for p, _ in pairs) / n, 4),
        "underpowered": n < MIN_N_POWERED,
    }

def analyze_sport(sport: str) -> Dict[str, Any]:
    by_game, as_of, window = load_home_snapshots(sport)
    outcomes = load_outcomes(sport)
    # per-anchor (prob, outcome) pairs, plus per-game close & T-24h for pairing.
    per_anchor: Dict[str, List[Tuple[float, int]]] = {a: [] for a in _ANCHOR_LABELS}
    paired: List[Tuple[float, float, int]] = []  # (p_t24, p_close, y)
    joined_games = 0
    for gid, snaps in by_game.items():
        if gid not in outcomes:
            continue
        joined_games += 1
        y = outcomes[gid]
        probs: Dict[str, Optional[float]] = {}
        for label, _tgt, accept_window in ANCHORS:
            p = bucket_prob(snaps, accept_window)
            probs[label] = p
            if p is not None:
                per_anchor[label].append((p, y))
        if probs["T-24h"] is not None and probs["close"] is not None:
            paired.append((probs["T-24h"], probs["close"], y))
    buckets = {a: score_bucket(per_anchor[a]) for a in _ANCHOR_LABELS}
    pair_out: Dict[str, Any] = {"n": len(paired)}
    if paired:
        b_t24 = sum((p - y) ** 2 for p, _c, y in paired) / len(paired)
        b_cl = sum((c - y) ** 2 for _p, c, y in paired) / len(paired)
        pair_out.update({
            "brier_t24h": round(b_t24, 6),
            "brier_close": round(b_cl, 6),
            "brier_delta_t24h_minus_close": round(b_t24 - b_cl, 6),
            "close_sharper": b_cl < b_t24,
            "underpowered": len(paired) < MIN_N_POWERED,
        })
    return {"as_of": as_of, "observation_window": window, "n_games_joined": joined_games,
            "buckets": buckets, "close_vs_t24h_paired": pair_out}

def build_verdict(sports: Dict[str, Any]) -> str:
    lines: List[str] = []
    for sport, res in sports.items():
        b = res["buckets"]
        seq = [(a, b[a].get("brier")) for a in _ANCHOR_LABELS if b[a].get("brier") is not None]
        if len(seq) < 2:
            lines.append(f"{sport}: too few populated horizons to compare ({res['n_games_joined']} games).")
            continue
        first_lbl, first_b = seq[0]
        last_lbl, last_b = seq[-1]
        drop = first_b - last_b
        pw = "" if not b[last_lbl].get("underpowered") else " (UNDERPOWERED)"
        direction = "sharpens toward the close" if drop > 0 else "does NOT sharpen toward the close"
        lines.append(
            f"{sport}: Brier {direction} -- {first_lbl}={first_b:.4f} -> {last_lbl}={last_b:.4f} "
            f"(delta={drop:+.4f}, n_games={res['n_games_joined']}){pw}."
        )
    return " ".join(lines) if lines else "No sport was joinable."

def make_plot(result: Dict[str, Any]) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    fig, ax = plt.subplots(figsize=(8, 5))
    xs = list(range(len(_ANCHOR_LABELS)))
    plotted = False
    for sport, res in result["sports"].items():
        b = res["buckets"]
        ys = [b[a].get("brier") for a in _ANCHOR_LABELS]
        pts = [(x, y) for x, y in zip(xs, ys) if y is not None]
        if len(pts) < 2:
            continue
        ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o",
                label=f"{sport} (n={res['n_games_joined']})")
        plotted = True
    ax.set_xticks(xs)
    ax.set_xticklabels(_ANCHOR_LABELS)
    ax.set_xlabel("horizon before tip-off (later = closer to start)")
    ax.set_ylabel("Brier (market devigged P(home) vs outcome)")
    ax.set_title("Closing-price decay: is the market sharper as tip-off nears?")
    ax.grid(True, alpha=0.3)
    if plotted:
        ax.legend(fontsize=8)
    aos = {s: r.get("as_of") for s, r in result["sports"].items()}
    ow = result.get("observation_window", {})
    fig.text(0.5, 0.005,
             "Source: data/cache/line_history/{wnba,soccer_intl} devigged moneyline snapshots joined "
             f"to ESPN-keyed outcomes. Observation window {ow.get('first_captured_at')} .. "
             f"{ow.get('last_captured_at')} (capture window, not a season). as_of={aos}. "
             "Calibration-only, edge_claimed=False.",
             ha="center", fontsize=6.5, color="gray")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    fig.savefig(OUT_PNG, dpi=140)
    plt.close(fig)
    return True

def run() -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "edge_claimed": False,
        "method": ("Consensus (median) devigged market P(home win) bucketed by hours-to-start into "
                   "T-24h/T-6h/T-1h/close, scored Brier + log-loss vs the settled ESPN outcome; "
                   "paired within-game close-vs-T-24h delta."),
        "assumptions": [
            "Market prob = home-side devigged_prob from line_history (consensus median across books/ticks in each horizon window).",
            "Binary event scored is 'home team wins'; a soccer draw counts as home-loss (y=0).",
            "Snapshots >72h before start are ignored (opening/stale noise); only 0<=horizon<=72h used.",
            f"Per-bucket n<{MIN_N_POWERED} flagged underpowered; single capture window -- provisional, not durable.",
        ],
        "anchors": [{"label": a, "target_hours_before_start": t, "accept_window_h": list(w)} for a, t, w in ANCHORS],
        "sports": {},
        "not_joinable": NOT_JOINABLE,
    }
    for sport in JOINABLE:
        result["sports"][sport] = analyze_sport(sport)
    wins = [r["observation_window"] for r in result["sports"].values()]
    firsts = [w["first_captured_at"] for w in wins if w.get("first_captured_at")]
    lasts = [w["last_captured_at"] for w in wins if w.get("last_captured_at")]
    result["observation_window"] = {
        "corpus": "data/cache/line_history/<sport>/*.jsonl",
        "first_captured_at": min(firsts) if firsts else None,
        "last_captured_at": max(lasts) if lasts else None,
        "span_days": max([w["span_days"] for w in wins if w.get("span_days") is not None] or [None]),
        "note": ("Union of the per-sport capture windows below. This is a single short capture "
                 "window, not a season or multi-season history -- every Brier here is provisional "
                 "and describes only these dates."),
    }
    result["verdict"] = build_verdict(result["sports"])
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    result["plot_written"] = make_plot(result)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return result

def _local_data_present() -> bool:
    return any(glob.glob(os.path.join(LH_DIR, s, "*.jsonl")) for s in JOINABLE)

def check() -> None:
    """Validate structure + Brier bounds. Clone-safe: with local data absent,
    verify the committed artifact instead of clobbering it with an empty run."""
    def validate(d: Dict[str, Any]) -> None:
        assert d.get("edge_claimed") is False, "edge_claimed must be False"
        assert d.get("sports"), "no sports in artifact"
        assert d.get("not_joinable"), "not_joinable list missing"
        ow = d.get("observation_window") or {}
        assert ow.get("first_captured_at") and ow.get("last_captured_at"), \
            "observation_window must declare first/last captured_at"
        for sport, res in d["sports"].items():
            sw = res.get("observation_window") or {}
            assert sw.get("first_captured_at") and sw.get("last_captured_at"), \
                f"{sport}: per-sport observation_window missing"
            for lbl, bk in res["buckets"].items():
                if bk.get("n"):
                    assert 0.0 <= bk["brier"] <= 1.0, f"{sport}/{lbl} Brier out of [0,1]: {bk['brier']}"
    if not _local_data_present():
        verify_recorded_artifact(OUT_JSON, validate, "micro_closing_decay")
        return
    result = run()
    validate(result)
    assert os.path.exists(OUT_JSON)
    # score_bucket sanity: a perfect predictor has Brier 0, worst has 1.
    assert score_bucket([(1.0, 1), (0.0, 0)])["brier"] == 0.0
    assert score_bucket([(1.0, 0)])["brier"] == 1.0
    print("OK: micro_closing_decay self-check passed")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
    else:
        res = run()
        print(json.dumps({
            "verdict": res["verdict"],
            "plot_written": res["plot_written"],
            "sports_n_games": {s: v.get("n_games_joined") for s, v in res["sports"].items()},
            "not_joinable": list(res["not_joinable"].keys()),
        }, indent=2))
