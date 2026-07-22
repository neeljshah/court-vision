"""
Market-microstructure MEASUREMENT (latency/cadence), NOT a trading signal.

Inspects rescued pod tick data in data/pod_backup_2026_07_20/ and reports:
  - inter-tick cadence (seconds between consecutive quotes on the same market/line)
  - price-move size distribution (|delta market_prob| between consecutive ticks)
  - model-vs-market divergence at each tick (model_prob - market_prob)

Primary source: ingame_grade_deriv/mlb/*.jsonl (per-market-line quote tracks,
ts + market_prob + model_prob). Secondary: tip_capture/wnba ingame_*.jsonl
(kalshi decimal-odds snapshots) for a second sport's capture cadence + overround.

Degrades honestly (status + paths_tried in the JSON) if inputs are missing.
Run once. ASCII output only.
"""
import json
import statistics as stats
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BACKUP = REPO / "data" / "pod_backup_2026_07_20"
OUT_JSON = Path(__file__).resolve().parent / "out" / "tick_microstructure.json"
OUT_PNG = REPO / "docs" / "img" / "tick_microstructure.png"

paths_tried = []


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def quantiles(vals, qs=(0.5, 0.9)):
    if not vals:
        return {}
    v = sorted(vals)
    out = {}
    for q in qs:
        idx = min(len(v) - 1, int(round(q * (len(v) - 1))))
        out[f"p{int(q*100)}"] = round(v[idx], 4)
    return out


