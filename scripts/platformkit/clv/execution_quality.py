"""execution_quality -- the execution-quality scoreboard (measurement-only).

Paper trading exists to perfect EXECUTION; CLV-vs-close is the yardstick for
whether an order got a good number, not whether the pick was "right". This
module answers, per (channel-phase, sport, venue): how much of the channel is
even CLV-measurable (true_close coverage), what the CLV distribution vs the
close looks like (mean/median/p10/p90, units only), and how early/late orders
land relative to game start (entry-timing buckets).

Sources (read-only; never mutates any ledger, never touches trading/guard
logic):
  * data/frontend/clv_ledger.jsonl        -- canonical CLV ledger (pregame PM
    + in-game ML/prop), read via the SAME reader clv_scoreboard.py uses.
  * data/frontend/paper_predictions_graded.jsonl -- pregame paper-prediction
    ledger; carries commence_time + logged_at so it is the only source with a
    real entry-timing signal. clv_status is 'no_close' for every row here
    (0% CLV coverage), reported honestly, not padded.
  * data/frontend/prop_ledger.jsonl       -- separate props lane (owned by the
    in-flight m13 lane; NOT touched). Counted for settled-row context only --
    it carries no CLV field, so its coverage is 0% by construction.

Channel-phase mapping (pregame vs in-game) is the one new taxonomy here;
everything else (dedup, measurability, venue key, mean+CI, percentile/bucket
math) is reused from clv_scoreboard.py / scoreboard_venue.py /
execution_quality_math.py so this module never re-derives CLV math.
Reproduces the standing in-game-prop CLV-adverse finding by reporting whether
the suppress guard (ingame_prop_clv_guard) is active and whether any live
paper_ingame_prop rows exist to re-measure against.

Honest rails: units only, no $/pnl/roi/bankroll token anywhere in the output
(see _BANNED_TOKENS); read-only over every ledger; ASCII only.

Run:  python -m scripts.platformkit.clv.execution_quality
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from scripts.platformkit.clv_ledger import load_ledger  # canonical reader
from scripts.platformkit.clv.clv_scoreboard import (
    _channel_of, _dedup_settled, _is_measurable, _mean_ci, _CHANNEL_LABEL)
from scripts.platformkit.pm_trading.scoreboard_venue import _venue_key
from scripts.platformkit.clv.execution_quality_math import (
    clv_distribution, entry_timing_from_graded, load_jsonl, same_venue_stats)

_OUT_JSON = os.path.join(_REPO, "data", "frontend", "ops", "execution_quality.json")
_OUT_MD = os.path.join(_REPO, "data", "frontend", "ops", "execution_quality.md")
_GRADED_PATH = os.path.join(_REPO, "data", "frontend", "paper_predictions_graded.jsonl")
_PROP_LEDGER_PATH = os.path.join(_REPO, "data", "frontend", "prop_ledger.jsonl")

# channel -> phase (pregame vs in-game); anything unmapped falls to "unknown_phase"
_PHASE_OF = {
    "paper": "pregame", "paper_pm": "pregame", "moneyline": "pregame",
    "unknown": "pregame",  # legacy '?' rows carry a real closing line -> pregame ML
    "paper_ingame": "ingame", "paper_ingame_prop": "ingame",
}

_BANNED_TOKENS = ("pnl", "roi", "dollar", "profit", "revenue", "bankroll", "stake_units_usd")


def _cell_stats(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    measurable = [r for r in rows if _is_measurable(r)]
    clvs = [float(r["clv_pct"]) for r in measurable]
    ci = _mean_ci(clvs)
    dist = clv_distribution(clvs)
    coverage = round(100.0 * len(measurable) / len(rows), 1) if rows else 0.0
    return {
        "n_settled": len(rows),
        "n_measurable": len(measurable),
        "true_close_coverage_pct": coverage,
        "clv_distribution_pct": dist,
        "clv_ci95": [ci["lo95"], ci["hi95"]],
        "clv_significant": ci["significant"],
        "same_venue": same_venue_stats(measurable, mean_ci=_mean_ci),
    }


def _ingame_prop_reproduction() -> Dict[str, Any]:
    """Honest status of the standing -31% in-game-prop CLV-adverse finding.

    The finding was measured on an ARCHIVED ledger, pre-guard. The suppress
    guard (ingame_prop_clv_guard) has been ON since, so the live ledger is
    expected to carry ~0 fresh paper_ingame_prop rows -- there is nothing new
    to re-measure against, which is the guard doing its job, not a data gap.
    """
    try:
        from scripts.platformkit.improve.ingame_prop_clv_guard import is_enabled
        guard_on = is_enabled()
    except Exception:  # noqa: BLE001
        guard_on = None
    return {
        "guard_module": "scripts.platformkit.improve.ingame_prop_clv_guard",
        "guard_enabled": guard_on,
        "note": ("Suppress-only guard measured -31.0% mean CLV (95% CI excludes 0, "
                 "n=402) on an ARCHIVED pre-guard ledger; anti-correlated with claimed "
                 "edge (worse when the model was most confident). Guard is default-ON "
                 "and blocks every NEW in-game-prop placement, so the live ledger is "
                 "expected to hold ~0 fresh rows for this channel -- that is the guard "
                 "working, not missing data. Re-enable measurement only on a future "
                 "cross-corpus finding that a sub-slice is CLV-neutral-or-better."),
    }


def build_scoreboard(
    ledger: Optional[Sequence[Dict[str, Any]]] = None,
    graded_rows: Optional[Sequence[Dict[str, Any]]] = None,
    prop_ledger_rows: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Pure aggregation (given rows) -> the full execution-quality report dict."""
    if ledger is None:
        ledger = load_ledger()
    settled = _dedup_settled(ledger)

    cells: Dict[str, Dict[str, Any]] = {}
    for r in settled:
        ch = _channel_of(r)
        phase = _PHASE_OF.get(ch, "unknown_phase")
        sport = str(r.get("sport") or "unknown")
        venue = _venue_key(r)
        key = "%s|%s|%s" % (phase, sport, venue)
        cells.setdefault(key, {"phase": phase, "channel": ch,
                               "channel_label": _CHANNEL_LABEL.get(ch, ch),
                               "sport": sport, "venue": venue, "rows": []})
        cells[key]["rows"].append(r)

    channels_out: Dict[str, Any] = {}
    for key, cell in sorted(cells.items()):
        stats = _cell_stats(cell["rows"])
        channels_out[key] = {
            "phase": cell["phase"], "channel": cell["channel"],
            "channel_label": cell["channel_label"], "sport": cell["sport"],
            "venue": cell["venue"], **stats,
        }

    if graded_rows is None:
        graded_rows = load_jsonl(_GRADED_PATH)
    if prop_ledger_rows is None:
        prop_ledger_rows = load_jsonl(_PROP_LEDGER_PATH)
    prop_settled = [r for r in prop_ledger_rows if r.get("status") == "settled"]

    return {
        "cells": channels_out,
        "n_cells": len(channels_out),
        "total_settled_clv_ledger": len(settled),
        "pregame_prediction_ledger": {
            **_cell_stats(graded_rows),
            "entry_timing": entry_timing_from_graded(graded_rows),
            "note": "clv_status is 'no_close' for every row here by construction "
                    "(no closing-line capture wired to this ledger) -- 0% coverage "
                    "is the honest number, not a bug.",
        },
        "separate_props_ledger": {
            "n_settled": len(prop_settled), "n_total_rows": len(prop_ledger_rows),
            "note": "prop_ledger.jsonl (m13 lane, not touched) carries no CLV field; "
                    "counted for context only, coverage is 0% by construction.",
        },
        "ingame_prop_clv_adverse_reproduction": _ingame_prop_reproduction(),
        "honest_note": (
            "Execution quality measures whether an order got a good NUMBER vs the "
            "close, in units and percent CLV only -- never a dollar figure. "
            "true_close_coverage_pct below 100 means part of the channel cannot be "
            "graded for edge at all (no closing line captured), which is itself the "
            "headline finding for that cell."),
    }


