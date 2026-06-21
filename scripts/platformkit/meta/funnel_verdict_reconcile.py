"""scripts.platformkit.meta.funnel_verdict_reconcile -- fold recorded funnel GATE
verdicts into the reject-ledger graveyard + expose a precise per-sport CLOSED index.

THE GAP THIS CLOSES: the leak-free gate writes a verdict per data layer to
``data/frontend/funnel/<sport>_<layer>_gate.json`` (carrying ``layer`` + ``verdict``),
but those verdicts were never folded into ``reject_ledger.jsonl``. So the
improvement_finder -- which reads ONLY the ledger -- could not see them and re-listed
already-tested data layers (nba_travel, mlb_atbat, ...) as UNTESTED. The backlog then
over-reported remaining work, making a near-complete funnel look unfinished.

This module:
  * fold_into_ledger() -- idempotently records each recorded funnel verdict in the
    canonical reject_ledger (source 'funnel_gate'); the single source of truth.
  * verdict_index()    -- sport -> set of distinctive (>=5-char) data-point slugs that
    HAVE a recorded verdict (READ-ONLY).
  * is_data_point_closed(sport, what) -- True iff a COVERAGE data-point prose row names a
    layer that already has a verdict (sport-scoped substring match -> PRECISE, never a
    fuzzy over-suppress; an unsure row stays OPEN, the honest error direction).

MEASUREMENT-ONLY: reads recorded verdicts; runs NO gate; flips NO flag; writes ONLY the
existing frontend ledger (never data/registry/); NO $ field. ASCII only; <=300 LOC.
CLI: python -m scripts.platformkit.meta.funnel_verdict_reconcile [--fold]
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from scripts.platformkit import reject_ledger as rl

_HERE = Path(__file__).resolve().parent
ROOT = _HERE.parents[2]
FUNNEL = ROOT / "data" / "frontend" / "funnel"

# Verdict strings that count as a recorded gate DECISION (the data point is closed).
_VERDICTS = {"REJECT", "SHIP", "PASS", "HOLD", "DEFER", "TIER3_BLOCKED",
             "PARTIAL", "SURVIVOR", "CONFIRMED_SURVIVOR", "SURVIVOR_HELD"}
# Sport prefixes a layer slug can carry (longest first so basketball_nba wins over nba).
_SPORT_PREFIXES = ("basketball_nba", "soccer_intl", "nba", "mlb", "soccer", "tennis")
# Curated aliases: layer slug -> extra normalized keywords that identify it in COVERAGE
# prose when the prose joins/abbreviates words differently than the slug (e.g. red card).
_ALIASES: Dict[str, Set[str]] = {
    "soccer_redcard": {"reddiff", "manadvantage", "redcard"},
}
# Recorded gate verdicts that live OUTSIDE data/frontend/funnel/ with sport-less
# filenames -- mapped EXPLICITLY (path-parts relative to data/frontend -> canonical slug)
# so the sport + data-point identity is exact, never inferred from a messy name.
_EXTRA_SOURCES: Dict[Tuple[str, ...], str] = {
    ("defender_matchup_gate.json",): "nba_defender_matchup",
    ("ingame", "pitch_layer_gate_mlb.json"): "mlb_pitch_states",
}
# Cadence re-check spam + non-gate artifacts to skip.
_SKIP_SUBSTR = ("survivor", "ci_", "parity", "coherence")
# Structural filename suffix tokens stripped to recover the clean data-point slug
# (the FILENAME is clean -- e.g. mlb_atbat_ingame_gate -> mlb_atbat -- where the in-body
# `layer` field sometimes carries messy descriptive prose).
_STRUCT_SUFFIX = {"gate", "ingame", "edge", "winprob", "asof", "states", "state",
                  "layer", "run", "real", "event", "xg", "prop", "kprop"}


def _norm(s: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _norm_sport(s: object) -> str:
    v = str(s or "").strip().lower()
    if "basketball" in v:
        return "nba"
    return v


def _sport_of(slug: str) -> str:
    for p in _SPORT_PREFIXES:
        if slug == p or slug.startswith(p + "_"):
            return _norm_sport(p)
    return slug.split("_", 1)[0]


def _slug_from_filename(stem: str) -> str:
    """Clean data-point slug from a gate filename: strip structural suffix tokens but
    always keep the sport prefix + >=1 distinctive token (e.g. mlb_atbat_ingame_gate ->
    mlb_atbat, soccer_espn28_gate -> soccer_espn28)."""
    toks = stem.lower().split("_")
    while len(toks) > 2 and toks[-1] in _STRUCT_SUFFIX:
        toks.pop()
    return "_".join(toks)


def iter_funnel_verdicts() -> List[Tuple[str, str, dict]]:
    """Return (slug, verdict, raw) for each recorded gate-verdict file (slug from the
    clean FILENAME, not the in-body `layer` which can carry descriptive prose)."""
    out: List[Tuple[str, str, dict]] = []
    if not FUNNEL.is_dir():
        return out
    for p in sorted(FUNNEL.glob("*.json")):
        b = p.name.lower()
        if any(s in b for s in _SKIP_SUBSTR):
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(d, dict):
            continue
        verdict = str(d.get("verdict") or d.get("decision") or
                      d.get("gate_verdict") or "").strip().upper()
        if verdict not in _VERDICTS:
            continue
        out.append((_slug_from_filename(p.stem), verdict, d))
    # EXPLICITLY-mapped verdict files outside funnel/ (sport-less filenames). Resolved
    # relative to data/frontend (FUNNEL.parent) so tests pointing FUNNEL at a tmp dir stay
    # isolated (the real extra paths simply do not exist under the tmp parent).
    for parts, slug in _EXTRA_SOURCES.items():
        p = FUNNEL.parent.joinpath(*parts)
        try:
            d = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(d, dict):
            continue
        verdict = str(d.get("verdict") or d.get("decision") or
                      d.get("gate_verdict") or "").strip().upper()
        if verdict in _VERDICTS:
            out.append((slug, verdict, d))
    return out


def fold_into_ledger(ledger_path: Optional[Path] = None) -> int:
    """Idempotently record each recorded funnel verdict in the reject-ledger.

    Keyed on (sport, signal) within source='funnel_gate' so re-runs never duplicate.
    Returns the number of NEW rows written.
    """
    have = {(rl._norm(r.get("sport")), str(r.get("signal", "")).strip())
            for r in rl.load(source="funnel_gate", ledger_path=ledger_path)}
    n = 0
    for slug, verdict, d in iter_funnel_verdicts():
        sport = _sport_of(slug)
        key = (rl._norm(sport), slug)
        if key in have:
            continue
        rl.record(
            sport, slug, verdict, str(d.get("vs_close") or "")[:200],
            source="funnel_gate",
            metrics={"n_corpora": d.get("n_corpora"),
                     "null_rejects": d.get("null_rejects"),
                     "proposal_only": d.get("proposal_only")},
            ledger_path=ledger_path,
        )
        have.add(key)
        n += 1
    return n


def _add_slug(idx: Dict[str, Set[str]], sport: str, sig: str) -> None:
    sport = _norm_sport(sport)
    sig = str(sig or "").strip().lower()
    if not sport or not sig:
        return
    dp = sig[len(sport) + 1:] if sig.startswith(sport + "_") else sig
    forms = {_norm(dp)} | {_norm(a) for a in _ALIASES.get(sig, set())}
    keep = {f for f in forms if len(f) >= 5}
    if keep:
        idx.setdefault(sport, set()).update(keep)


def verdict_index(ledger_path: Optional[Path] = None) -> Dict[str, Set[str]]:
    """sport -> set of distinctive (>=5-char) data-point slugs WITH a recorded verdict.

    Reads BOTH the reject-ledger (durable, folded verdicts) AND the live funnel verdict
    files directly (READ-ONLY) so the index is correct even if fold_into_ledger has not
    been run this cycle -- the finder never depends on a prior write.
    """
    idx: Dict[str, Set[str]] = {}
    for r in rl.load(ledger_path=ledger_path):
        _add_slug(idx, r.get("sport"), r.get("signal", ""))
    for slug, _verdict, _raw in iter_funnel_verdicts():  # live, read-only
        _add_slug(idx, _sport_of(slug), slug)
    return idx


def is_data_point_closed(sport: object, what: object,
                         idx: Optional[Dict[str, Set[str]]] = None) -> bool:
    """True iff a COVERAGE data-point row names a layer that already has a verdict.

    Sport-scoped substring match: PRECISE (a >=5-char distinctive slug must appear in the
    normalized prose) so generic words never over-close; an unsure row stays OPEN.
    """
    index = idx if idx is not None else verdict_index()
    nw = _norm(what)
    if not nw:
        return False
    for slug in index.get(_norm_sport(sport), ()):  # type: ignore[arg-type]
        if slug and slug in nw:
            return True
    return False


def main(argv: Optional[List[str]] = None) -> int:
    import sys
    args = list(argv) if argv is not None else sys.argv[1:]
    verdicts = iter_funnel_verdicts()
    print(f"funnel_verdict_reconcile: {len(verdicts)} recorded gate verdicts on disk")
    for layer, verdict, _ in verdicts:
        print(f"  {verdict:<18} {layer}")
    if "--fold" in args:
        n = fold_into_ledger()
        print(f"folded {n} NEW verdict row(s) into the reject-ledger (source funnel_gate)")
    idx = verdict_index()
    print("closed data-point slugs per sport:")
    for sport in sorted(idx):
        print(f"  {sport}: {sorted(idx[sport])[:12]}")
    return 0


__all__ = ["iter_funnel_verdicts", "fold_into_ledger", "verdict_index",
           "is_data_point_closed", "FUNNEL"]


if __name__ == "__main__":
    raise SystemExit(main())
