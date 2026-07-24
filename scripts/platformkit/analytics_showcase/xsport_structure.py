"""Cross-sport market structure: one methodology, four sports.

Reads the per-sport in-game reliability maps
(data/cache/calibration_grid/<sport>_reliability_map.json), which each carry the
SAME bucket schema (market_mean_prob, outcome_rate, market_brier, n_ticks,
n_games). Applies one methodology across NBA / MLB / soccer / tennis:

  (a) favorite-longshot check -- in favorite buckets (market prob >= FAV) vs
      longshot buckets (<= DOG), does the realized outcome_rate exceed / trail
      the market-implied prob? Signed gap = outcome_rate - market_mean_prob.
  (b) market calibration quality -- n_ticks-weighted ECE = |market_prob-outcome|
      and n_ticks-weighted market Brier of the market-implied probs.
  (c) comeback proxy -- in near-decided buckets (market prob >= DECIDED), the
      realized frequency the heavy favorite still lost = 1 - outcome_rate.

One table, one method, honest per-sport n. Tennis has no reliability map on disk
-> emitted as {"status":"not_buildable"} rather than guessed (precedent:
aging_curve_lite). edge_claimed=False -- calibration/structure only, no $ claims.

Usage:
    python -m scripts.platformkit.analytics_showcase.xsport_structure
    python -m scripts.platformkit.analytics_showcase.xsport_structure --check
"""
import argparse
import json
import os
from typing import Any, Dict, List, Optional

try:
    from scripts.platformkit.analytics_showcase._clone_safe import verify_recorded_artifact
except ImportError:  # bare-import fallback (running from the module dir)
    from _clone_safe import verify_recorded_artifact

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
GRID_DIR = os.path.join(REPO_ROOT, "data", "cache", "calibration_grid")
OUT_JSON = os.path.join(REPO_ROOT, "scripts", "platformkit", "analytics_showcase", "out", "xsport_structure.json")
OUT_PNG = os.path.join(REPO_ROOT, "docs", "img", "xsport_structure.png")

# sport label -> reliability-map filename. Tennis intentionally absent.
SPORTS = {
    "nba": "nba_reliability_map.json",
    "mlb": "mlb_reliability_map.json",
    "soccer": "soccer_reliability_map.json",
    "tennis": None,
}
MIN_GAMES = 30      # per-bucket floor (matches can_price min_games gate)
FAV = 0.60          # favorite stratum threshold on market_mean_prob
DOG = 0.40          # longshot stratum threshold
DECIDED = 0.85      # near-decided threshold for the comeback proxy


def _wmean(pairs: List[tuple]) -> Optional[float]:
    """n-weighted mean of (value, weight) pairs. None if no weight."""
    tw = sum(w for _, w in pairs)
    if tw <= 0:
        return None
    return sum(v * w for v, w in pairs) / tw


def _stratum(buckets: List[Dict[str, Any]], keep) -> Optional[Dict[str, Any]]:
    """n_ticks-weighted market prob vs outcome for buckets passing keep(prob)."""
    sel = [b for b in buckets if keep(b["market_mean_prob"])]
    if not sel:
        return None
    tw = sum(b["n_ticks"] for b in sel)
    mp = _wmean([(b["market_mean_prob"], b["n_ticks"]) for b in sel])
    oc = _wmean([(b["outcome_rate"], b["n_ticks"]) for b in sel])
    return {
        "n_buckets": len(sel),
        "n_ticks": tw,
        "n_games": sum(b["n_games"] for b in sel),
        "mean_market_prob": round(mp, 4),
        "mean_outcome": round(oc, 4),
        "gap_outcome_minus_prob": round(oc - mp, 4),
    }


