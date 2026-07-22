"""Cross-sport calibration scoreboard: compose ALL existing verdict artifacts
into one JSON + one PNG. Reads only, computes nothing new -- every number here
already exists in a benchmark artifact; this just lays them side by side.

edge_claimed is always False. Verdicts are copied verbatim from source.

Usage:
    python -m scripts.platformkit.analytics_showcase.cross_sport_scoreboard
    python -m scripts.platformkit.analytics_showcase.cross_sport_scoreboard --check
"""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CRPS_DIR = ROOT / "scripts" / "platformkit" / "benchmarks" / "crps_market"
OUT_DIR = Path(__file__).resolve().parent / "out"
IMG_PATH = ROOT / "docs" / "img" / "cross_sport_scoreboard.png"
OUT_JSON = OUT_DIR / "cross_sport_scoreboard.json"

# (source file, sport label, market label, honest reason if unusable)
PAIRED_SOURCES = [
    (CRPS_DIR / "last_run_ingame_nba_winprob_ALLGAMES_v3.json", "nba", "winprob (Brier)"),
    (CRPS_DIR / "last_run_ingame_mlb.json", "mlb_ingame", "CRPS"),
    (CRPS_DIR / "last_run_mlb.json", "mlb_pregame", "CRPS"),
    (CRPS_DIR / "last_run_ingame_soccer.json", "soccer_intl", "winprob (Brier)"),
]

# artifacts that exist but don't carry a per-checkpoint model-vs-market
# paired delta+CI -- honest skip, not silently dropped.
SKIP_NOTES = []


def _rows_from_checkpoints(path: Path, sport: str, market: str):
    """last_run_mlb.json is a single flat record (no 'checkpoints' dict);
    everything else nests per-checkpoint records under 'checkpoints'."""
    d = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    if "checkpoints" in d:
        for cp_key, cp in d["checkpoints"].items():
            rows.append({
                "sport": sport,
                "market": market,
                "checkpoint": cp_key,
                "n": cp.get("n"),
                "paired_delta_mean": cp.get("paired_delta_mean"),
                "paired_delta_95ci": cp.get("paired_delta_95ci"),
                "verdict": cp.get("verdict"),
                "source": str(path.relative_to(ROOT)).replace("\\", "/"),
            })
    else:
        rows.append({
            "sport": sport,
            "market": f"{market} ({d.get('market')})" if d.get("market") else market,
            "checkpoint": "pregame",
            "n": d.get("n_scored"),
            "paired_delta_mean": d.get("paired_delta_mean"),
            "paired_delta_95ci": d.get("paired_delta_95ci"),
            "verdict": d.get("verdict"),
            "source": str(path.relative_to(ROOT)).replace("\\", "/"),
        })
    return rows


def _check_extra_out_files():
    """Session out/*.json files that exist but lack the paired delta+CI
    shape this scoreboard needs -- record why they're skipped, not silent."""
    for f in sorted(OUT_DIR.glob("*.json")):
        if f.name == "cross_sport_scoreboard.json":
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        if "verdict" in d and "sports" in d:
            SKIP_NOTES.append({
                "source": str(f.relative_to(ROOT)).replace("\\", "/"),
                "reason": ("murphy decomposition: full-season reliability/resolution gap "
                           "per sport, no per-checkpoint CI -- not the same shape as the "
                           "paired-delta scoreboard. verdict copied verbatim: " + str(d["verdict"])),
            })


def build():
    rows = []
    for path, sport, market in PAIRED_SOURCES:
        if not path.exists():
            SKIP_NOTES.append({"source": str(path), "reason": "file not found"})
            continue
        rows.extend(_rows_from_checkpoints(path, sport, market))
    _check_extra_out_files()

    wf_path = ROOT / "results" / "winprob_walk_forward_results.json"
    if wf_path.exists():
        SKIP_NOTES.append({
            "source": "results/winprob_walk_forward_results.json",
            "reason": "walk-forward accuracy/Brier of the model alone, no market-paired "
                      "delta or CI -- not comparable to the scoreboard rows.",
        })

    payload = {
        "edge_claimed": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "composition only -- every number copied verbatim from its source artifact",
        "n_rows": len(rows),
        "rows": rows,
        "skipped": SKIP_NOTES,
        "honest_note": ("Model beats market only where verdict starts MODEL_SHARPER "
                         "(still PROVISIONAL pending more data). Most rows are UNDERPOWERED "
                         "(CI spans zero) or MARKET_SHARPER -- reported as-is."),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _verdict_color(v):
    if v is None:
        return "#888888"
    if v.startswith("MODEL_SHARPER"):
        return "#2b8a3e"
    if v.startswith("MARKET_SHARPER"):
        return "#c0392b"
    if v.startswith("UNDERPOWERED"):
        return "#888888"
    return "#4a6fa5"


def plot(payload):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = sorted(payload["rows"], key=lambda r: (r["sport"], r["market"], r["checkpoint"]))
    labels = [f"{r['sport']} / {r['market']} / {r['checkpoint']} (n={r['n']})" for r in rows]
    deltas = [r["paired_delta_mean"] for r in rows]
    lo = [r["paired_delta_mean"] - r["paired_delta_95ci"][0] for r in rows]
    hi = [r["paired_delta_95ci"][1] - r["paired_delta_mean"] for r in rows]
    colors = [_verdict_color(r["verdict"]) for r in rows]

    fig, ax = plt.subplots(figsize=(10, max(4, 0.4 * len(rows))))
    y = range(len(rows))
    ax.errorbar(deltas, y, xerr=[lo, hi], fmt="o", ecolor="#999999",
                elinewidth=1.5, capsize=3, markersize=0)
    ax.scatter(deltas, y, c=colors, s=60, zorder=3)
    ax.axvline(0, color="black", linewidth=0.8, linestyle="--")
    # ponytail: CRPS (runs) and Brier (probability) share one x-axis here --
    # units differ by sport, only the sign/CI-vs-zero is comparable across rows.
    ax.set_yticks(list(y))
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("paired delta = market_error - model_error  (positive = model sharper)")
    ax.set_title("Cross-sport calibration scoreboard: model vs market (95% CI)\n"
                  "edge_claimed=False -- verdicts copied verbatim from source artifacts",
                  fontsize=10)

    from matplotlib.lines import Line2D
    legend = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#2b8a3e", markersize=8, label="MODEL_SHARPER*"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#c0392b", markersize=8, label="MARKET_SHARPER*"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#888888", markersize=8, label="UNDERPOWERED"),
    ]
    ax.legend(handles=legend, loc="lower right", fontsize=8)
    fig.tight_layout()
    IMG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(IMG_PATH, dpi=150)
    plt.close(fig)


def check():
    assert OUT_JSON.exists(), "scoreboard JSON missing"
    d = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    assert d["edge_claimed"] is False
    assert d["n_rows"] == len(d["rows"]) > 0
    for r in d["rows"]:
        assert r["paired_delta_95ci"][0] <= r["paired_delta_mean"] <= r["paired_delta_95ci"][1]
        assert r["verdict"]
    assert IMG_PATH.exists(), "scoreboard PNG missing"
    print(f"OK: {d['n_rows']} rows, {len(d['skipped'])} skipped sources, image at {IMG_PATH}")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        check()
    else:
        payload = build()
        plot(payload)
        check()
