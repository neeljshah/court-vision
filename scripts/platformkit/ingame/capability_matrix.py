"""In-game capability matrix: per-sport latency/coverage/calibration readout.

Reads MEASURED artifacts named in docs/research/organization-sprint/
INGAME_CAPABILITY_2026-09-01.md; never hardcodes a number. A missing or
corrupt artifact marks that cell UNMEASURED (fail-closed) -- ROWS is still
built, the CLI still exits 0, only the affected cell says UNMEASURED.
No edge/ROI claims: latency/coverage/calibration language only.

Viability classes (EVENT_REACTIVE / SLOW_STATE / DARK) reuse
latency_scoreboard.py's pre-registered gate constants verbatim; they are
never redefined here.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.ingame import arm_registry
from scripts.platformkit.ingame import latency_scoreboard as gates
from scripts.platformkit.odds_provider import kalshi_series_spec

REPO_ROOT = Path(__file__).resolve().parents[3]
TICK_LATENCY_PATH = REPO_ROOT / "data" / "frontend" / "ops" / "inplay_tick_latency.json"
CROSSVENUE_LAG_PATH = REPO_ROOT / "data" / "frontend" / "ops" / "latency_audit.json"
NBA_NEWSPRIOR_PATH = REPO_ROOT / "data" / "cache" / "benchmarks" / "ingame_nba_newsprior_verdict.json"
GAP_LEDGER_CELLS_PATH = REPO_ROOT / "scripts" / "platformkit" / "gap_ledger_cells.tsv"
OUT_PATH = REPO_ROOT / "data" / "cache" / "ingame" / "capability_matrix.json"
SOCCER_ARM_DOC = (REPO_ROOT / "docs" / "research" / "organization-sprint" /
                  "PROPOSED_soccer_inplay_suppression.md")

UNMEASURED = "UNMEASURED"
EVENT_REACTIVE = "EVENT_REACTIVE"
SLOW_STATE = "SLOW_STATE"
DARK = "DARK"
VIABILITY_CLASSES = frozenset((EVENT_REACTIVE, SLOW_STATE, DARK))

# (display sport, internal key used by inplay_tick_latency.json's by_sport map)
_SPORT_KEYS = (
    ("MLB", "mlb"),
    ("Soccer (domestic, e.g. EPL)", "soccer"),
    ("Soccer (international / World Cup)", "soccer_intl"),
    ("NBA", "nba"),
    ("Tennis", "tennis"),
    ("NFL", "nfl"),
)


def _load_json(path: Path) -> Optional[dict]:
    """Fail-closed JSON read: any missing/unreadable/corrupt file -> None, never raises."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _field(source: dict, name: str) -> Any:
    """source.get(name), with a JSON null (as well as an absent key) mapped to
    UNMEASURED -- a source artifact may legitimately store null for a value it
    could not compute (e.g. a sport with zero games), and that is not the same
    as this matrix having read nothing."""
    value = source.get(name)
    return UNMEASURED if value is None else value


def _cadence(key: str, tick_doc: Optional[dict]) -> Dict[str, Any]:
    row = (tick_doc or {}).get("by_sport", {}).get(key)
    if not row:
        return {"tick_p50_sec": UNMEASURED, "tick_p90_sec": UNMEASURED,
                "n_games": UNMEASURED, "n_ticks": UNMEASURED,
                "source_verdict": UNMEASURED, "lag_p90_sec": UNMEASURED,
                "src_ts_coverage_pct": UNMEASURED, "capture_lag_p50_sec": UNMEASURED,
                "artifact": str(TICK_LATENCY_PATH)}
    # The EVENT_REACTIVE gate is defined on lag_p90 AND src_ts coverage. This corpus
    # carries neither key (schema_has_venue_ts=false for every sport), so both read
    # UNMEASURED and the gate fails closed. capture_lag_vs_venue_sec_p50 is a p50 and is
    # reported under its own p50 name -- it is NEVER substituted into the p90 gate.
    return {"tick_p50_sec": _field(row, "gap_p50_sec"),
            "tick_p90_sec": _field(row, "gap_p90_sec"),
            "n_games": _field(row, "n_games"),
            "n_ticks": _field(row, "n_ticks"),
            "source_verdict": _field(row, "verdict"),
            "lag_p90_sec": _field(row, "lag_p90_sec"),
            "src_ts_coverage_pct": _field(row, "src_ts_coverage_pct"),
            "capture_lag_p50_sec": _field(row, "capture_lag_vs_venue_sec_p50"),
            "artifact": str(TICK_LATENCY_PATH)}