def analyze(rel_map: Dict[str, Any]) -> Dict[str, Any]:
    """Apply the shared methodology to one reliability map. Uses only buckets
    with a non-null market_mean_prob and n_games >= MIN_GAMES."""
    raw = rel_map.get("buckets", {})
    usable = [
        b for b in raw.values()
        if b.get("market_mean_prob") is not None
        and b.get("outcome_rate") is not None
        and b.get("n_games", 0) >= MIN_GAMES
        and b.get("n_ticks", 0) > 0
    ]
    if not usable:
        return {"status": "not_buildable",
                "reason": f"no bucket had market_mean_prob and n_games>={MIN_GAMES}"}

    # (b) market calibration quality -- tick-weighted ECE + Brier
    ece = _wmean([(abs(b["market_mean_prob"] - b["outcome_rate"]), b["n_ticks"]) for b in usable])
    brier = _wmean([(b["market_brier"], b["n_ticks"]) for b in usable if b.get("market_brier") is not None])

    # (a) favorite-longshot
    fav = _stratum(usable, lambda p: p >= FAV)
    dog = _stratum(usable, lambda p: p <= DOG)

    # (c) comeback proxy: near-decided buckets, realized favorite-loses rate
    decided = [b for b in usable if b["market_mean_prob"] >= DECIDED]
    comeback = None
    if decided:
        oc = _wmean([(b["outcome_rate"], b["n_ticks"]) for b in decided])
        comeback = {
            "threshold_market_prob": DECIDED,
            "n_buckets": len(decided),
            "n_ticks": sum(b["n_ticks"] for b in decided),
            "n_games": sum(b["n_games"] for b in decided),
            "favorite_hold_rate": round(oc, 4),
            "comeback_rate": round(1.0 - oc, 4),
        }

    return {
        "status": "ok",
        "sport_from_map": rel_map.get("sport"),
        "as_of": rel_map.get("generated_at"),
        "n_games_total": rel_map.get("n_games_total"),
        "n_buckets_usable": len(usable),
        "market_ece": round(ece, 4) if ece is not None else None,
        "market_brier": round(brier, 4) if brier is not None else None,
        "favorite_longshot": {"favorite_ge_%.2f" % FAV: fav, "longshot_le_%.2f" % DOG: dog},
        "comeback_proxy": comeback,
    }


def build_table(sports: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for sport, s in sports.items():
        if s.get("status") != "ok":
            rows.append({"sport": sport, "status": s.get("status"), "n_games": None})
            continue
        fav = s["favorite_longshot"].get("favorite_ge_%.2f" % FAV) or {}
        dog = s["favorite_longshot"].get("longshot_le_%.2f" % DOG) or {}
        cb = s.get("comeback_proxy") or {}
        rows.append({
            "sport": sport,
            "status": "ok",
            "n_games": s["n_games_total"],
            "n_buckets_usable": s["n_buckets_usable"],
            "market_ece": s["market_ece"],
            "market_brier": s["market_brier"],
            "fav_gap": fav.get("gap_outcome_minus_prob"),
            "dog_gap": dog.get("gap_outcome_minus_prob"),
            "comeback_rate": cb.get("comeback_rate"),
        })
    return rows


def build_verdict(rows: List[Dict[str, Any]]) -> str:
    ok = [r for r in rows if r["status"] == "ok"]
    miss = [r["sport"] for r in rows if r["status"] != "ok"]
    if not ok:
        return "No sport had a usable reliability map."
    parts = []
    for r in ok:
        fl = ""
        if r["fav_gap"] is not None and r["dog_gap"] is not None:
            sign = "favorite-longshot-consistent" if (r["fav_gap"] > 0 and r["dog_gap"] < 0) else "no clean fav-longshot signature"
            fl = f", fav_gap={r['fav_gap']:+.3f}/dog_gap={r['dog_gap']:+.3f} ({sign})"
        cb = f", comeback~{r['comeback_rate']:.3f}" if r["comeback_rate"] is not None else ""
        parts.append(f"{r['sport']}: market ECE={r['market_ece']:.3f} (n_games={r['n_games']}){fl}{cb}")
    tail = f" Not buildable: {', '.join(miss)}." if miss else ""
    return "Same methodology, per-sport n honest. " + "; ".join(parts) + "." + tail


def make_plot(result: Dict[str, Any]) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    ok = [r for r in result["table"] if r["status"] == "ok"]
    if not ok:
        return False
    labels = [r["sport"] for r in ok]
    x = range(len(labels))
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.5))

    ax = axes[0]
    ax.bar([i - 0.2 for i in x], [r["market_ece"] or 0 for r in ok], 0.4, label="market ECE")
    ax.bar([i + 0.2 for i in x], [r["market_brier"] or 0 for r in ok], 0.4, label="market Brier")
    ax.set_xticks(list(x)); ax.set_xticklabels(labels)
    ax.set_title("(b) market calibration quality"); ax.legend(fontsize=8)

    ax = axes[1]
    ax.bar([i - 0.2 for i in x], [r["fav_gap"] or 0 for r in ok], 0.4, label="favorite gap")
    ax.bar([i + 0.2 for i in x], [r["dog_gap"] or 0 for r in ok], 0.4, label="longshot gap")
    ax.axhline(0, color="gray", linewidth=1)
    ax.set_xticks(list(x)); ax.set_xticklabels(labels)
    ax.set_title("(a) favorite-longshot: outcome - implied"); ax.legend(fontsize=8)

    ax = axes[2]
    ax.bar(list(x), [r["comeback_rate"] or 0 for r in ok], 0.5, color="#b5651d")
    ax.set_xticks(list(x)); ax.set_xticklabels(labels)
    ax.set_title("(c) comeback proxy (fav prob >= %.2f)" % DECIDED)

    fig.suptitle("Cross-sport market structure -- one methodology, per-sport n")
    fig.text(0.5, 0.005,
             "Source: data/cache/calibration_grid/{nba,mlb,soccer}_reliability_map.json. "
             "as_of=%s. Tick-weighted; calibration/structure only, edge_claimed=False." % result.get("as_of"),
             ha="center", fontsize=7, color="gray")
    fig.tight_layout(rect=(0, 0.04, 1, 0.96))
    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    fig.savefig(OUT_PNG, dpi=140)
    plt.close(fig)
    return True


