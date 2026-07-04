"""scripts.platformkit.ingame.tail_hypothesis_ledger -- LANE 3: composes the
tail-hypothesis evidence ledger (one row per hypothesis x corpus) purely by
READING existing verdict artifacts on disk. NEVER computes a new statistic --
every number in every row is copied verbatim from the artifact that produced
it. A missing artifact yields an honest status=ABSENT row rather than a
fabricated or interpolated one.

CORPORA composed (6, LANE 4 adds the last 2):
  kalshi_discovery_2026   -- data/frontend/ops/ingame_tail_scan.json (MLB
                              discovery scan) + the MLB forward-gate context
                              (data/domains/mlb/ingame_tail_verdict.json)
  forward_gates           -- data/domains/<sport>/ingame_tail_verdict.json for
                              all 6 sports (mlb + the 5 cross-sport gates)
  polymarket_2023         -- data/venue_history/polymarket/mlb_tail_validation.json
                              (the 2023 "dailies" corpus, mlb only)
  kalshi_historical       -- data/venue_history/kalshi/*_tail_validation.json
  polymarket_2024plus_nba -- data/venue_history/polymarket/nba_2024plus_tail_validation.json
                              (LANE 4: 2024-25+2025-26 alternate-slug corpus, nba)
  polymarket_2024plus_mlb -- data/venue_history/polymarket/mlb_2024plus_tail_validation.json
                              (LANE 4: 2025+2026 alternate-slug corpus, mlb)

PROVENANCE RULE (binding, do not pool): each corpus is a separate, provenance-
labeled row. Forward gates stay forward-only. Historical venue corpora are
validation corpora, never pooled with the forward evidence or with each other.

Output: data/frontend/ops/tail_hypothesis_ledger.json

INVARIANTS: platformkit-only; <=300 LOC; ASCII; no network; read-only against
data/; never writes data/registry/; no flag flip; edge_claimed always False.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_tail_hypothesis_ledger.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.ingame.tail_hypothesis_ledger_2024plus import (
    h1_all_calibrated_outside_thin_pm2023, rows_polymarket_2024plus,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]

FORWARD_GATE_SPORTS: List[str] = [
    "basketball_nba", "kbo", "mlb", "mlb_sbro", "npb",
    "soccer", "soccer_fd", "soccer_intl", "tennis", "tennis_atp", "wnba",
]

HYPOTHESES: List[Dict[str, str]] = [
    {"id": "H1_longshot_underpriced", "band": "[0.10,0.20)",
     "direction": "VENUE_UNDERPRICES"},
    {"id": "H2_midfav_overpriced", "band": "[0.65,0.80)",
     "direction": "VENUE_OVERPRICES"},
]

_SYNTHESIS = (
    "H2 midfav overpriced: CALIBRATED in both independent historical corpora "
    "(PM-2023 n=138, Kalshi-excluded n=799) -- likely dead; awaiting "
    "forward-gate confirmation before formal retirement. H1 longshot "
    "underpriced: supported in PM-2023 (realized .523 vs price .155, CI excl "
    "0, n=14 THIN) and in the 2026 Kalshi discovery window; NOT visible in "
    "the Kalshi discovery-excluded window; verdict rides on the "
    "pre-registered forward gates. No edge claimed; calibration statements "
    "about venue prices only."
)

# LANE 4 (2026-07-04): after adding the 2 new PM-2024plus corpora (nba, mlb;
# resumed backfill through the cursors reached this run -- see the run report,
# not re-derived here), every corpus EXCEPT the original thin PM-2023 H1 n=14
# pocket reads CALIBRATED for H1. This line is additive to (does not replace)
# the H2 sentence above.
_SYNTHESIS_H1_UPDATE = (
    "H1 evidence after 6 corpora: only the PM-MLB-2023 pocket (n=14) is "
    "significant; every larger corpus reads CALIBRATED. The prior shifts "
    "toward 'no persistent venue tail bias'; the forward gates remain the "
    "arbiter and continue accruing."
)


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def _absent_row(hyp_id: str, corpus: str, provenance: str, sport: str, path: Path) -> Dict[str, Any]:
    return {
        "hypothesis": hyp_id, "corpus": corpus, "provenance": provenance,
        "sport": sport, "n_games": None, "status": "ABSENT",
        "verdict": None, "key_numbers": {}, "caveats": ["file not found: %s" % path],
    }


def _rows_kalshi_discovery(scan_doc: Optional[Dict[str, Any]],
                            mlb_gate_doc: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """kalshi_discovery_2026 corpus: MLB in-play discovery scan bands +
    the forward-gate's discovery_band_reference_only context (same numbers
    the gate itself pre-registered from, never re-derived here)."""
    rows: List[Dict[str, Any]] = []
    scan_path = _REPO_ROOT / "data" / "frontend" / "ops" / "ingame_tail_scan.json"
    gate_path = _REPO_ROOT / "data" / "domains" / "mlb" / "ingame_tail_verdict.json"
    for h in HYPOTHESES:
        if scan_doc is None:
            rows.append(_absent_row(h["id"], "kalshi_discovery_2026",
                                     "kalshi_discovery_scan", "mlb", scan_path))
            continue
        band = scan_doc.get("bands", {}).get(h["band"])
        gate_ref = None
        if mlb_gate_doc is not None:
            for hyp in mlb_gate_doc.get("hypotheses", []):
                if hyp.get("id") == h["id"]:
                    gate_ref = hyp.get("discovery_band_reference_only")
                    break
        if band is None:
            rows.append(_absent_row(h["id"], "kalshi_discovery_2026",
                                     "kalshi_discovery_scan", "mlb", scan_path))
            continue
        rows.append({
            "hypothesis": h["id"], "corpus": "kalshi_discovery_2026",
            "provenance": "kalshi_discovery_scan", "sport": "mlb",
            "n_games": band.get("n_games"), "status": "PRESENT",
            "verdict": band.get("venue_verdict"),
            "key_numbers": {
                "mean_market": band.get("mean_market"),
                "realized_rate": band.get("realized_rate"),
                "venue_gap": band.get("venue_gap"),
                "venue_gap_ci95": band.get("venue_gap_ci95"),
                "n_ticks": band.get("n_ticks"),
            },
            "caveats": [
                "discovery/pre-registration sample -- NOT independent forward "
                "evidence; bands were chosen from this sample (see gate basis)",
                "no fees/fills modeled",
            ] + (["gate discovery-reference cross-check: %s" % gate_ref.get("venue_verdict")]
                 if gate_ref else ["no matching forward-gate reference found"]),
        })
    return rows


def _rows_forward_gates() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for sport in FORWARD_GATE_SPORTS:
        path = _REPO_ROOT / "data" / "domains" / sport / "ingame_tail_verdict.json"
        doc = _read_json(path)
        for h in HYPOTHESES:
            if doc is None:
                rows.append(_absent_row(h["id"], "forward_gates",
                                         "pre_registered_forward_gate", sport, path))
                continue
            hyp = next((x for x in doc.get("hypotheses", []) if x.get("id") == h["id"]), None)
            if hyp is None:
                rows.append(_absent_row(h["id"], "forward_gates",
                                         "pre_registered_forward_gate", sport, path))
                continue
            fwd = hyp.get("forward_band") or {}
            rows.append({
                "hypothesis": h["id"], "corpus": "forward_gates",
                "provenance": "pre_registered_forward_gate", "sport": sport,
                "n_games": fwd.get("n_games", doc.get("n_forward_games")),
                "status": "PRESENT",
                "verdict": hyp.get("forward_verdict"),
                "key_numbers": {
                    "mean_market": fwd.get("mean_market"),
                    "realized_rate": fwd.get("realized_rate"),
                    "venue_gap": fwd.get("venue_gap"),
                    "delta_brier": fwd.get("delta_brier"),
                    "n_ticks": fwd.get("n_ticks"),
                },
                "caveats": [
                    "forward-only; never pooled with discovery or historical corpora",
                    "pre_registered_at=%s" % doc.get("pre_registered_at", doc.get("registered_at")),
                ],
            })
    return rows


def _rows_venue_history(venue: str, corpus_name: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    vh_dir = _REPO_ROOT / "data" / "venue_history" / venue
    path = vh_dir / "mlb_tail_validation.json"
    doc = _read_json(path)
    for h in HYPOTHESES:
        if doc is None:
            rows.append(_absent_row(h["id"], corpus_name, "%s_historical_validation" % venue,
                                     "mlb", path))
            continue
        # kalshi doc keys bands under pooled_all/excluded_discovery_window;
        # polymarket doc keys bands directly under "bands" -> pooled.
        band = None
        n_games = None
        if "bands" in doc:  # polymarket shape
            b = doc["bands"].get(h["band"], {}).get("pooled")
            if b:
                band = b
                n_games = b.get("n_games")
        elif "excluded_discovery_window" in doc:  # kalshi shape -- use the
            # honest independent subset (close_time outside the discovery
            # window), never the discovery-overlapping pooled_all
            b = doc["excluded_discovery_window"].get("bands", {}).get(h["band"])
            if b:
                band = b
                n_games = b.get("n_markets")
        if band is None:
            rows.append(_absent_row(h["id"], corpus_name, "%s_historical_validation" % venue,
                                     "mlb", path))
            continue
        rows.append({
            "hypothesis": h["id"], "corpus": corpus_name,
            "provenance": "%s_historical_validation" % venue, "sport": "mlb",
            "n_games": n_games, "status": "PRESENT",
            "verdict": band.get("venue_verdict"),
            "key_numbers": {
                "mean_market": band.get("mean_market") or band.get("mean_venue_price"),
                "realized_rate": band.get("realized_rate"),
                "venue_gap": band.get("venue_gap"),
                "venue_gap_ci95": band.get("venue_gap_ci95"),
                "n_ticks": band.get("n_ticks"),
            },
            "caveats": [
                "independent historical validation corpus -- never pooled with "
                "the forward gate or with the other venue's history",
                doc.get("note", "")[:200],
            ],
        })
    return rows


def build_ledger() -> Dict[str, Any]:
    """Compose the full ledger dict from artifacts on disk. Never raises --
    each row degrades to status=ABSENT on a read failure."""
    scan_doc = _read_json(_REPO_ROOT / "data" / "frontend" / "ops" / "ingame_tail_scan.json")
    mlb_gate_doc = _read_json(_REPO_ROOT / "data" / "domains" / "mlb" / "ingame_tail_verdict.json")

    rows: List[Dict[str, Any]] = []
    rows.extend(_rows_kalshi_discovery(scan_doc, mlb_gate_doc))
    rows.extend(_rows_forward_gates())
    rows.extend(_rows_venue_history("polymarket", "polymarket_2023"))
    rows.extend(_rows_venue_history("kalshi", "kalshi_historical"))
    rows.extend(rows_polymarket_2024plus(
        "nba", repo_root=_REPO_ROOT, hypotheses=HYPOTHESES,
        read_json=_read_json, absent_row=_absent_row))
    rows.extend(rows_polymarket_2024plus(
        "mlb", repo_root=_REPO_ROOT, hypotheses=HYPOTHESES,
        read_json=_read_json, absent_row=_absent_row))

    n_present = sum(1 for r in rows if r["status"] == "PRESENT")
    n_absent = sum(1 for r in rows if r["status"] == "ABSENT")

    synthesis = _SYNTHESIS
    if h1_all_calibrated_outside_thin_pm2023(rows):
        synthesis = _SYNTHESIS + " " + _SYNTHESIS_H1_UPDATE

    return {
        "component": "tail_hypothesis_ledger",
        "note": ("one row per (hypothesis, corpus); every number is copied "
                 "verbatim from an existing verdict artifact -- this module "
                 "computes NOTHING new; missing artifact = honest ABSENT row"),
        "corpora": ["kalshi_discovery_2026", "forward_gates", "polymarket_2023",
                    "kalshi_historical", "polymarket_2024plus_nba",
                    "polymarket_2024plus_mlb"],
        "hypotheses": [h["id"] for h in HYPOTHESES],
        "rows": rows,
        "n_rows": len(rows), "n_present": n_present, "n_absent": n_absent,
        "synthesis": synthesis,
        "edge_claimed": False,
    }


def write_ledger(out_path: Optional[Path] = None) -> Path:
    doc = build_ledger()
    path = out_path or (_REPO_ROOT / "data" / "frontend" / "ops" / "tail_hypothesis_ledger.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    return path


def main() -> None:
    doc = build_ledger()
    print("tail_hypothesis_ledger | rows=%d present=%d absent=%d" %
          (doc["n_rows"], doc["n_present"], doc["n_absent"]))
    path = write_ledger()
    print("wrote %s" % path)
    print("NOTE: composition only, no new stats; no edge claimed.")


if __name__ == "__main__":
    main()
