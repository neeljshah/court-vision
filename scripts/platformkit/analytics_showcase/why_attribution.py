"""Why-attribution: explain any in-game win-prob move by the state transition
that produced it.

Reads the committed state-conditioned calibration artifact
(out/state_conditioned_calibration.json), which buckets every graded ingame
prediction by (sport x game-state time bucket x model_prob band) and records
mean_y -- the empirically-realized win rate for that state. The expected
win-prob impact of a state transition A -> B is then mean_y(B) - mean_y(A):
"the game was in state A (calibrated win prob mean_y(A)); it moved to state B
(mean_y(B)); the move was worth that difference in win-prob points."

Transitions are restricted to ADJACENT time buckets (early->mid->late for mlb,
consecutive 15-min segments for soccer) so each row reads as a real forward
move, e.g. "late-innings .4-.6 -> .2-.4 costs X win-prob points on average."

This is NOT observed transition frequencies (that needs per-game trajectories);
it is the calibrated win-prob difference between the two states, which is what
attributes a move once you know which buckets it crossed.

NBA is not buildable here: the only in-game NBA artifact is the checkpoint
bench (last_run_ingame_nba_winprob.json), which reports checkpoint Brier but no
per-state-bucket realized win rate -- so it carries no mean_y to difference.
Recorded honestly as not_buildable (a null is a success).

edge_claimed=False always. Calibration attribution, never a $/ROI claim.

Usage:
    python -m scripts.platformkit.analytics_showcase.why_attribution
    python -m scripts.platformkit.analytics_showcase.why_attribution --check
"""
import argparse
import json
import os
from typing import Any, Dict, List, Optional, Tuple

try:  # -m package invocation (check_all) vs bare-script invocation
    from scripts.platformkit.analytics_showcase._clone_safe import verify_recorded_artifact
except ImportError:  # pragma: no cover - fallback for bare-script runs
    from _clone_safe import verify_recorded_artifact

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
IN_JSON = os.path.join(ROOT, "scripts", "platformkit", "analytics_showcase", "out", "state_conditioned_calibration.json")
OUT_JSON = os.path.join(ROOT, "scripts", "platformkit", "analytics_showcase", "out", "why_attribution.json")
OUT_PNG = os.path.join(ROOT, "docs", "img", "why_attribution.png")

# Ordered forward game-state time buckets, matching state_conditioned_calibration vocab.
TIME_ORDER: Dict[str, List[str]] = {
    "mlb": ["early(inn1-3)", "mid(inn4-6)", "late(inn7+)"],
    "soccer_intl": ["0-15", "15-30", "30-45", "45-60", "60-75", "75-90+"],
}
PROB_ORDER: List[str] = ["0-.2", ".2-.4", ".4-.6", ".6-.8", ".8-1"]
MIN_SUPPORT = 30  # floor: skip buckets thinner than this (mean_y too noisy to difference)


