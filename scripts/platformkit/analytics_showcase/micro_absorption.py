"""Market microstructure: pregame price-absorption speed, from our OWN scraped
line history in data/cache/line_history/<sport>/<date>.jsonl.

Each jsonl row is one book snapshot of one (game, market_type, side): it carries
a devigged_prob, a captured_at timestamp, and the game's commence_time. We group
rows into per-(game, market, side, book) SERIES, sort by captured_at, keep only
PREGAME snapshots (captured strictly before commence), and measure three
descriptive properties of how the market moves before tip/first-pitch:

  1. inter-update intervals -- minutes between consecutive pregame snapshots of a
     series (cadence of the feed / how often the price is refreshed).
  2. move magnitude by time-to-start bucket -- mean |delta devigged_prob| between
     consecutive snapshots, bucketed by minutes-to-commence.
  3. final-hour movement share -- fraction of a series' total pregame absolute
     movement that lands in the last hour before start.

This is MARKET SCIENCE / observation only. It describes the market's own
behavior; it is NOT a forecast, a signal, or an edge. edge_claimed=False. No
$/ROI/profit claim -- truth source docs/JOB_EVIDENCE_PACKET.md and
.claude/rules/no-edge-claims.md.

SCOPE / FLOORS (declared, not tuned):
  * A sport is reported only at n >= MIN_MOVES (=20) consecutive pregame move
    pairs; otherwise it is marked insufficient_data.
  * Only rows with captured_at STRICTLY before commence_time count (pregame).
    Snapshots whose file replays already-started games contribute nothing.
  * Single June-July 2026 corpus, single read, no CIs -- descriptive only.
  * Absolute movement is in devigged-probability units, not price/line units.

OBSERVATION WINDOW (declared, not assumed): this feed is a SHORT window, not a
season or a multi-season history. The `observation_window` field (top level, plus
per-sport) reports the exact span of daily files consumed -- start, end, distinct
days, file count -- computed from the `<date>.jsonl` filenames actually globbed.
Large move-pair counts here come from snapshot density inside that window, NOT
from a long history; read every n alongside the window.

Usage:
    python -m scripts.platformkit.analytics_showcase.micro_absorption
    python -m scripts.platformkit.analytics_showcase.micro_absorption --check
"""
import argparse
import glob
import json
import os
from collections import defaultdict
from datetime import datetime

try:
    from scripts.platformkit.analytics_showcase._clone_safe import verify_recorded_artifact
except ImportError:  # bare-import fallback when run from the module dir
    from _clone_safe import verify_recorded_artifact

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
IN_DIR = os.path.join(REPO_ROOT, "data", "cache", "line_history")
OUT_JSON = os.path.join(REPO_ROOT, "scripts", "platformkit", "analytics_showcase", "out", "micro_absorption.json")
OUT_PNG = os.path.join(REPO_ROOT, "docs", "img", "micro_absorption.png")

MIN_MOVES = 20
# time-to-start buckets in minutes: (label, lo_inclusive, hi_exclusive), far -> close
BUCKETS = [
    ("6h+", 360.0, float("inf")),
    ("3-6h", 180.0, 360.0),
    ("1-3h", 60.0, 180.0),
    ("0-1h", 0.0, 60.0),
]
FINAL_HOUR_MIN = 60.0


def _parse_ts(s: str):
    """Parse an ISO-ish timestamp; tolerate a trailing 'Z' and missing seconds.
    Returns an aware datetime or None."""
    if not s or not isinstance(s, str):
        return None
    t = s.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(t)
    except ValueError:
        return None


def _percentile(sorted_vals, q: float) -> float:
    """Nearest-rank percentile on an already-sorted list (q in [0,1])."""
    if not sorted_vals:
        return float("nan")
    idx = min(len(sorted_vals) - 1, int(round(q * (len(sorted_vals) - 1))))
    return sorted_vals[idx]


def _sport_files(sport: str):
    """The exact daily files load_series() consumes for one sport (same glob)."""
    return sorted(glob.glob(os.path.join(IN_DIR, sport, "*.jsonl")))


def _window(paths):
    """Observation window from daily `<date>.jsonl` filenames: start/end date,
    distinct days, file count. ponytail: filename dates, not a re-scan of every
    row -- the file grain IS the day grain of this feed."""
    days = sorted({os.path.splitext(os.path.basename(p))[0] for p in paths})
    return {
        "start": days[0] if days else None,
        "end": days[-1] if days else None,
        "days": len(days),
        "files": len(paths),
    }


