"""scripts.platformkit.ingame.forward_evidence_scoreboard -- LANE 3 arbiter view.

WHY
---
Every live hypothesis this lane runs (the tail H1/H2 bands across 6 sports in
ingame_tail_gate.py / ingame_tail_gate_multi.py, and the enrichment gates
A/B/C in ingame_enrichment_gates*.py) is pre-registered and can only be
decided by FORWARD evidence accruing since its own pre_registered_at stamp.
Today that forward evidence is scattered across ~9 verdict JSONs under
data/domains/*/. This module is a READ-ONLY composer: it never recomputes a
Brier, a venue_gap, or any statistic -- it only reads the existing verdict
artifacts and reports, per (gate, sport), how much forward evidence has
accrued and how far that is from the pre-declared MIN_GAMES floor.

SOURCES (read-only, never recomputed)
--------------------------------------
  * data/domains/<sport>/ingame_tail_verdict.json      -- MLB's own-format
    tail gate (ingame_tail_gate.py) OR the multi-sport tail gate
    (ingame_tail_gate_multi.py) for the other 6 sports (wnba/kbo/npb/soccer/
    soccer_intl/tennis). One row per (sport, hypothesis-id) is emitted.
  * data/domains/mlb/enrichment_gate_verdict.json        -- GATE B (mlb base-out)
  * data/domains/soccer_intl/enrichment_gate_verdict.json -- GATE A (soccer xG)
  * data/domains/soccer_intl/enrichment_gate_verdict_staleq.json -- GATE C
    (cross_sport stale-quote covariate; sport recorded as "cross_sport",
    rows have no games floor -- see note in the row).

Deliberately EXCLUDED: enrichment_gate_validation*.json (soccer_intl) --
those are explicitly labeled non-forward "backfill_validation" reads on a
finished-match corpus, never pooled with a forward gate per their own
honest_note. Including them here would misrepresent them as forward evidence.

ROW SCHEMA (one row per (gate, sport)):
  gate, sport, pre_registered_at, days_accruing, forward_n,
  verdict, distance_to_decidable

*forward_n* is the gate's own forward evidence count (n_forward_games_graded
for tail gates, n_games for enrichment gates, n_rows for gate C).
*days_accruing* = now - pre_registered_at in days (negative if the stamp is
in the future -- honestly reported, not clamped to zero).
*distance_to_decidable* = games_needed_at_current_rate: forward_n/days_accruing
-> games/day rate -> ceil((MIN_GAMES_FLOOR - forward_n) / rate) days. Honest
"NEVER_AT_THIS_RATE" when rate <= 0 (no accrual yet / off-season sport) and
"DECIDABLE_NOW" when forward_n already clears the floor.

INVARIANTS: read-only (no writes to any verdict file); <=300 LOC; ASCII only;
no network; never writes data/registry/; never raises out; edge_claimed=False
always (this module states no $ figure).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_forward_evidence_scoreboard.py -q
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.eval_gate.claim_primacy import label_row

_REPO_ROOT = Path(__file__).resolve().parents[3]
DOMAINS_DIR = _REPO_ROOT / "data" / "domains"
OUT_PATH = _REPO_ROOT / "data" / "frontend" / "ops" / "forward_evidence_scoreboard.json"
COMPONENT = "forward_evidence_scoreboard"

# Sports the tail gate covers (mirrors ingame_tail_gate_multi.HYPOTHESES sports
# plus MLB's own-format gate). Read-only list -- not a source of truth, just
# where this composer looks.
TAIL_SPORTS: List[str] = ["mlb", "wnba", "kbo", "npb", "soccer", "soccer_intl", "tennis"]

# MIN_GAMES floors, read from the producing modules' own constants (duplicated
# here as plain ints since importing those modules is unnecessary for a
# read-only composer and would couple this file to their internals).
TAIL_MIN_GAMES_SPORT = 20     # ingame_tail_scan_multi.MIN_GAMES_SPORT
ENRICHMENT_MIN_GAMES = 8      # ingame_enrichment_gates.MIN_GAMES (gates A, B)

_NEVER = "NEVER_AT_THIS_RATE"
_NOW = "DECIDABLE_NOW"
_UNKNOWN = "UNKNOWN_RATE"


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- missing/corrupt file degrades to absent row
        return None


def _parse_ts(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        s2 = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:  # noqa: BLE001
        return None


def _days_accruing(pre_registered_at: Optional[str], now: datetime) -> Optional[float]:
    dt = _parse_ts(pre_registered_at)
    if dt is None:
        return None
    return (now - dt).total_seconds() / 86400.0


def distance_to_decidable(forward_n: int, days_accruing: Optional[float],
                          min_games: int) -> str:
    """Games/day rate -> days needed to clear min_games. Never recomputes a
    verdict -- purely an honest ETA on the existing forward_n count."""
    if forward_n >= min_games:
        return _NOW
    if days_accruing is None:
        return _UNKNOWN
    if days_accruing <= 0:
        # pre-registration stamp is in the future (or "now") -- no accrual window yet
        return _NEVER if forward_n == 0 else _UNKNOWN
    rate = forward_n / days_accruing
    if rate <= 0:
        return _NEVER
    days_needed = math.ceil((min_games - forward_n) / rate)
    return "%d_DAYS" % max(days_needed, 0)


def _tail_rows_for_sport(sport: str, now: datetime) -> List[Dict[str, Any]]:
    path = DOMAINS_DIR / sport / "ingame_tail_verdict.json"
    doc = _read_json(path)
    if doc is None:
        return [{
            "gate": "tail_%s" % h["id"], "sport": sport, "pre_registered_at": None,
            "days_accruing": None, "forward_n": 0, "verdict": "ABSENT",
            "distance_to_decidable": _UNKNOWN, "source": str(path),
        } for h in (
            {"id": "H1_longshot_underpriced"}, {"id": "H2_midfav_overpriced"})]
    pre_reg = doc.get("pre_registered_at") or doc.get("registered_at")
    days = _days_accruing(pre_reg, now)
    # LEAK-FREE COUNT: n_forward_games is the post-pre-registration forward
    # evidence -- the ONLY count that may drive distance_to_decidable. The
    # multi-sport gate ALSO writes n_forward_games_graded, but that field can
    # equal the DISCOVERY corpus (e.g. soccer_intl: n_forward_games=1 while
    # n_forward_games_graded=31, the 31-game pre-registration discovery set) --
    # reading graded falsely reported DECIDABLE_NOW. Prefer n_forward_games; the
    # graded fallback is purely defensive for any artifact that omits it.
    forward_n = doc.get("n_forward_games")
    if forward_n is None:
        forward_n = doc.get("n_forward_games_graded", 0)
    rows = []
    for h in doc.get("hypotheses", []) or []:
        rows.append({
            "gate": "tail_%s" % h.get("id", "?"), "sport": sport,
            "pre_registered_at": pre_reg, "days_accruing": days,
            "forward_n": forward_n, "verdict": h.get("forward_verdict", "UNKNOWN"),
            "distance_to_decidable": distance_to_decidable(
                int(forward_n or 0), days, TAIL_MIN_GAMES_SPORT),
            "source": str(path),
        })
    if not rows:
        rows.append({
            "gate": "tail_overall", "sport": sport, "pre_registered_at": pre_reg,
            "days_accruing": days, "forward_n": forward_n,
            "verdict": doc.get("verdict", "UNKNOWN"),
            "distance_to_decidable": distance_to_decidable(
                int(forward_n or 0), days, TAIL_MIN_GAMES_SPORT),
            "source": str(path),
        })
    return rows


def _enrichment_row(gate: str, sport: str, path: Path, now: datetime,
                    n_key_candidates: List[str], min_games: int) -> Dict[str, Any]:
    doc = _read_json(path)
    if doc is None:
        return {"gate": gate, "sport": sport, "pre_registered_at": None,
                "days_accruing": None, "forward_n": 0, "verdict": "ABSENT",
                "distance_to_decidable": _UNKNOWN, "source": str(path)}
    pre_reg = doc.get("pre_registered_at")
    days = _days_accruing(pre_reg, now)
    forward_n = 0
    for k in n_key_candidates:
        if doc.get(k) is not None:
            forward_n = doc.get(k)
            break
    return {
        "gate": gate, "sport": sport, "pre_registered_at": pre_reg,
        "days_accruing": days, "forward_n": forward_n,
        "verdict": doc.get("verdict", "UNKNOWN"),
        "distance_to_decidable": distance_to_decidable(int(forward_n or 0), days,
                                                        min_games),
        "source": str(path),
    }


def build_scoreboard(now: Optional[datetime] = None) -> Dict[str, Any]:
    """Compose the scoreboard from existing verdict artifacts only. Never
    raises -- a missing/corrupt source file degrades that row to ABSENT
    rather than killing the whole scoreboard."""
    now = now or datetime.now(timezone.utc)
    rows: List[Dict[str, Any]] = []
    try:
        for sport in TAIL_SPORTS:
            rows.extend(_tail_rows_for_sport(sport, now))
    except Exception:  # noqa: BLE001
        pass
    try:
        rows.append(_enrichment_row(
            "enrichment_A_soccer_xg", "soccer_intl",
            DOMAINS_DIR / "soccer_intl" / "enrichment_gate_verdict.json", now,
            ["n_games"], ENRICHMENT_MIN_GAMES))
        rows.append(_enrichment_row(
            "enrichment_B_mlb_baseout", "mlb",
            DOMAINS_DIR / "mlb" / "enrichment_gate_verdict.json", now,
            ["n_games"], ENRICHMENT_MIN_GAMES))
        rows.append(_enrichment_row(
            "enrichment_C_stale_quote_covariate", "cross_sport",
            DOMAINS_DIR / "soccer_intl" / "enrichment_gate_verdict_staleq.json", now,
            ["n_rows"], ENRICHMENT_MIN_GAMES))
    except Exception:  # noqa: BLE001
        pass
    rows = [label_row(row) for row in rows]
    n_decidable_now = sum(1 for r in rows if r["distance_to_decidable"] == _NOW)
    n_never = sum(1 for r in rows if r["distance_to_decidable"] == _NEVER)
    return {
        "component": COMPONENT,
        "generated_at": now.isoformat(),
        "rows": rows,
        "n_rows": len(rows),
        "n_decidable_now": n_decidable_now,
        "n_never_at_current_rate": n_never,
        "honest_note": ("Composed read-only from existing pre-registered verdict "
                        "artifacts (ingame_tail_verdict.json per sport, "
                        "enrichment_gate_verdict*.json) -- never recomputes a Brier, "
                        "venue_gap, or verdict. distance_to_decidable is an honest "
                        "ETA from the CURRENT forward-accrual rate to the pre-declared "
                        "MIN_GAMES floor; NEVER_AT_THIS_RATE means zero forward games "
                        "have accrued (e.g. an off-season sport) -- not a rejection. "
                        "No $ edge claimed; this file states no ROI/PnL figure."),
        "edge_claimed": False,
    }


def write_doc(doc: Dict[str, Any], path: Optional[Path] = None) -> None:
    p = Path(path) if path is not None else OUT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1, default=str), encoding="ascii")
    tmp.replace(p)


def render(doc: Dict[str, Any]) -> str:
    L = ["=" * 112, "FORWARD-EVIDENCE SCOREBOARD -- the honest 'what can we conclude yet' view"]
    L.append("%-32s %-12s %-18s %10s %8s %-16s %-14s" %
             ("GATE", "SPORT", "PRE_REGISTERED", "DAYS_ACC", "FWD_N", "VERDICT", "CLAIM_LABEL"))
    L.append("-" * 112)
    for r in doc.get("rows", []):
        days = r.get("days_accruing")
        days_s = ("%.1f" % days) if isinstance(days, (int, float)) else "n/a"
        L.append("%-32s %-12s %-18s %10s %8s %-16s %-14s -> %s" % (
            r.get("gate"), r.get("sport"),
            (r.get("pre_registered_at") or "n/a")[:18],
            days_s, r.get("forward_n"), r.get("verdict"), r.get("claim_label"),
            r.get("distance_to_decidable")))
    L.append("=" * 112)
    L.append("rows=%d decidable_now=%d never_at_current_rate=%d" % (
        doc.get("n_rows", 0), doc.get("n_decidable_now", 0),
        doc.get("n_never_at_current_rate", 0)))
    L.append("edge_claimed=False. Read-only composition, no stat recomputed here.")
    L.append("=" * 112)
    return "\n".join(L)


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="forward_evidence_scoreboard")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    doc = build_scoreboard()
    if not a.no_write:
        write_doc(doc)
    print(render(doc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "OUT_PATH", "COMPONENT", "TAIL_SPORTS", "TAIL_MIN_GAMES_SPORT",
    "ENRICHMENT_MIN_GAMES", "distance_to_decidable", "build_scoreboard",
    "write_doc", "render",
]