def _model_lookup(buckets: List[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """(time_bucket, prob_bucket) -> bucket, for source==model buckets meeting the
    support floor. Later duplicates would overwrite, but the source artifact has one
    model row per (time,prob) pair."""
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for b in buckets:
        if b.get("source") != "model":
            continue
        if b.get("mean_y") is None or b.get("n", 0) < MIN_SUPPORT:
            continue
        out[(b["time_bucket"], b["prob_bucket"])] = b
    return out


def build_transitions(sport: str, buckets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every adjacent-time state transition and its calibrated win-prob delta."""
    order = TIME_ORDER[sport]
    lut = _model_lookup(buckets)
    rows: List[Dict[str, Any]] = []
    for i in range(len(order) - 1):
        t_src, t_dst = order[i], order[i + 1]
        for pb_src in PROB_ORDER:
            src = lut.get((t_src, pb_src))
            if src is None:
                continue
            for pb_dst in PROB_ORDER:
                dst = lut.get((t_dst, pb_dst))
                if dst is None:
                    continue
                delta = round(dst["mean_y"] - src["mean_y"], 4)
                rows.append({
                    "sport": sport,
                    "from": {"time": t_src, "prob": pb_src, "mean_y": src["mean_y"], "n": src["n"]},
                    "to": {"time": t_dst, "prob": pb_dst, "mean_y": dst["mean_y"], "n": dst["n"]},
                    "winprob_delta": delta,
                    "min_support_n": min(src["n"], dst["n"]),
                })
    return rows


def make_chart(result: Dict[str, Any], out_png: str) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:  # pragma: no cover
        return False

    sports = [s for s, v in result["sports"].items() if v.get("transitions")]
    if not sports:
        return False
    fig, axes = plt.subplots(1, len(sports), figsize=(6.5 * len(sports), 6), squeeze=False)
    for ax, sport in zip(axes[0], sports):
        trans = result["sports"][sport]["transitions"]
        # rows = source (time:prob), cols = destination prob band (dest time = src time + 1).
        src_keys = sorted({(t["from"]["time"], t["from"]["prob"]) for t in trans},
                          key=lambda k: (TIME_ORDER[sport].index(k[0]), PROB_ORDER.index(k[1])))
        grid = np.full((len(src_keys), len(PROB_ORDER)), np.nan)
        row_idx = {k: i for i, k in enumerate(src_keys)}
        for t in trans:
            r = row_idx[(t["from"]["time"], t["from"]["prob"])]
            c = PROB_ORDER.index(t["to"]["prob"])
            grid[r, c] = t["winprob_delta"]
        im = ax.imshow(grid, cmap="RdBu", vmin=-1, vmax=1, aspect="auto")
        ax.set_xticks(range(len(PROB_ORDER)))
        ax.set_xticklabels([f"->{p}" for p in PROB_ORDER], fontsize=8)
        ax.set_yticks(range(len(src_keys)))
        ax.set_yticklabels([f"{t}:{p}" for t, p in src_keys], fontsize=7)
        ax.set_title(sport)
        ax.set_xlabel("destination prob band (next time bucket)")
        for r in range(len(src_keys)):
            for c in range(len(PROB_ORDER)):
                if not np.isnan(grid[r, c]):
                    ax.text(c, r, f"{grid[r, c]:+.2f}", ha="center", va="center", fontsize=6)
        fig.colorbar(im, ax=ax, shrink=0.8, label="calibrated win-prob delta")
    axes[0][0].set_ylabel("source state (time:model_prob band)")
    fig.suptitle("Why-attribution: calibrated win-prob delta of adjacent-time state transitions")
    fig.text(0.5, 0.005,
             "Source: out/state_conditioned_calibration.json (mean_y per state). "
             "delta = mean_y(dest) - mean_y(src). Calibration-only, edge_claimed=False.",
             ha="center", fontsize=7, color="gray")
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    fig.savefig(out_png, dpi=130)
    plt.close(fig)
    return True


def _as_of(cal: Dict[str, Any]) -> Optional[str]:
    return cal.get("as_of") or cal.get("generated_at")


def run() -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "edge_claimed": False,
        "source_artifact": "out/state_conditioned_calibration.json",
        "method": (
            "For each adjacent-time state transition A->B (source==model buckets, "
            "n>={}), attribute win-prob impact as mean_y(B) - mean_y(A) where mean_y "
            "is the state's calibrated realized win rate.".format(MIN_SUPPORT)
        ),
        "assumptions": [
            "mean_y (realized win rate per bucket) is the state's calibrated win prob.",
            "Transitions restricted to consecutive time buckets; no skipping.",
            "Not observed transition frequencies -- the win-prob DIFFERENCE between two states.",
            "Buckets thinner than n={} are dropped (noisy mean_y).".format(MIN_SUPPORT),
        ],
        "sports": {},
        "skipped": [],
    }

    if not os.path.exists(IN_JSON):
        result["status"] = "not_buildable"
        result["reason"] = "state_conditioned_calibration.json absent; cannot derive state transitions"
        os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        return result

    with open(IN_JSON, encoding="utf-8") as f:
        cal = json.load(f)
    result["source_as_of"] = _as_of(cal)

    all_trans: List[Dict[str, Any]] = []
    for sport in TIME_ORDER:
        sport_cal = cal.get("sports", {}).get(sport)
        if not sport_cal or not sport_cal.get("buckets"):
            result["skipped"].append({"sport": sport, "reason": "no buckets in source artifact"})
            continue
        trans = build_transitions(sport, sport_cal["buckets"])
        if not trans:
            result["skipped"].append({"sport": sport, "reason": "no adjacent-time bucket pairs met support floor"})
            continue
        all_trans.extend(trans)
        result["sports"][sport] = {"n_transitions": len(trans), "transitions": trans}

    # NBA: only the checkpoint bench exists, which has no per-state mean_y to difference.
    result["skipped"].append({
        "sport": "nba",
        "reason": "only last_run_ingame_nba_winprob.json (checkpoint Brier) exists; "
                  "no per-state-bucket realized win rate (mean_y) to attribute transitions",
    })

    biggest_drops = sorted(all_trans, key=lambda r: r["winprob_delta"])[:10]
    biggest_gains = sorted(all_trans, key=lambda r: r["winprob_delta"], reverse=True)[:10]
    result["biggest_drops"] = biggest_drops
    result["biggest_gains"] = biggest_gains

    if all_trans:
        drop = biggest_drops[0]
        result["verdict"] = (
            "Largest calibrated win-prob drop: {sport} {ft}:{fp} -> {tt}:{tp} "
            "= {d:+.4f} (min support n={n}). Any in-game move decomposes into the "
            "adjacent-time bucket transition it crossed.".format(
                sport=drop["sport"], ft=drop["from"]["time"], fp=drop["from"]["prob"],
                tt=drop["to"]["time"], tp=drop["to"]["prob"], d=drop["winprob_delta"],
                n=drop["min_support_n"])
        )
    else:
        result["verdict"] = "No sport produced adjacent-time transitions above the support floor."

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    result["plot_written"] = make_chart(result, OUT_PNG) if all_trans else False
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return result


def check() -> None:
    """Verify the transition delta reconstructs from bucket mean_y and rankings sort.
    Falls back to the committed artifact when the source calibration artifact is
    absent (clone-safe)."""
    def validate(d: Dict[str, Any]) -> None:
        assert d.get("edge_claimed") is False
        if d.get("status") == "not_buildable":
            return
        drops = d.get("biggest_drops", [])
        assert drops, "expected biggest_drops"
        assert all(drops[i]["winprob_delta"] <= drops[i + 1]["winprob_delta"]
                   for i in range(len(drops) - 1)), "biggest_drops not ascending"
        t = drops[0]
        recon = round(t["to"]["mean_y"] - t["from"]["mean_y"], 4)
        assert abs(recon - t["winprob_delta"]) < 1e-9, (recon, t["winprob_delta"])

    if not os.path.exists(IN_JSON):
        verify_recorded_artifact(OUT_JSON, validate, "why_attribution")
        return
    result = run()
    validate(result)
    assert os.path.exists(OUT_JSON)
    print("OK: why_attribution self-check passed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        check()
    else:
        res = run()
        print(json.dumps({k: v for k, v in res.items() if k != "sports"}, indent=2)[:2500])