def load_series(sport: str):
    """Return {series_key: [(captured_dt, devigged_prob), ...]} for one sport,
    only rows with a parseable captured_at, commence_time, and float prob."""
    series = defaultdict(list)
    commence = {}
    for path in glob.glob(os.path.join(IN_DIR, sport, "*.jsonl")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                prob = d.get("devigged_prob")
                cap = _parse_ts(d.get("captured_at"))
                com = _parse_ts(d.get("commence_time"))
                if prob is None or cap is None or com is None:
                    continue
                key = (d.get("game_id"), d.get("market_type"), d.get("side"), d.get("book"))
                series[key].append((cap, float(prob)))
                commence[key] = com
    return series, commence


def analyze_sport(sport: str):
    """Compute microstructure stats for one sport. Returns a dict; a sport with
    too few pregame move pairs is marked insufficient_data (still reported)."""
    series, commence = load_series(sport)
    intervals = []          # minutes between consecutive pregame snapshots
    bucket_moves = {b[0]: [] for b in BUCKETS}
    total_move = 0.0
    final_hour_move = 0.0
    n_series_used = 0
    n_snapshots = 0

    for key, points in series.items():
        com = commence[key]
        pre = sorted((c, p) for c, p in points if c < com)
        n_snapshots += len(pre)
        if len(pre) < 2:
            continue
        used = False
        for (c0, p0), (c1, p1) in zip(pre[:-1], pre[1:]):
            dt_min = (c1 - c0).total_seconds() / 60.0
            if dt_min <= 0:
                continue
            intervals.append(dt_min)
            delta = abs(p1 - p0)
            total_move += delta
            # attribute the move to the time-to-start of the LATER snapshot
            mins_to_start = (com - c1).total_seconds() / 60.0
            for label, lo, hi in BUCKETS:
                if lo <= mins_to_start < hi:
                    bucket_moves[label].append(delta)
                    break
            if mins_to_start < FINAL_HOUR_MIN:
                final_hour_move += delta
            used = True
        if used:
            n_series_used += 1

    n_moves = len(intervals)
    out = {
        "n_series_used": n_series_used,
        "n_pregame_snapshots": n_snapshots,
        "n_move_pairs": n_moves,
    }
    if n_moves < MIN_MOVES:
        out["status"] = "insufficient_data"
        out["reason"] = f"only {n_moves} pregame move pairs (< MIN_MOVES={MIN_MOVES})"
        return out

    si = sorted(intervals)
    out["status"] = "ok"
    out["interval_minutes"] = {
        "median": round(_percentile(si, 0.5), 3),
        "p90": round(_percentile(si, 0.9), 3),
        "mean": round(sum(si) / len(si), 3),
    }
    out["move_by_bucket"] = {}
    for label, _, _ in BUCKETS:
        vals = bucket_moves[label]
        out["move_by_bucket"][label] = {
            "n": len(vals),
            "mean_abs_move": round(sum(vals) / len(vals), 5) if vals else None,
        }
    out["total_abs_move"] = round(total_move, 5)
    out["final_hour_abs_move"] = round(final_hour_move, 5)
    out["final_hour_movement_share"] = round(final_hour_move / total_move, 4) if total_move > 0 else None
    return out


def make_plot(result) -> bool:
    """Absorption curves: cumulative share of total pregame movement vs
    time-to-start bucket (far -> close), one line per reportable sport."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    order = [b[0] for b in BUCKETS]  # far -> close
    fig, ax = plt.subplots(figsize=(8, 5))
    plotted = 0
    for sport, s in result["sports"].items():
        if s.get("status") != "ok":
            continue
        per_bucket = []
        for label in order:
            b = s["move_by_bucket"][label]
            per_bucket.append((b["mean_abs_move"] or 0.0) * b["n"])
        tot = sum(per_bucket) or 1.0
        cum, curve = 0.0, []
        for v in per_bucket:
            cum += v
            curve.append(cum / tot)
        ax.plot(order, curve, marker="o", label=f"{sport} (final-hr share={s['final_hour_movement_share']})")
        plotted += 1
    if plotted == 0:
        plt.close(fig)
        return False
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("time-to-start bucket (far -> close)")
    ax.set_ylabel("cumulative share of total pregame |devig-prob| movement")
    ax.set_title("Pregame price-absorption curves (market microstructure)")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    w = result.get("observation_window") or {}
    fig.text(0.5, 0.005,
             f"Source: data/cache/line_history/<sport>/*.jsonl (own scraped feed). "
             f"Observation window {w.get('start')} .. {w.get('end')} ({w.get('days')} days). "
             f"as_of={result['as_of']}. Descriptive market science, edge_claimed=False.",
             ha="center", fontsize=7, color="gray")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    fig.savefig(OUT_PNG, dpi=140)
    plt.close(fig)
    return True


def discover_sports():
    if not os.path.isdir(IN_DIR):
        return []
    return sorted(d for d in os.listdir(IN_DIR) if os.path.isdir(os.path.join(IN_DIR, d)))


def run():
    sports = discover_sports()
    result = {
        "edge_claimed": False,
        "descriptive_only": True,
        "method": "pregame per-series consecutive-snapshot |devigged_prob| movement, "
                  "bucketed by minutes-to-commence, from own scraped line_history",
        "as_of": datetime.utcnow().strftime("%Y-%m-%d"),
        "source": "data/cache/line_history/<sport>/*.jsonl",
        "min_moves_floor": MIN_MOVES,
        "observation_window": _window([]),
        "buckets_minutes": [{"label": b[0], "lo": b[1], "hi": None if b[2] == float("inf") else b[2]} for b in BUCKETS],
        "sports": {},
    }
    if not sports:
        result["status"] = "not_buildable"
        result["reason"] = f"no line_history sport dirs under {IN_DIR}"
    else:
        all_paths = []
        for sport in sports:
            result["sports"][sport] = analyze_sport(sport)
            paths = _sport_files(sport)
            all_paths.extend(paths)
            result["sports"][sport]["observation_window"] = _window(paths)
        result["observation_window"] = _window(all_paths)
        result["observation_window"]["per_sport"] = {
            s: result["sports"][s]["observation_window"] for s in sports
        }
        result["observation_window"]["note"] = (
            "Span of daily line_history files actually consumed. Counts (n_move_pairs, "
            "snapshots) are dense sampling INSIDE this window, not a long history."
        )
        reportable = [s for s, v in result["sports"].items() if v.get("status") == "ok"]
        result["status"] = "ok" if reportable else "not_buildable"
        if not reportable:
            result["reason"] = "no sport reached MIN_MOVES pregame move pairs"

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    result["plot_written"] = make_plot(result) if result["status"] == "ok" else False
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return result


def _validate_artifact(data) -> None:
    assert "sports" in data and isinstance(data["sports"], dict), "missing sports map"
    assert data.get("edge_claimed") is False, "edge_claimed must be False"
    assert data.get("status") in ("ok", "not_buildable"), "bad top-level status"
    w = data.get("observation_window")
    assert isinstance(w, dict) and w, "missing observation_window"
    if data["status"] == "ok":
        assert w.get("start") and w.get("end"), "observation_window start/end empty"
        assert w.get("days", 0) > 0 and w.get("files", 0) > 0, "observation_window empty"
        assert w.get("per_sport"), "observation_window missing per_sport"
    for sport, s in data["sports"].items():
        assert "status" in s, f"{sport}: missing status"
        sw = s.get("observation_window")
        assert isinstance(sw, dict) and sw, f"{sport}: missing observation_window"
        if s["status"] == "ok":
            share = s.get("final_hour_movement_share")
            assert share is None or 0.0 <= share <= 1.0, f"{sport}: share out of range"
            for label, _, _ in BUCKETS:
                assert label in s["move_by_bucket"], f"{sport}: missing bucket {label}"


def check() -> None:
    """Pure-function self-check on the movement math, then verify the recorded
    artifact (clone-safe when local data is absent)."""
    assert _parse_ts("2026-06-14T00:30Z") is not None
    assert _parse_ts("2026-07-01T00:00:40+00:00") is not None
    assert _parse_ts("garbage") is None
    assert _percentile([1.0, 2.0, 3.0, 4.0], 0.5) in (2.0, 3.0)
    assert _percentile([], 0.5) != _percentile([], 0.5)  # nan
    assert _window([]) == {"start": None, "end": None, "days": 0, "files": 0}
    assert _window(["x/2026-06-18.jsonl", "x/2026-07-17.jsonl", "x/2026-06-18.jsonl"]) == {
        "start": "2026-06-18", "end": "2026-07-17", "days": 2, "files": 3}
    if os.path.isdir(IN_DIR) and discover_sports():
        res = run()
        _validate_artifact(res)
        w = res["observation_window"]
        print(f"micro_absorption self-check OK -- window={w['start']}..{w['end']} "
              f"({w['days']} days, {w['files']} files), status={res['status']}, "
              f"sports={ {s: v.get('status') for s, v in res['sports'].items()} }")
    else:
        verify_recorded_artifact(OUT_JSON, _validate_artifact, "micro_absorption")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
    else:
        res = run()
        print(json.dumps({
            "status": res["status"],
            "as_of": res["as_of"],
            "observation_window": {k: res["observation_window"].get(k)
                                   for k in ("start", "end", "days", "files")},
            "plot_written": res.get("plot_written"),
            "sports": {s: {k: v.get(k) for k in ("status", "n_move_pairs", "final_hour_movement_share")}
                       for s, v in res["sports"].items()},
        }, indent=2))