def _crossvenue(key: str, audit_doc: Optional[dict]) -> Dict[str, Any]:
    # Only MLB's latency_audit.json exists today; every other sport is UNMEASURED
    # rather than borrowing MLB's number.
    if key != "mlb" or not audit_doc:
        return {"median_lag_sec": UNMEASURED, "caveat": UNMEASURED, "artifact": str(CROSSVENUE_LAG_PATH)}
    kalshi = audit_doc.get("kalshi", {})
    return {"median_lag_sec": _field(kalshi, "median_lag_seconds"),
            "caveat": _field(audit_doc, "method_caveat"),
            "artifact": str(CROSSVENUE_LAG_PATH)}


def _nba_calibration(key: str, verdict_doc: Optional[dict]) -> Dict[str, Any]:
    if key != "nba" or not verdict_doc:
        return {"unadjusted_brier": UNMEASURED, "market_brier": UNMEASURED,
                "verdict_vs_market": UNMEASURED, "artifact": str(NBA_NEWSPRIOR_PATH)}
    cp = verdict_doc.get("checkpoints", {}).get("end_q1", {})
    return {"unadjusted_brier": _field(cp, "unadjusted_brier_mean"),
            "market_brier": _field(cp, "market_brier_mean"),
            "verdict_vs_market": _field(cp, "verdict_vs_market"),
            "artifact": str(NBA_NEWSPRIOR_PATH)}


def _arm_families(key: str) -> List[str]:
    """String summaries, never a bare number -- MLB's cites arm_registry's own live
    attributes so this file can never drift from the locked constants."""
    if key == "mlb":
        return ["gap_leadoff_arm: delta_brier=%s n_eff=%s -- this IS arm_registry.py's locked "
                "incumbent bar a challenger must beat, not an arm that passed one; "
                "gap_regime_arm/gap_offset_arm/gap_blend_arm: experiment-stage, not locked"
                % (arm_registry.MEASURED_DELTA_BRIER_LOCK, arm_registry.MEASURED_EFFECTIVE_N_LOCK)]
    if key == "soccer_intl":
        # Verdict LABELS only. The supporting counts live in the source doc and are not
        # transcribed here -- this module reads artifacts, and that source is prose.
        return ["minute_window_H1_H2: RAW=INSUFFICIENT, BACKFILLED=ADVERSE-REPLICATED "
                "(WORSE_THAN_VENUE, freshness-control survived); pending human provenance "
                "decision, not executed. Counts: "
                + (str(SOCCER_ARM_DOC) if SOCCER_ARM_DOC.is_file() else UNMEASURED)]
    if key == "nba":
        return ["schedule_context/market_micro/market_coherence: manifest only "
                "(officials excluded, cache verified empty); no NBA-specific locked number"]
    return []


def _viability(cadence: Dict[str, Any]) -> str:
    """Reuses latency_scoreboard's pre-registered gates verbatim -- BOTH halves of the
    EVENT_REACTIVE conjunction (lag_p90 AND src_ts coverage), not just the lag half."""
    if cadence.get("source_verdict") != "GREEN":
        return DARK
    lag90 = cadence.get("lag_p90_sec")
    coverage = cadence.get("src_ts_coverage_pct")
    if (isinstance(lag90, (int, float)) and isinstance(coverage, (int, float))
            and lag90 <= gates.EVENT_REACTIVE_LAG_P90_SEC
            and coverage >= gates.EVENT_REACTIVE_COVERAGE_PCT):
        return EVENT_REACTIVE
    tick90 = cadence.get("tick_p90_sec")
    if isinstance(tick90, (int, float)) and tick90 <= gates.SLOW_STATE_TICK_P90_SEC:
        return SLOW_STATE
    return DARK


