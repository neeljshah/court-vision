"""answers.calibration_resolver -- fail-closed readout of the in-game
calibration artifacts under data/ab_reports/.

Answers model-QUALITY questions only (reliability, over/under-confidence,
isotonic effect, regime breakdown, model-vs-market Brier in-window). Every
number is quoted verbatim from the newest matching artifact and the exact
filename is returned in `source_artifact`; nothing is recomputed except two
trivial reductions over the quoted rows (which bin has the largest gap, and
which bins predict further from 0.5 than the observed frequency).

Honesty rails (.claude/rules/no-edge-claims.md):
  - when the artifact says the model's Brier is WORSE than the market's, the
    envelope says "model TRAILS market" in plain words -- never softened;
  - any question phrased as edge / ROI / profit is REFUSED before an artifact
    is opened (shared guard: resolver_registry.is_edge_language);
  - artifact absent/unreadable -> no_data; unrecognised intent -> not_supported.

Run: python -m scripts.platformkit.answers.calibration_resolver "did isotonic help"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

from scripts.platformkit.answers.resolver_registry import is_edge_language

CATEGORY = "calibration_diagnostics"
_REPO = Path(__file__).resolve().parents[3]
_REPORTS_REL = "data/ab_reports"
_RULE = ".claude/rules/no-edge-claims.md"

# intent -> filename glob under data/ab_reports (newest by filename wins)
_PATTERNS = {
    "overall": "wp_diagnostics_*.json",
    "overconfidence": "wp_diagnostics_*.json",
    "reliability_bins": "wp_diagnostics_*.json",
    "isotonic": "wp_oos_*.json",
    "market_window": "lag_window_calibration.json",
    "market_lag": "market_lag_study.json",
    "regime": "regime_calibration.json",
    "coverage": "wp_series_audit_*.json",
    "replay": "window_strategy_replay.json",
}
# Priority-ordered: the first keyword hit wins, so specific phrases sit above
# the bare "calibrat*" fallback (which every one of these questions contains).
_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("overconfidence", ("overconfident", "overconfidence", "too confident", "underconfident")),
    ("isotonic", ("isotonic", "recalibrat", "did it help", "walk-forward", "walk forward")),
    ("market_lag", ("lag", "stale", "how fast does the market")),
    ("market_window", ("market", "in-window", "in window", "compare to the close")),
    ("regime", ("regime", "by month", "by confidence", "break down", "breaks down")),
    ("coverage", ("how much data", "how many games", "coverage", "series audit", "sample size")),
    ("replay", ("replay", "strategy", "entry")),
    ("reliability_bins", ("by bin", "per bin", "reliability", "bins")),
    ("overall", ("calibrat", "brier", "model quality", "how good is the model")),
]


def classify_intent(query: str) -> str | None:
    low = query.lower()
    for intent, words in _KEYWORDS:
        if any(w in low for w in words):
            return intent
    return None


def _sport_match(key: str, sport: str | None) -> bool:
    """Loose containment both ways -- artifact sport keys are a mix of plain
    ('mlb', 'soccer_intl') and Kalshi series ('KXMLBGAME')."""
    if not sport:
        return True
    s, k = sport.lower(), key.lower()
    return s in k or k in s


def _fmt(x: Any, nd: int = 4) -> Any:
    return round(x, nd) if isinstance(x, (int, float)) and not isinstance(x, bool) else x


# ---------------------------------------------------------------------------
# per-intent extractors: (artifact_dict, sport) -> fields dict, or None -> no_data
# ---------------------------------------------------------------------------
def _worst_bin(rows: list[dict]) -> dict | None:
    scored = [r for r in rows if r.get("gap") is not None]
    return max(scored, key=lambda r: abs(r["gap"])) if scored else None


def _overall(d: dict, sport: str | None) -> dict | None:
    rows = d.get("reliability") or []
    worst = _worst_bin(rows)
    if worst is None:
        return None
    gaps = [abs(r["gap"]) for r in rows if r.get("gap") is not None]
    iso = d.get("isotonic_check") or {}
    return {
        "tick_count": d.get("tick_count"),
        "n_bins": len(rows),
        "max_abs_reliability_gap": _fmt(max(gaps)),
        "mean_abs_reliability_gap": _fmt(sum(gaps) / len(gaps)),
        "worst_bin": worst,
        "isotonic_check_in_sample": iso or None,
        "verdict": (
            "largest reliability gap {g} in bin {b} (mean predicted {p}, observed {o}, n={n}); "
            "gap = observed - predicted, so a negative gap means the model predicted too high"
        ).format(g=_fmt(worst["gap"]), b=worst.get("bin"),
                 p=_fmt(worst.get("mean_predicted_prob")),
                 o=_fmt(worst.get("observed_win_freq")), n=worst.get("n")),
        "note": ("isotonic_check in this artifact is IN-SAMPLE -- for the "
                 "out-of-sample answer ask about walk-forward isotonic (wp_oos_*.json)"),
    }


def _overconfidence(d: dict, sport: str | None) -> dict | None:
    rows = d.get("reliability") or []
    if not rows:
        return None
    over = [r for r in rows
            if r.get("gap") is not None and r.get("mean_predicted_prob") is not None
            and abs(r["mean_predicted_prob"] - 0.5) > abs(r.get("observed_win_freq", 0.5) - 0.5)]
    over.sort(key=lambda r: abs(r["gap"]), reverse=True)
    return {
        "tick_count": d.get("tick_count"),
        "n_bins_total": len(rows),
        "n_bins_overconfident": len(over),
        "overconfident_bins": over[:5],
        "definition": ("overconfident = the bin's mean predicted probability is further "
                       "from 0.5 than the observed win frequency in that bin"),
        "verdict": ("{k} of {t} bins are overconfident by that definition"
                    .format(k=len(over), t=len(rows))
                    + ("; worst is bin {b} (predicted {p}, observed {o}, n={n})".format(
                        b=over[0].get("bin"), p=_fmt(over[0].get("mean_predicted_prob")),
                        o=_fmt(over[0].get("observed_win_freq")), n=over[0].get("n")) if over else "")),
    }


def _reliability_bins(d: dict, sport: str | None) -> dict | None:
    rows = d.get("reliability") or []
    if not rows:
        return None
    return {"tick_count": d.get("tick_count"), "n_bins": len(rows),
            "reliability": rows,
            "note": "gap = observed_win_freq - mean_predicted_prob, verbatim from the artifact"}


def _isotonic(d: dict, sport: str | None) -> dict | None:
    sports = {k: v for k, v in (d.get("sports") or {}).items() if _sport_match(k, sport)}
    if not sports:
        return None
    out, verdicts = {}, []
    for key, blk in sports.items():
        wf = blk.get("walk_forward_isotonic") or {}
        pooled = wf.get("pooled") or {}
        out[key] = {"tick_count": blk.get("tick_count"), "fold_count": wf.get("fold_count"),
                    "pooled": pooled, "folds": wf.get("folds"), "note": wf.get("note")}
        delta = pooled.get("delta")
        if delta is not None:
            verdicts.append("{k}: isotonic {w} pooled out-of-sample Brier by {d} ({b} -> {a})".format(
                k=key, w="IMPROVED" if delta > 0 else "WORSENED", d=_fmt(abs(delta)),
                b=_fmt(pooled.get("brier_before")), a=_fmt(pooled.get("brier_after"))))
    return {"by_series": out, "verdict": "; ".join(verdicts) or "no pooled delta stored",
            "note": "walk-forward: each fold is scored only on ticks after its fit window"}


def _market_window(d: dict, sport: str | None) -> dict | None:
    rows = [r for r in (d.get("summaries") or []) if _sport_match(r.get("sport", ""), sport)]
    if not rows:
        return None
    verdicts = []
    for r in rows:
        model, market = r.get("brier_model_window"), r.get("brier_market_window")
        if model is None or market is None:
            continue
        verdicts.append("{s}: model {v} the market in-window (model Brier {m} vs market {k}, "
                        "delta {d}, n_ticks={n})".format(
                            s=r.get("sport"), v="TRAILS" if model > market else "leads",
                            m=_fmt(model), k=_fmt(market), d=_fmt(r.get("delta")),
                            n=r.get("n_ticks")))
    return {"window_seconds": d.get("window_seconds"), "summaries": rows,
            "verdict": "; ".join(verdicts) or "no comparable Brier pair stored",
            "note": ("delta = model minus market Brier over the post-event window; negative "
                     "delta means the model is WORSE than the market there. Calibration "
                     "comparison only -- not a tradeable quantity")}


def _market_lag(d: dict, sport: str | None) -> dict | None:
    rows = [r for r in (d.get("summaries") or []) if _sport_match(r.get("sport", ""), sport)]
    if not rows:
        return None
    return {"horizon_ticks": d.get("horizon_ticks"),
            "threshold_fraction": d.get("threshold_fraction"),
            "n_events": len(d.get("events") or []),
            "summaries": rows,
            "note": "lag_seconds/lag_ticks are how long each series took to move after a scoring event"}


def _regime(d: dict, sport: str | None) -> dict | None:
    buckets = d.get("buckets") or []
    if not buckets:
        return None
    ranked = sorted(buckets, key=lambda b: abs(b.get("reliability_gap") or 0.0), reverse=True)
    sig = [b for b in buckets if b.get("status") == "SIGNIFICANT"]
    return {"tick_count": d.get("tick_count"), "min_n": d.get("min_n"),
            "global_reliability": _fmt(d.get("global_reliability")),
            "n_buckets": len(buckets), "n_significant": len(sig),
            "worst_buckets": ranked[:5],
            "verdict": "{k} of {t} regime buckets deviate significantly from global reliability".format(
                k=len(sig), t=len(buckets))}


def _coverage(d: dict, sport: str | None) -> dict | None:
    series = (d.get("series") or {}).get("model_prob") or {}
    overall = series.get("overall")
    if not overall:
        return None
    return {"raw_probability_fields": d.get("raw_probability_fields"),
            "model_prob_overall": overall,
            "model_prob_by_sport": series.get("by_sport"),
            "note": "coverage audit of the graded tick store behind every other calibration answer"}


def _replay(d: dict, sport: str | None) -> dict | None:
    by_sport = {k: v for k, v in (d.get("by_sport") or {}).items() if _sport_match(k, sport)}
    if not by_sport:
        return None
    verdicts = []
    for key, blk in by_sport.items():
        entry, market = blk.get("entry_brier"), blk.get("market_brier")
        if entry is None or market is None:
            continue
        verdicts.append("{k}: entry Brier {e} vs market {m} -- model {v}".format(
            k=key, e=_fmt(entry), m=_fmt(market),
            v="TRAILS the market" if entry > market else "leads the market"))
    cal = {k: (v or {}).get("pooled") for k, v in (d.get("calibration_oos") or {}).items()
           if _sport_match(k, sport)}
    return {"spec": d.get("spec"), "by_sport": by_sport, "calibration_oos_pooled": cal,
            "honest_verdict": d.get("honest_verdict"),
            "verdict": "; ".join(verdicts) or "no comparable Brier pair stored",
            "note": "replay is a calibration benchmark; the artifact's own honest_verdict is quoted verbatim"}


_HANDLERS: dict[str, Callable[[dict, str | None], dict | None]] = {
    "overall": _overall, "overconfidence": _overconfidence,
    "reliability_bins": _reliability_bins, "isotonic": _isotonic,
    "market_window": _market_window, "market_lag": _market_lag,
    "regime": _regime, "coverage": _coverage, "replay": _replay,
}


def _newest(reports_dir: Path, pattern: str) -> Path | None:
    hits = sorted(reports_dir.glob(pattern), key=lambda p: p.name)
    return hits[-1] if hits else None


def resolve(query: str, sport: str | None = None,
            reports_dir: Path | str | None = None, **_kw: Any) -> dict:
    """The one entry point. Returns the standard fail-closed envelope."""
    base: dict[str, Any] = {"category": CATEGORY, "sport": sport or "all", "query": query}
    tok = is_edge_language(query)
    if tok:
        return {**base, "status": "refused", "source_artifact": _RULE,
                "note": ("edge/ROI/retracted-number language ('{t}') is out of scope -- this "
                         "resolver reports calibration quality only, never a dollar edge. "
                         "See {r}".format(t=tok, r=_RULE))}
    intent = classify_intent(query)
    if intent is None:
        return {**base, "status": "not_supported", "intent": None,
                "note": "no calibration intent recognised. Supported: " + ", ".join(sorted(_PATTERNS))}
    rdir = Path(reports_dir) if reports_dir else _REPO / _REPORTS_REL
    pattern = _PATTERNS[intent]
    base["intent"] = intent
    path = _newest(rdir, pattern)
    if path is None:
        return {**base, "status": "no_data", "source_artifact": f"{_REPORTS_REL}/{pattern}",
                "note": f"no artifact matching '{pattern}' under {_REPORTS_REL}"}
    rel = f"{_REPORTS_REL}/{path.name}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        return {**base, "status": "no_data", "source_artifact": rel,
                "note": f"artifact unreadable: {exc}"}
    fields = _HANDLERS[intent](data, sport)
    as_of = data.get("generated_at") or data.get("generated")
    if fields is None:
        return {**base, "status": "no_data", "source_artifact": rel, "as_of": as_of,
                "note": f"artifact present but has no rows for intent '{intent}'"
                        + (f" and sport '{sport}'" if sport else "")}
    return {**base, "status": "ok", "source_artifact": rel, "as_of": as_of, **fields}


if __name__ == "__main__":  # pragma: no cover
    q = sys.argv[1] if len(sys.argv) > 1 else "how calibrated is the in-game model"
    sp = sys.argv[2] if len(sys.argv) > 2 else None
    print(json.dumps(resolve(q, sp), indent=2, default=str)[:4000])