def measure_mlb_deriv():
    """ingame_grade_deriv/mlb/*.jsonl: per-(file,line,side) quote tracks."""
    d = BACKUP / "ingame_grade_deriv" / "mlb"
    paths_tried.append(str(d))
    if not d.exists():
        return None

    tracks = defaultdict(list)  # (file, line, side) -> [(ts, market_prob, model_prob)]
    n_rows = 0
    for f in sorted(d.glob("*.jsonl")):
        with open(f, encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                n_rows += 1
                key = (f.name, row.get("line"), row.get("side"))
                try:
                    ts = parse_ts(row["ts"])
                except Exception:
                    continue
                tracks[key].append((ts, row.get("market_prob"), row.get("model_prob")))

    inter_tick_s = []
    price_moves = []
    divergences = []
    for key, rows in tracks.items():
        rows.sort(key=lambda r: r[0])
        for (ts, mp, modp) in rows:
            if mp is not None and modp is not None:
                divergences.append(abs(modp - mp))
        for i in range(1, len(rows)):
            dt = (rows[i][0] - rows[i - 1][0]).total_seconds()
            if dt > 0:
                inter_tick_s.append(dt)
            mp0, mp1 = rows[i - 1][1], rows[i][1]
            if mp0 is not None and mp1 is not None and mp1 != mp0:
                price_moves.append(abs(mp1 - mp0))

    return {
        "source": "ingame_grade_deriv/mlb (Kalshi total-market quote tracks)",
        "n_files": len(list(d.glob("*.jsonl"))),
        "n_rows": n_rows,
        "n_quote_tracks": len(tracks),
        "inter_tick_seconds": {
            "n": len(inter_tick_s),
            "median": round(stats.median(inter_tick_s), 1) if inter_tick_s else None,
            "mean": round(stats.mean(inter_tick_s), 1) if inter_tick_s else None,
            **quantiles(inter_tick_s),
        },
        "price_move_size": {
            "n": len(price_moves),
            "median": round(stats.median(price_moves), 4) if price_moves else None,
            "mean": round(stats.mean(price_moves), 4) if price_moves else None,
            **quantiles(price_moves),
            "note": "abs delta in market_prob between consecutive ticks on same market line",
        },
        "model_vs_market_divergence": {
            "n": len(divergences),
            "median": round(stats.median(divergences), 4) if divergences else None,
            "mean": round(stats.mean(divergences), 4) if divergences else None,
            **quantiles(divergences),
            "note": "abs(model_prob - market_prob) per tick; a calibration-gap MEASUREMENT, not an edge",
        },
    }, inter_tick_s, price_moves


def measure_wnba_kalshi():
    """tip_capture/wnba ingame_*.jsonl: capture-cadence + Kalshi decimal-odds overround."""
    files = sorted((BACKUP / "tip_capture" / "wnba").glob("ingame_*.jsonl"))
    paths_tried.append(str(BACKUP / "tip_capture" / "wnba" / "ingame_*.jsonl"))
    if not files:
        return None

    capture_ts = []
    overrounds = []
    n_rows = 0
    for f in files:
        with open(f, encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                n_rows += 1
                try:
                    capture_ts.append(parse_ts(row["capture_ts"]))
                except Exception:
                    pass
                events = (
                    row.get("payload", {}).get("market", {}).get("kalshi", {}).get("events", [])
                )
                for ev in events:
                    p = ev.get("prices", {}).get("kalshi", {})
                    h, a = p.get("home"), p.get("away")
                    if h and a and h > 0 and a > 0:
                        overrounds.append(1.0 / h + 1.0 / a - 1.0)

    capture_ts.sort()
    inter_tick_s = [
        (capture_ts[i] - capture_ts[i - 1]).total_seconds()
        for i in range(1, len(capture_ts))
        if (capture_ts[i] - capture_ts[i - 1]).total_seconds() > 0
    ]

    return {
        "source": "tip_capture/wnba ingame_*.jsonl (Kalshi decimal-odds board snapshots)",
        "n_files": len(files),
        "n_rows": n_rows,
        "capture_cadence_seconds": {
            "n": len(inter_tick_s),
            "median": round(stats.median(inter_tick_s), 1) if inter_tick_s else None,
            "mean": round(stats.mean(inter_tick_s), 1) if inter_tick_s else None,
            **quantiles(inter_tick_s),
        },
        "kalshi_overround": {
            "n": len(overrounds),
            "median": round(stats.median(overrounds), 4) if overrounds else None,
            "mean": round(stats.mean(overrounds), 4) if overrounds else None,
            **quantiles(overrounds),
            "note": "1/home_decimal + 1/away_decimal - 1, per event snapshot (spread/vig measurement)",
        },
    }, inter_tick_s


def plot(mlb_ticks, mlb_moves, wnba_ticks, out_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(13, 4))

    if mlb_ticks:
        axes[0].hist([t for t in mlb_ticks if t < 600], bins=40, color="#4C72B0")
    axes[0].set_title("MLB deriv: inter-tick gaps (s, <10min)")
    axes[0].set_xlabel("seconds")

    if mlb_moves:
        axes[1].hist(mlb_moves, bins=40, color="#DD8452")
    axes[1].set_title("MLB deriv: |market_prob delta| per tick")
    axes[1].set_xlabel("prob delta")

    if wnba_ticks:
        axes[2].hist([t for t in wnba_ticks if t < 600], bins=40, color="#55A868")
    axes[2].set_title("WNBA capture: inter-tick gaps (s, <10min)")
    axes[2].set_xlabel("seconds")

    fig.suptitle(
        "Market-microstructure MEASUREMENT (cadence/latency) -- NOT a trading signal",
        fontsize=10,
    )
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=110)
    plt.close(fig)


def main():
    result = {
        "label": "market-microstructure MEASUREMENT (latency/cadence) -- NOT a trading signal",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "paths_tried": [],
        "sports": {},
        "status": "ok",
    }

    mlb_out = measure_mlb_deriv()
    wnba_out = measure_wnba_kalshi()
    result["paths_tried"] = paths_tried

    mlb_ticks, mlb_moves, wnba_ticks = [], [], []
    if mlb_out:
        stat, mlb_ticks, mlb_moves = mlb_out
        result["sports"]["mlb"] = stat
    if wnba_out:
        stat, wnba_ticks = wnba_out
        result["sports"]["wnba"] = stat

    if not result["sports"]:
        result["status"] = "no_data"

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2))

    if result["sports"]:
        plot(mlb_ticks, mlb_moves, wnba_ticks, OUT_PNG)

    print(json.dumps(result, indent=2)[:3000])


if __name__ == "__main__":
    main()