def _nfl_note() -> str:
    if "nfl" in kalshi_series_spec.SERIES_SPEC:
        return "kalshi series declared for nfl"
    for line in _load_text(GAP_LEDGER_CELLS_PATH).splitlines():
        if line.upper().startswith("NFL\t"):
            return line.strip()
    return "no kalshi series declared for nfl; " + str(GAP_LEDGER_CELLS_PATH) + " UNMEASURED"


def _note_for(key: str, cadence: Dict[str, Any]) -> str:
    if key == "nfl":
        return _nfl_note()
    if key == "nba":
        return ("live path excluded from inplay_tick_latency.py's SPORTS list at "
                "measurement time; see nba_calibration for the separate offline corpus")
    return "source_verdict=" + str(cadence["source_verdict"])


def _build_rows() -> List[Dict[str, Any]]:
    tick_doc = _load_json(TICK_LATENCY_PATH)
    audit_doc = _load_json(CROSSVENUE_LAG_PATH)
    verdict_doc = _load_json(NBA_NEWSPRIOR_PATH)
    rows = []
    for sport, key in _SPORT_KEYS:
        cadence = _cadence(key, tick_doc)
        rows.append({
            "sport": sport,
            "cadence": cadence,
            "crossvenue_lag": _crossvenue(key, audit_doc),
            "nba_calibration": _nba_calibration(key, verdict_doc),
            "arm_families": _arm_families(key),
            "viability": _viability(cadence),
            "note": _note_for(key, cadence),
        })
    return rows


ROWS: List[Dict[str, Any]] = _build_rows()


def by_sport(sport: str) -> Dict[str, Any]:
    """Row for *sport* (exact display name), or {} if not one of the 6 tracked sports."""
    for row in ROWS:
        if row["sport"] == sport:
            return row
    return {}


def render() -> str:
    # Sport names contain spaces, so a bare space-join is not splittable into columns;
    # pad to fixed widths instead.
    table = [["sport", "viability", "tick_p50", "tick_p90", "n_games", "n_ticks",
              "lag_p90", "crossvenue_lag_p50"]]
    for row in ROWS:
        c = row["cadence"]
        table.append([str(x) for x in [
            row["sport"], row["viability"], c["tick_p50_sec"], c["tick_p90_sec"],
            c["n_games"], c["n_ticks"], c["lag_p90_sec"],
            row["crossvenue_lag"]["median_lag_sec"]]])
    widths = [max(len(r[i]) for r in table) for i in range(len(table[0]))]
    lines = ["  ".join(cell.ljust(w) for cell, w in zip(r, widths)).rstrip() for r in table]
    lines.insert(1, "gates: EVENT_REACTIVE_LAG_P90_SEC=%s EVENT_REACTIVE_COVERAGE_PCT=%s "
                    "SLOW_STATE_TICK_P90_SEC=%s (EVENT_REACTIVE needs BOTH)"
                    % (gates.EVENT_REACTIVE_LAG_P90_SEC, gates.EVENT_REACTIVE_COVERAGE_PCT,
                       gates.SLOW_STATE_TICK_P90_SEC))
    return "\n".join(lines)


def to_json_doc() -> Dict[str, Any]:
    return {"component": "ingame_capability_matrix", "edge_claimed": False,
            "gates": {"event_reactive_lag_p90_sec": gates.EVENT_REACTIVE_LAG_P90_SEC,
                      "event_reactive_coverage_pct": gates.EVENT_REACTIVE_COVERAGE_PCT,
                      "slow_state_tick_p90_sec": gates.SLOW_STATE_TICK_P90_SEC},
            "sports": ROWS}


def write_doc(path: Optional[Path] = None) -> Path:
    p = path if path is not None else OUT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(to_json_doc(), indent=1), encoding="ascii")
    return p


def main() -> int:
    write_doc()
    print(render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