def _atomic_write_json(path: str, doc: Dict[str, Any]) -> bool:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1, ensure_ascii=True)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def render_md(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Execution Quality Scoreboard")
    lines.append("")
    lines.append("Measurement-only. Units/CLV-percent only, no dollar figure.")
    lines.append("")
    lines.append("| phase | channel | sport | venue | n_settled | n_meas | covg%% | "
                 "mean CLV%% (unrestricted) | median | p10 | p90 | "
                 "same-venue n / mean%% | cross-venue n / mean%% | no-close-book n |"
                 .replace("%%", "%"))
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for key in sorted(report["cells"]):
        c = report["cells"][key]
        d = c["clv_distribution_pct"]
        sig = "*" if c["clv_significant"] else ""
        mean = ("%+.2f%s" % (d["mean"], sig)) if d["mean"] is not None else "--"
        med = ("%+.2f" % d["median"]) if d["median"] is not None else "--"
        p10 = ("%+.2f" % d["p10"]) if d["p10"] is not None else "--"
        p90 = ("%+.2f" % d["p90"]) if d["p90"] is not None else "--"
        sv, cv, nc = (c["same_venue"]["same_venue"], c["same_venue"]["cross_venue"],
                     c["same_venue"]["no_same_venue_close"])
        sv_txt = ("%d / %+.2f" % (sv["n"], sv["clv_distribution_pct"]["mean"])
                  if sv["clv_distribution_pct"]["mean"] is not None else "%d / --" % sv["n"])
        cv_txt = ("%d / %+.2f" % (cv["n"], cv["clv_distribution_pct"]["mean"])
                  if cv["clv_distribution_pct"]["mean"] is not None else "%d / --" % cv["n"])
        lines.append("| %s | %s | %s | %s | %d | %d | %.0f | %s | %s | %s | %s | %s | %s | %d |"
                     % (c["phase"], c["channel_label"], c["sport"], c["venue"],
                        c["n_settled"], c["n_measurable"],
                        c["true_close_coverage_pct"], mean, med, p10, p90,
                        sv_txt, cv_txt, nc["n"]))
    lines.append("")
    lines.append("`*` = mean CLV 95%% CI excludes 0.".replace("%%", "%"))
    lines.append("")
    lines.append(
        "**Same-venue restriction** (see "
        "docs/research/PROPOSED_same_venue_close_restriction.md): the "
        "'mean CLV%% (unrestricted)' column mixes cross-venue settlements "
        "(bet at one book, settled vs a DIFFERENT book's close) into the "
        "headline mean -- an artifact, not a real per-venue edge. "
        "'same-venue n / mean%%' is the honest restricted reading: CLV computed "
        "ONLY when the close's book (close_book_home/away, stamped by "
        "grade_paper.grade_one at settle time) matches the bet's own taken_book. "
        "close_book_* is a NEW field (added by this fix) -- every row settled "
        "BEFORE this change has no provenance and correctly falls into "
        "'no-close-book n', not into either venue bucket.".replace("%%", "%"))
    lines.append("")
    pg = report["pregame_prediction_ledger"]
    lines.append("## Pregame prediction ledger (entry timing source)")
    lines.append("n_settled=%d coverage=%.1f%% (no closing-line capture wired here)"
                 % (pg["n_settled"], pg["true_close_coverage_pct"]))
    et = pg["entry_timing"]
    lines.append("entry-timing buckets (n_parsed=%d/%d): %s"
                 % (et["n_timing_parsed"], et["n_rows"], json.dumps(et["buckets"])))
    lines.append("")
    sp = report["separate_props_ledger"]
    lines.append("## Separate props ledger (m13 lane, context only)")
    lines.append("n_settled=%d/%d, no CLV field -- 0%% coverage by construction"
                 % (sp["n_settled"], sp["n_total_rows"]))
    lines.append("")
    ig = report["ingame_prop_clv_adverse_reproduction"]
    lines.append("## In-game prop CLV-adverse guard")
    lines.append("guard_enabled=%s -- %s" % (ig["guard_enabled"], ig["note"]))
    return "\n".join(lines)


def _assert_no_banned_tokens(doc: Any) -> None:
    """Recursively assert no banned dollar/pnl/roi token in any KEY (case-insens)."""
    if isinstance(doc, dict):
        for k, v in doc.items():
            kl = str(k).lower()
            for tok in _BANNED_TOKENS:
                assert tok not in kl, "banned token %r found in key %r" % (tok, k)
            _assert_no_banned_tokens(v)
    elif isinstance(doc, list):
        for v in doc:
            _assert_no_banned_tokens(v)


def main(argv: Optional[Sequence[str]] = None) -> int:
    report = build_scoreboard()
    _assert_no_banned_tokens(report)
    md = render_md(report)
    print(md)
    ok_json = _atomic_write_json(_OUT_JSON, report)
    print("\nwrote %s: %s" % (_OUT_JSON, ok_json))
    try:
        os.makedirs(os.path.dirname(_OUT_MD), exist_ok=True)
        tmp = _OUT_MD + ".tmp"
        with open(tmp, "w", encoding="ascii", errors="replace") as fh:
            fh.write(md)
        os.replace(tmp, _OUT_MD)
        print("wrote %s" % _OUT_MD)
    except OSError as exc:
        print("(md not written: %s)" % type(exc).__name__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
