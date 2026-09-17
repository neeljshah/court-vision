"""scripts.platformkit.diff_timing_artifacts -- diff the six TIMING showcase
artifacts rebuilt on the segmented in-game corpus against the published ones.

Sibling of diff_showcase_artifacts.py, which covered the thirteen label-consuming
artifacts of the first regeneration pass. The five timing artifacts left under review
there (blowout_dynamics, novel_live_clock_fraction, market_convergence,
why_attribution, comeback_atlas) plus novel_market_foresight_premium are rebuilt with
CV_INGAME_CORPUS_SUFFIX=_segmented into
scripts/platformkit/analytics_showcase/out_segmented/ and compared here against the
copy published under webapp/public/data/showcase/. It publishes nothing itself.

Everything below is a DESCRIPTIVE measurement of game flow and forecaster agreement.
The corpus lost the files whose tick path mixed more than one real game, so before and
after are different populations; a move is what the measurement should have said, not a
forecaster that got better, and none of it is a money statement.
From /c/Users/neelj/nba-ai-system: `python scripts/platformkit/diff_timing_artifacts.py`
and `python -m pytest tests/platformkit/test_diff_timing_artifacts.py -q`.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

try:  # -m package invocation vs bare-script invocation
    from scripts.platformkit.diff_showcase_artifacts import _num, _rel, _table, diff_artifact
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from diff_showcase_artifacts import _num, _rel, _table, diff_artifact

_REPO = Path(__file__).resolve().parents[2]
DEFAULT_BEFORE = _REPO / "webapp" / "public" / "data" / "showcase"
DEFAULT_AFTER = _REPO / "scripts" / "platformkit" / "analytics_showcase" / "out_segmented"
DEFAULT_MD = _REPO / "docs" / "research" / "ingame_timing_regeneration_diff_2026-09-17.md"
AS_OF = "2026-09-17"

ARTIFACTS: Tuple[str, ...] = (
    "blowout_dynamics", "novel_live_clock_fraction", "market_convergence",
    "why_attribution", "comeback_atlas", "novel_market_foresight_premium",
)


def _sport(doc: Any, sport: str) -> Dict[str, Any]:
    return ((doc or {}).get("sports", {}) or {}).get(sport, {}) or {}


def _threshold(doc: Any, sport: str, value: int) -> Dict[str, Any]:
    """Blowout threshold rows are a list; select by value, not by index."""
    for row in _sport(doc, sport).get("thresholds", []) or []:
        if row.get("threshold") == value:
            return row
    return {}


def _lcf(doc: Any, sport: str) -> Dict[str, Any]:
    for row in (doc or {}).get("results", []) or []:
        if row.get("sport") == sport:
            return row
    return {}


def _mfp(doc: Any, sport: str) -> Dict[str, Any]:
    return ((doc or {}).get("results", {}) or {}).get(sport, {}) or {}


def _ticks(doc: Any, sport: str) -> Optional[float]:
    cps = ((doc or {}).get("checkpoints", {}) or {}).get(sport)
    if not isinstance(cps, dict) or not cps:
        return None
    return float(sum((c or {}).get("n", 0) for c in cps.values()))


# (label, artifact, accessor). Accessors return a number or None; never an index.
HEADLINES: Tuple[Tuple[str, str, Callable[[Any], Any]], ...] = (
    ("MLB games usable", "blowout_dynamics", lambda d: _sport(d, "mlb").get("n_games_usable")),
    ("soccer games usable", "blowout_dynamics", lambda d: _sport(d, "soccer_intl").get("n_games_usable")),
    ("MLB 2-run gap: share of games decided", "blowout_dynamics",
     lambda d: _threshold(d, "mlb", 2).get("decided_frac_of_games")),
    ("MLB 2-run gap: median inning decided", "blowout_dynamics",
     lambda d: _threshold(d, "mlb", 2).get("decided_clock_median")),
    ("MLB 3-run gap: share of games decided", "blowout_dynamics",
     lambda d: _threshold(d, "mlb", 3).get("decided_frac_of_games")),
    ("MLB 3-run gap: median clock fraction", "blowout_dynamics",
     lambda d: _threshold(d, "mlb", 3).get("decided_clockfrac_median")),
    ("MLB 5-run gap: share of games decided", "blowout_dynamics",
     lambda d: _threshold(d, "mlb", 5).get("decided_frac_of_games")),
    ("MLB 5-run gap: median inning decided", "blowout_dynamics",
     lambda d: _threshold(d, "mlb", 5).get("decided_clock_median")),
    ("soccer 1-goal gap: share of games decided", "blowout_dynamics",
     lambda d: _threshold(d, "soccer_intl", 1).get("decided_frac_of_games")),
    ("soccer 1-goal gap: median minute decided", "blowout_dynamics",
     lambda d: _threshold(d, "soccer_intl", 1).get("decided_clock_median")),
    ("MLB Live-Clock Fraction", "novel_live_clock_fraction",
     lambda d: _lcf(d, "mlb").get("live_clock_fraction")),
    ("MLB LCF games total", "novel_live_clock_fraction",
     lambda d: _lcf(d, "mlb").get("n_games_total")),
    ("soccer Live-Clock Fraction", "novel_live_clock_fraction",
     lambda d: _lcf(d, "soccer_intl").get("live_clock_fraction")),
    ("soccer LCF games total", "novel_live_clock_fraction",
     lambda d: _lcf(d, "soccer_intl").get("n_games_total")),
    ("MLB ticks across checkpoints", "market_convergence", lambda d: _ticks(d, "mlb")),
    ("soccer ticks across checkpoints", "market_convergence", lambda d: _ticks(d, "soccer_intl")),
    ("MLB forecaster gap, inning 1", "market_convergence",
     lambda d: (d.get("summary", {}).get("mlb", {}) or {}).get("gap_first")),
    ("MLB forecaster gap, inning 10", "market_convergence",
     lambda d: (d.get("summary", {}).get("mlb", {}) or {}).get("gap_last")),
    ("MLB reference entropy, inning 1 (bits)", "market_convergence",
     lambda d: (d.get("summary", {}).get("mlb", {}) or {}).get("entropy_market_first_bits")),
    ("MLB reference entropy, inning 10 (bits)", "market_convergence",
     lambda d: (d.get("summary", {}).get("mlb", {}) or {}).get("entropy_market_last_bits")),
    ("soccer forecaster gap, minute 0", "market_convergence",
     lambda d: (d.get("summary", {}).get("soccer_intl", {}) or {}).get("gap_first")),
    ("soccer forecaster gap, minute 90", "market_convergence",
     lambda d: (d.get("summary", {}).get("soccer_intl", {}) or {}).get("gap_last")),
    ("MLB state transitions", "why_attribution",
     lambda d: _sport(d, "mlb").get("n_transitions")),
    ("soccer state transitions", "why_attribution",
     lambda d: _sport(d, "soccer_intl").get("n_transitions")),
    ("largest win-prob drop", "why_attribution",
     lambda d: (d.get("biggest_drops") or [{}])[0].get("winprob_delta")),
    ("largest win-prob drop: support n", "why_attribution",
     lambda d: (d.get("biggest_drops") or [{}])[0].get("min_support_n")),
    ("atlas state buckets", "comeback_atlas", lambda d: (d or {}).get("n_buckets_total")),
    ("atlas buckets below the n>=30 mask", "comeback_atlas",
     lambda d: (d or {}).get("n_buckets_masked_n_lt_30")),
    ("MLB MFP first checkpoint", "novel_market_foresight_premium",
     lambda d: _mfp(d, "mlb").get("mfp_first")),
    ("MLB MFP last checkpoint", "novel_market_foresight_premium",
     lambda d: _mfp(d, "mlb").get("mfp_last")),
    ("MLB MFP mean", "novel_market_foresight_premium",
     lambda d: _mfp(d, "mlb").get("mfp_mean")),
    ("soccer MFP first checkpoint", "novel_market_foresight_premium",
     lambda d: _mfp(d, "soccer_intl").get("mfp_first")),
    ("soccer MFP last checkpoint", "novel_market_foresight_premium",
     lambda d: _mfp(d, "soccer_intl").get("mfp_last")),
    ("soccer MFP mean", "novel_market_foresight_premium",
     lambda d: _mfp(d, "soccer_intl").get("mfp_mean")),
)


def _value(fn: Callable[[Any], Any], doc: Any) -> Optional[float]:
    try:
        v = fn(doc)
    except Exception:  # noqa: BLE001 -- a shape change reports n/a, never crashes
        return None
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def build_report(before_dir: Path, after_dir: Path, top: int = 8) -> Dict[str, Any]:
    docs: Dict[str, Dict[str, Any]] = {}
    artifacts: List[Dict[str, Any]] = []
    for name in ARTIFACTS:
        bp, ap = before_dir / (name + ".json"), after_dir / (name + ".json")
        before = json.loads(bp.read_text(encoding="utf-8")) if bp.exists() else None
        after = json.loads(ap.read_text(encoding="utf-8")) if ap.exists() else None
        docs[name] = {"before": before, "after": after}
        if before is None or after is None:
            artifacts.append({"artifact": name, "missing": {
                "before": not bp.exists(), "after": not ap.exists()}})
            continue
        artifacts.append(diff_artifact(name, before, after, top))

    headlines = []
    for label, name, fn in HEADLINES:
        pair = docs.get(name, {})
        b, a = _value(fn, pair.get("before")), _value(fn, pair.get("after"))
        headlines.append({"label": label, "artifact": name, "before": b, "after": a,
                          "delta": None if b is None or a is None else round(a - b, 6)})
    return {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": AS_OF,
        "before_dir": _rel(before_dir), "after_dir": _rel(after_dir),
        "before_label": "published (revision 1, mixed-game corpus)",
        "after_label": "staged (revision 2, segmented corpus)",
        "artifacts": artifacts, "headlines": headlines,
    }


def render_markdown(report: Dict[str, Any]) -> str:
    """ASCII markdown, calibration and game-flow vocabulary only."""
    L = ["# In-game timing artifacts: regeneration diff (%s)" % report["as_of"], "",
         "BEFORE = the artifact published under `%s`, built from the" % report["before_dir"],
         "corpus in which 126 of 227 MLB files and 1 of 51 soccer files hold ticks from more",
         "than one real game. AFTER = the staged rebuild in `%s`," % report["after_dir"],
         "from `data/cache/ingame_grade_joined/{mlb,soccer_intl}_segmented` (one real game",
         "per file). This is the input to the publish decision, not the decision itself.", "",
         "## 0. How to read this -- before and after are DIFFERENT POPULATIONS", "",
         "Segmentation dropped 49 of 227 MLB files and 24 of 51 soccer files outright, so the",
         "after column describes 178 MLB and 27 soccer stored games instead of 227 and 51.",
         "Every move below is a POPULATION change. The measurement did not get sharper and no",
         "forecaster changed; these are the numbers the exhibits should have carried all along.",
         "Timing artifacts are hit harder than the label-consuming ones because a mixed file",
         "concatenates two score paths: a lead that 'never reverts' in the stored file can be",
         "two separate games' leads laid end to end, which pushes the point of no return later",
         "and inflates the live-clock fraction. Read the clock figures falling as that artifact",
         "being removed. Nothing here is a money statement.", "",
         "## 1. Headline figures", ""]
    body = [[h["label"], _num(h["before"]), _num(h["after"]), _num(h["delta"])]
            for h in report["headlines"]]
    L += _table(["figure", "before", "after", "delta"], body)

    L += ["", "## 2. Per-artifact scale of the change", ""]
    body = []
    for art in report["artifacts"]:
        if art.get("missing"):
            body.append([art["artifact"], "MISSING", "-", "-", "-"])
            continue
        body.append([art["artifact"], str(art["n_numeric_leaves_before"]),
                     str(art["n_numeric_leaves_after"]), str(art["n_count_moves"]),
                     str(art["n_moved"])])
    L += _table(["artifact", "leaves before", "leaves after", "count moves",
                 "other moves"], body)

    L += ["", "## 3. Per-artifact detail", ""]
    for art in report["artifacts"]:
        L += ["### %s" % art["artifact"], ""]
        if art.get("missing"):
            side = "before" if art["missing"]["before"] else "after"
            L += ["MISSING on the %s side -- not compared." % side, ""]
            continue
        if art["count_changes"]:
            L += ["Row/game counts:", ""]
            L += _table(["path", "before", "after", "delta"],
                        [[c["path"], _num(c["before"]), _num(c["after"]), _num(c["delta"])]
                         for c in art["count_changes"]])
            L.append("")
        if art["largest_changes"]:
            L += ["Largest absolute moves in other numeric fields:", ""]
            L += _table(["path", "before", "after", "delta"],
                        [[m["path"], _num(m["before"]), _num(m["after"]), _num(m["delta"])]
                         for m in art["largest_changes"]])
            L.append("")
        if not art["count_changes"] and not art["largest_changes"]:
            L += ["No numeric field moved.", ""]
    return "\n".join(L) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--before-dir", default=str(DEFAULT_BEFORE))
    ap.add_argument("--after-dir", default=str(DEFAULT_AFTER))
    ap.add_argument("--out-md", default=str(DEFAULT_MD))
    ap.add_argument("--top", type=int, default=8)
    args = ap.parse_args(argv)

    after_dir = Path(args.after_dir)
    if not after_dir.is_dir():
        print("NO_DATA: %s is not a directory" % after_dir)
        return 2
    report = build_report(Path(args.before_dir), after_dir, args.top)
    out_md = Path(args.out_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render_markdown(report), encoding="ascii")
    out_json = out_md.with_suffix(".json")
    out_json.write_text(json.dumps(report, indent=1, ensure_ascii=True), encoding="utf-8")
    print("\n".join(_table(["figure", "before", "after", "delta"],
                           [[h["label"], _num(h["before"]), _num(h["after"]), _num(h["delta"])]
                            for h in report["headlines"]])))
    print("\nwrote %s\nwrote %s" % (out_md, out_json))
    return 0


if __name__ == "__main__":
    sys.exit(main())
