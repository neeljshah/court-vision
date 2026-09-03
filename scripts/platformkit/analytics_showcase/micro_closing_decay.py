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
import os
from typing import Any, Dict, List, Optional, Tuple

try:
    from scripts.platformkit.analytics_showcase._clone_safe import verify_recorded_artifact
    from scripts.platformkit.analytics_showcase.closing_decay_io import (
        JOINABLE, MIN_N_POWERED, REPO_ROOT, bucket_prob, load_home_snapshots,
        load_outcomes, score_bucket,
    )
except ImportError:
    from _clone_safe import verify_recorded_artifact
    from closing_decay_io import (
        JOINABLE, MIN_N_POWERED, REPO_ROOT, bucket_prob, load_home_snapshots,
        load_outcomes, score_bucket,
    )

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
NOT_JOINABLE: Dict[str, str] = {
    "nba": "line_history covers the 2026 window; no ESPN-keyed NBA outcome table on disk spans it (games.parquet uses NBA-stats ids).",
    "mlb": "line_history uses ESPN/odds-api ids; games.parquet uses date-team keys (20100404-BOS-NYY-1) -- 0 direct joins.",
    "soccer": "club-league feed with only ~20 games and no on-disk ESPN-keyed outcome table.",
    "tennis": "player-hashed match ids; no ESPN-keyed match-outcome table on disk.",
    "kbo": "line_history rows carry no commence_time (game_id=0) -- hours-to-start is undefined.",
    "npb": "line_history rows carry no commence_time (game_id=0) -- hours-to-start is undefined.",
}

def analyze_sport(sport: str) -> Dict[str, Any]:
    by_game, as_of, window = load_home_snapshots(sport)
    outcomes = load_outcomes(sport)
    # Per-anchor pairs plus retained per-game values for the two paired summaries.
    per_anchor: Dict[str, List[Tuple[float, int]]] = {a: [] for a in _ANCHOR_LABELS}
    paired: List[Tuple[float, float, int]] = []  # (p_t24, p_close, y)
    joined_probs: List[Tuple[Dict[str, Optional[float]], int]] = []
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
        joined_probs.append((probs, y))
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
    first_anchor = next((a for a in _ANCHOR_LABELS if buckets[a].get("brier") is not None), None)
    first_paired: List[Tuple[float, float, int]] = []
    if first_anchor is not None:
        for probs, y in joined_probs:
            if probs[first_anchor] is not None and probs["close"] is not None:
                first_paired.append((probs[first_anchor], probs["close"], y))
    first_pair_out: Dict[str, Any] = {"first_anchor": first_anchor, "n": len(first_paired)}
    if first_paired:
        b_first = sum((p - y) ** 2 for p, _c, y in first_paired) / len(first_paired)
        b_close = sum((c - y) ** 2 for _p, c, y in first_paired) / len(first_paired)
        first_pair_out.update({
            "brier_first_anchor": round(b_first, 6),
            "brier_close": round(b_close, 6),
            "brier_delta_first_anchor_minus_close": round(b_first - b_close, 6),
            "close_sharper": b_close < b_first,
            "underpowered": len(first_paired) < MIN_N_POWERED,
        })
    return {"as_of": as_of, "observation_window": window, "n_games_joined": joined_games,
            "buckets": buckets, "close_vs_t24h_paired": pair_out,
            "close_vs_first_paired": first_pair_out}

def build_verdict(sports: Dict[str, Any]) -> str:
    lines: List[str] = []
    for sport, res in sports.items():
        paired = res["close_vs_first_paired"]
        first_anchor = paired.get("first_anchor")
        if first_anchor is None:
            lines.append(f"{sport}: no populated horizon to pair with close (n_games=0).")
            continue
        if paired["n"] == 0:
            lines.append(f"{sport}: no paired games between {first_anchor} and close (n_games=0).")
            continue
        first_b = paired["brier_first_anchor"]
        close_b = paired["brier_close"]
        drop = paired["brier_delta_first_anchor_minus_close"]
        pw = "" if not paired["underpowered"] else " (UNDERPOWERED)"
        direction = "sharpens toward the close" if drop > 0 else "does NOT sharpen toward the close"
        lines.append(
            f"{sport}: Brier {direction} -- {first_anchor}={first_b:.4f} -> close={close_b:.4f} "
            f"(delta={drop:+.4f}, n_games={paired['n']}){pw}."
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
                   "paired within-game close-vs-T-24h and close-vs-first-populated-horizon summaries."),
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
    return any(glob.glob(os.path.join(REPO_ROOT, "data", "cache", "line_history", s, "*.jsonl")) for s in JOINABLE)

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
            paired = res.get("close_vs_first_paired") or {}
            assert "first_anchor" in paired and "n" in paired, \
                f"{sport}: close_vs_first_paired missing anchor or n"
            if paired["n"]:
                assert 0.0 <= paired["brier_first_anchor"] <= 1.0
                assert 0.0 <= paired["brier_close"] <= 1.0
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