def run() -> Dict[str, Any]:
    sports: Dict[str, Any] = {}
    as_ofs = []
    for sport, fname in SPORTS.items():
        if fname is None:
            sports[sport] = {"status": "not_buildable",
                             "reason": "no reliability map (data/cache/calibration_grid/%s_reliability_map.json absent)" % sport}
            continue
        path = os.path.join(GRID_DIR, fname)
        if not os.path.exists(path):
            sports[sport] = {"status": "not_buildable", "reason": "reliability map missing at %s" % path}
            continue
        with open(path, encoding="utf-8") as f:
            rel_map = json.load(f)
        sports[sport] = analyze(rel_map)
        if sports[sport].get("as_of"):
            as_ofs.append(sports[sport]["as_of"])

    result = {
        "edge_claimed": False,
        "method": ("one reliability-map methodology across sports: tick-weighted market ECE/Brier (b), "
                   "favorite (>=%.2f) vs longshot (<=%.2f) outcome-minus-implied gap (a), "
                   "near-decided (>=%.2f) favorite-loses comeback rate (c)" % (FAV, DOG, DECIDED)),
        "floors": ("per-bucket n_games>=%d AND non-null market_mean_prob; tick-weighted aggregates; "
                   "tennis has no map -> not_buildable, never guessed; edge_claimed=False" % MIN_GAMES),
        "source_maps": {s: f for s, f in SPORTS.items() if f},
        "as_of": max(as_ofs) if as_ofs else None,
        "sports": sports,
    }
    result["table"] = build_table(sports)
    result["verdict"] = build_verdict(result["table"])

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    result["plot_written"] = make_plot(result)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return result


def _selfcheck_math() -> None:
    """Synthetic reliability map: a perfectly-calibrated market -> ECE ~ 0."""
    buckets = {
        "a": {"n_ticks": 100, "n_games": 50, "outcome_rate": 0.90, "market_mean_prob": 0.90, "market_brier": 0.09},
        "b": {"n_ticks": 100, "n_games": 50, "outcome_rate": 0.30, "market_mean_prob": 0.30, "market_brier": 0.21},
    }
    out = analyze({"buckets": buckets, "sport": "x", "n_games_total": 100})
    assert out["status"] == "ok", out
    assert abs(out["market_ece"]) < 1e-9, out
    # favorite stratum (>=0.60) has only bucket a; gap should be ~0
    fav = out["favorite_longshot"]["favorite_ge_%.2f" % FAV]
    assert fav is not None and abs(fav["gap_outcome_minus_prob"]) < 1e-9, fav
    print("xsport_structure math self-check OK")


def check() -> None:
    _selfcheck_math()

    def _validate(data: Dict[str, Any]) -> None:
        assert data.get("edge_claimed") is False
        assert "sports" in data and "table" in data and "verdict" in data
        assert any(s.get("status") == "ok" for s in data["sports"].values()), "no sport built"

    if os.path.exists(GRID_DIR) and any(os.path.exists(os.path.join(GRID_DIR, f)) for f in SPORTS.values() if f):
        res = run()
        _validate(res)
        print("PASS (local data): xsport_structure -- %s" % res["verdict"])
    else:
        verify_recorded_artifact(OUT_JSON, _validate, "xsport_structure")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
    else:
        res = run()
        print(json.dumps({"verdict": res["verdict"], "plot_written": res["plot_written"],
                          "table": res["table"]}, indent=2))
