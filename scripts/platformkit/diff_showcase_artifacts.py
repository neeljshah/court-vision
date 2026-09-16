"""scripts.platformkit.diff_showcase_artifacts -- diff the staged, segmented-corpus
showcase artifacts against the PUBLISHED ones, and write the reviewer's before/after.

The 13 label-consuming showcase modules were regenerated from
data/cache/ingame_grade_joined/{mlb,soccer_intl}_segmented (one real game per file)
into scripts/platformkit/analytics_showcase/out_segmented/. This compares each staged
artifact with the copy currently published under webapp/public/data/showcase/ so a
human can decide what, if anything, to publish. It publishes nothing itself.

Per artifact it reports the row/game counts that moved and the largest absolute moves in
every other numeric leaf, plus a fixed HEADLINES table of the figures a reader notices
first: MLB Brier (model and reference quote), ECE, the Murphy reliability/resolution
split, the late-inning .8-1 state cell, and how many reliability bins have a gap CI that
crosses zero. These are CALIBRATION measurements; a corrected corpus can move them
either way, and none of them is a profit statement.
From /c/Users/neelj/nba-ai-system: `python scripts/platformkit/diff_showcase_artifacts.py`
and `python -m pytest scripts/platformkit/test_diff_showcase_artifacts.py -q`.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_REPO = Path(__file__).resolve().parents[2]
DEFAULT_BEFORE = _REPO / "webapp" / "public" / "data" / "showcase"
DEFAULT_AFTER = _REPO / "scripts" / "platformkit" / "analytics_showcase" / "out_segmented"
DEFAULT_MD = _REPO / "docs" / "research" / "ingame_regeneration_diff_2026-09-16.md"

ARTIFACTS: Tuple[str, ...] = (
    "state_conditioned_calibration", "calibration_stability", "murphy_decomposition",
    "brier_skill_scores", "residual_anatomy", "calibration_by_market_type",
    "residual_autocorrelation", "calibration_over_time", "atlas_calibration_manifest",
    "market_disagreement_profile", "info_arrival_curve", "market_overreaction",
    "soccer_calibration_pack",
)
COUNT_KEYS = {"n", "n_rows", "n_games", "n_files", "n_records", "n_entries", "n_ticks",
              "n_usable_model", "n_usable_market", "n_skipped_no_state_field"}
TOP_CHANGES = 8
# (label, artifact, dict path). List members are reached by the bucket selector below,
# not by index, because list order is not stable across runs.
HEADLINES: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ("MLB game files scored", "calibration_by_market_type", ("market_types", "mlb_moneyline", "n_files")),
    ("MLB ticks scored", "calibration_by_market_type", ("market_types", "mlb_moneyline", "n_rows")),
    ("soccer game files scored", "calibration_by_market_type", ("market_types", "soccer_match", "n_files")),
    ("soccer ticks scored", "calibration_by_market_type", ("market_types", "soccer_match", "n_rows")),
    ("MLB Brier -- model", "brier_skill_scores", ("sports", "mlb", "grains", "all", "brier_model")),
    ("MLB Brier -- reference quote", "brier_skill_scores", ("sports", "mlb", "grains", "all", "brier_market")),
    ("MLB Brier -- climatology", "brier_skill_scores", ("sports", "mlb", "grains", "all", "brier_clim")),
    ("MLB base rate", "brier_skill_scores", ("sports", "mlb", "grains", "all", "base_rate")),
    ("MLB Brier gap, model minus reference", "calibration_by_market_type",
     ("market_types", "mlb_moneyline", "brier_gap_model_minus_market")),
    ("soccer Brier gap, model minus reference", "calibration_by_market_type",
     ("market_types", "soccer_match", "brier_gap_model_minus_market")),
    ("MLB ECE -- model", "calibration_by_market_type", ("market_types", "mlb_moneyline", "model_ece")),
    ("MLB ECE -- reference quote", "calibration_by_market_type", ("market_types", "mlb_moneyline", "market_ece")),
    ("MLB reliability -- model", "murphy_decomposition", ("sports", "mlb", "model_prob", "reliability")),
    ("MLB resolution -- model", "murphy_decomposition", ("sports", "mlb", "model_prob", "resolution")),
    ("MLB uncertainty", "murphy_decomposition", ("sports", "mlb", "model_prob", "uncertainty")),
    ("MLB reliability -- reference quote", "murphy_decomposition", ("sports", "mlb", "market_prob", "reliability")),
    ("MLB resolution -- reference quote", "murphy_decomposition", ("sports", "mlb", "market_prob", "resolution")),
    ("MLB reliability bins with gap CI crossing 0 -- model", "calibration_stability",
     ("sports", "mlb", "sides", "model_prob", "n_within_noise_bins")),
    ("MLB reliability bins with gap CI crossing 0 -- reference quote", "calibration_stability",
     ("sports", "mlb", "sides", "market_prob", "n_within_noise_bins")),
    ("soccer Brier -- model", "brier_skill_scores", ("sports", "soccer_intl", "grains", "all", "brier_model")),
    ("soccer Brier -- reference quote", "brier_skill_scores", ("sports", "soccer_intl", "grains", "all", "brier_market")),
)
LATE_CELL = ("state_conditioned_calibration", "late(inn7+)", ".8-1")  # state cell probe
LATE_FIELDS = ("n", "mean_p", "mean_y", "calibration_error")


def _rel(path: Any) -> str:  # repo-relative when inside the repo, else unchanged
    text, root = str(path).replace("\\", "/"), str(_REPO).replace("\\", "/") + "/"
    return text[len(root):] if text.startswith(root) else text


def numeric_leaves(obj: Any, path: str = "") -> Dict[str, float]:
    """Every numeric leaf as {"/a/b/0/c": value}. Booleans are not numbers here."""
    out: Dict[str, float] = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            out.update(numeric_leaves(value, "%s/%s" % (path, key)))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            out.update(numeric_leaves(value, "%s/%d" % (path, index)))
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        out[path] = float(obj)
    return out


def _is_count(path: str) -> bool:
    return path.rsplit("/", 1)[-1] in COUNT_KEYS


def dig(obj: Any, path: Sequence[str]) -> Optional[float]:
    """Follow a dict path; None when any step is missing or the leaf is not numeric."""
    for key in path:
        if not isinstance(obj, dict) or key not in obj:
            return None
        obj = obj[key]
    return float(obj) if isinstance(obj, (int, float)) and not isinstance(obj, bool) else None


def late_cell(doc: Any, sport: str, time_bucket: str, prob_bucket: str,
              source: str) -> Dict[str, Optional[float]]:
    """The one state-conditioned bucket row matching (time, prob, source), by value --
    bucket lists are not index-stable between runs."""
    buckets = (doc or {}).get("sports", {}).get(sport, {}).get("buckets", [])
    for row in buckets if isinstance(buckets, list) else []:
        if (row.get("time_bucket") == time_bucket and row.get("prob_bucket") == prob_bucket
                and row.get("source") == source):
            return {f: row.get(f) for f in LATE_FIELDS}
    return {f: None for f in LATE_FIELDS}


def diff_artifact(name: str, before: Any, after: Any,
                  top: int = TOP_CHANGES) -> Dict[str, Any]:
    """Count moves and the largest non-count numeric moves for one artifact."""
    a, b = numeric_leaves(before), numeric_leaves(after)
    shared = sorted(set(a) & set(b))
    counts = [{"path": p, "before": a[p], "after": b[p], "delta": b[p] - a[p]}
              for p in shared if _is_count(p) and a[p] != b[p]]
    moves = [{"path": p, "before": round(a[p], 6), "after": round(b[p], 6),
              "delta": round(b[p] - a[p], 6)}
             for p in shared if not _is_count(p) and abs(b[p] - a[p]) > 1e-9]
    moves.sort(key=lambda m: -abs(m["delta"]))
    return {
        "artifact": name,
        "n_numeric_leaves_before": len(a), "n_numeric_leaves_after": len(b),
        "n_leaves_only_before": len(set(a) - set(b)),
        "n_leaves_only_after": len(set(b) - set(a)),
        "n_moved": len(moves), "n_count_moves": len(counts),
        "count_changes": sorted(counts, key=lambda c: -abs(c["delta"]))[:top],
        "largest_changes": moves[:top],
    }


def build_report(before_dir: Path, after_dir: Path, top: int = TOP_CHANGES) -> Dict[str, Any]:
    """Load both sides for every artifact and assemble the full comparison."""
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
    for label, name, path in HEADLINES:
        pair = docs.get(name, {})
        b, a = dig(pair.get("before"), path), dig(pair.get("after"), path)
        headlines.append({"label": label, "artifact": name, "path": "/".join(path),
                          "before": b, "after": a,
                          "delta": None if b is None or a is None else round(a - b, 6)})
    name, tb, pb = LATE_CELL
    cells = []
    for source in ("model", "market"):
        b = late_cell(docs.get(name, {}).get("before"), "mlb", tb, pb, source)
        a = late_cell(docs.get(name, {}).get("after"), "mlb", tb, pb, source)
        cells.append({"source": source, "before": b, "after": a})
    return {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": "2026-09-16",
        "before_dir": _rel(before_dir), "after_dir": _rel(after_dir),
        "before_label": "published (contaminated corpus)",
        "after_label": "staged (segmented corpus)",
        "artifacts": artifacts, "headlines": headlines,
        "late_inning_high_confidence_cell": {
            "sport": "mlb", "time_bucket": tb, "prob_bucket": pb, "cells": cells},
    }


def _table(head: Sequence[str], body: Sequence[Sequence[str]]) -> List[str]:
    widths = [max([len(head[i])] + [len(r[i]) for r in body]) for i in range(len(head))]
    rows = ["| " + " | ".join(c.ljust(w) for c, w in zip(head, widths)) + " |",
            "|" + "|".join("-" * (w + 2) for w in widths) + "|"]
    return rows + ["| " + " | ".join(c.ljust(w) for c, w in zip(r, widths)) + " |"
                   for r in body]


def _num(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return str(int(value)) if float(value).is_integer() else "%.6f" % value


def render_markdown(report: Dict[str, Any]) -> str:
    """ASCII markdown. Calibration vocabulary only -- no edge/profit framing."""
    L = ["# In-game corpus segmentation: regeneration diff (2026-09-16)", "",
         "BEFORE = the artifact published under `%s`, built from the corpus in which 126 of"
         % report["before_dir"],
         "227 MLB files hold ticks from more than one real game. AFTER = the staged artifact",
         "in `%s`, rebuilt from" % report["after_dir"],
         "`data/cache/ingame_grade_joined/{mlb,soccer_intl}_segmented` (one real game per",
         "file). Nothing here is published; this is the input to that decision. Every figure",
         "below is a CALIBRATION measurement -- reliability, resolution, Brier, ECE. A",
         "corrected corpus can move them either way and none of them is a profit statement.",
         "Truth source: `docs/JOB_EVIDENCE_PACKET.md`.", "",
         "Rebuild: `python scripts/platformkit/segment_ingame_join.py`, regenerate with",
         "`CV_INGAME_CORPUS_SUFFIX=_segmented`, then",
         "`python scripts/platformkit/diff_showcase_artifacts.py`.", "",
         "## 0. How to read this -- before and after are DIFFERENT POPULATIONS", "",
         "Segmentation dropped every tick it could not attribute to the labelled game, so the",
         "after column is scored on a smaller, differently-mixed sample (first four rows of",
         "section 1). A lower Brier or ECE here is NOT evidence the forecaster improved -- the",
         "forecaster did not change. It means the earlier figure was measured against ticks",
         "whose label belonged to another game. Read each move as what the measurement should",
         "have said, not as a gain, and note that the smaller sample widens every interval.",
         "Soccer moves the other way and gets the same plainness: its draw share falls from",
         "26% to 14% of ticks, and a draw (outcome 0.5) is mechanically cheap to score against",
         "a two-way probability, so BOTH the model and the reference quote post a higher Brier",
         "on the segmented soccer sample. The model-minus-reference gap is the like-for-like",
         "line to read; it halves for MLB and widens for soccer.", "",
         "## 1. Headline figures", ""]
    body = [[h["label"], _num(h["before"]), _num(h["after"]), _num(h["delta"])]
            for h in report["headlines"]]
    L += _table(["figure", "before", "after", "delta"], body)

    cell = report["late_inning_high_confidence_cell"]
    L += ["", "## 2. Late-inning high-confidence state cell (%s x %s, mlb)"
          % (cell["time_bucket"], cell["prob_bucket"]), ""]
    body = []
    for c in cell["cells"]:
        for field in LATE_FIELDS:
            body.append([c["source"], field, _num(c["before"].get(field)),
                         _num(c["after"].get(field))])
    L += _table(["source", "field", "before", "after"], body)

    L += ["", "## 3. Per-artifact scale of the change", ""]
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

    L += ["", "## 4. Per-artifact detail", ""]
    for art in report["artifacts"]:
        L += ["### %s" % art["artifact"], ""]
        if art.get("missing"):
            side = "before" if art["missing"]["before"] else "after"
            L += ["MISSING on the %s side -- not compared." % side, ""]
            continue
        if art["count_changes"]:
            L += ["Row/game counts:", ""]
            L += _table(["path", "before", "after", "delta"],
                        [[c["path"], _num(c["before"]), _num(c["after"]),
                          _num(c["delta"])] for c in art["count_changes"]])
            L.append("")
        if art["largest_changes"]:
            L += ["Largest absolute moves in other numeric fields:", ""]
            L += _table(["path", "before", "after", "delta"],
                        [[m["path"], _num(m["before"]), _num(m["after"]),
                          _num(m["delta"])] for m in art["largest_changes"]])
            L.append("")
        if not art["count_changes"] and not art["largest_changes"]:
            L += ["No numeric field moved.", ""]
    return "\n".join(L) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--before-dir", default=str(DEFAULT_BEFORE))
    ap.add_argument("--after-dir", default=str(DEFAULT_AFTER))
    ap.add_argument("--out-md", default=str(DEFAULT_MD))
    ap.add_argument("--top", type=int, default=TOP_CHANGES)
    args = ap.parse_args(argv)

    before_dir, after_dir = Path(args.before_dir), Path(args.after_dir)
    if not after_dir.is_dir():
        print("NO_DATA: %s is not a directory" % after_dir)
        return 2
    report = build_report(before_dir, after_dir, args.top)
    out_md = Path(args.out_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render_markdown(report), encoding="ascii")
    out_json = out_md.with_suffix(".json")
    out_json.write_text(json.dumps(report, indent=1, ensure_ascii=True), encoding="utf-8")
    body = [[h["label"], _num(h["before"]), _num(h["after"]), _num(h["delta"])]
            for h in report["headlines"]]
    print("\n".join(_table(["figure", "before", "after", "delta"], body)))
    print("\nwrote %s\nwrote %s" % (out_md, out_json))
    return 0


if __name__ == "__main__":
    sys.exit(main())
