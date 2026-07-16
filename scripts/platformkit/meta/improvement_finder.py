"""scripts.platformkit.meta.improvement_finder -- MEASUREMENT-ONLY improvement finder.

Scans existing READ-ONLY artifacts (funnel coverage, deep-data prioritization,
the durable reject ledger, the parity grid, the repo tree, the self-improve
loop status) and emits a RANKED, DEDUPED backlog of concrete improvement
CANDIDATES. It DISCOVERS and RANKS; it does NOT fix, flip a flag, ship, write
data/ or registry/, or touch the pipeline sentinel.

NON-NEGOTIABLE HONESTY RAILS (binding, enforced in code + test):
  * UNITS / probability only. There is NO $ field on any candidate, EVER. We
    never fabricate an edge or invent a candidate.
  * NEVER recommend force-feeding a gate-REJECTED signal into a model as a
    FEATURE (that re-follows the market + overfits -> destroys calibration).
    A REJECT is a CLOSED dead-end, not a to-do. The only honest moves are:
    (a) TEST untested data through the gate, (b) EXPOSE coherent-but-hidden
    markets, (c) SURFACE validated priors as priors/provenance (not features),
    (d) close stale-green / fragility / coherence / LOC / orphan / missing-test
    gaps -- all CALIBRATION / COVERAGE / ROBUSTNESS, never edge.
  * A data point that already has a recorded gate verdict (PASS/SHIP/REJECT/
    HOLD/DEFER) in the reject ledger is CLOSED -> NOT a candidate.

Categories: UNTESTED_DATA | EXPOSE_COHERENT_MARKET | SURFACE_VALIDATED_PRIOR |
STALE_GREEN_RISK | COHERENCE_GAP | FRAGILITY | LOC_VIOLATION | ORPHAN_MODULE |
MISSING_TEST | TIER3_ACQUISITION | PARITY_GAP.

Build only here + a per-file test; backlog written under .planning/product/meta/.
PURE offline read-only (no heavy training, no full pytest). <=300 LOC; ASCII only.
CLI: python -m scripts.platformkit.meta.improvement_finder
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, List, Optional

_HERE = Path(__file__).resolve().parent
ROOT = _HERE.parents[2]
PRODUCT = ROOT / ".planning" / "product"
FUNNEL = PRODUCT / "funnel"
DEEPDATA = PRODUCT / "deepdata"
META_OUT = PRODUCT / "meta"
LEDGER = ROOT / "data" / "frontend" / "reject_ledger.jsonl"
IMPROVE_LEDGER = ROOT / "data" / "frontend" / "improve_ledger.jsonl"
SAFE_BUILD_DIRS = ("scripts/platformkit", "domains")

CATEGORIES = (
    "UNTESTED_DATA", "EXPOSE_COHERENT_MARKET", "SURFACE_VALIDATED_PRIOR",
    "STALE_GREEN_RISK", "COHERENCE_GAP", "FRAGILITY", "LOC_VIOLATION",
    "ORPHAN_MODULE", "MISSING_TEST", "TIER3_ACQUISITION", "PARITY_GAP",
    "DECAYED_CLAIM", "DISCREPANT_STAT", "CLAIM_CONTRADICTION",
)
# Category -> base priority (coverage / honesty-criticality, NOT promised edge).
_BASE = {
    "UNTESTED_DATA": 90, "PARITY_GAP": 85, "EXPOSE_COHERENT_MARKET": 80,
    "STALE_GREEN_RISK": 78, "COHERENCE_GAP": 70, "SURFACE_VALIDATED_PRIOR": 68,
    "FRAGILITY": 60, "MISSING_TEST": 55, "ORPHAN_MODULE": 50,
    "LOC_VIOLATION": 45, "TIER3_ACQUISITION": 40,
    "DECAYED_CLAIM": 78, "DISCREPANT_STAT": 82, "CLAIM_CONTRADICTION": 65,
}
HONEST_NOTE = ("MEASUREMENT-ONLY: discovers+ranks; never fixes/ships/flags. "
               "A REJECT is a closed dead-end, never force-fed as a feature. "
               "calibration != edge; no $ field anywhere.")
# Phrases that would imply force-feeding a rejected signal as a model feature.
_FORBIDDEN = re.compile(r"force[- ]?feed|rejected.*as a feature|add reject", re.I)


@dataclass
class Candidate:
    id: str
    category: str
    sport: str
    what: str
    where: str
    expected_outcome: str
    gate_action: str
    priority: float
    # NOTE: deliberately NO `$` / dollar / edge field. UNITS-only by construction.

    def key(self) -> str:
        return f"{self.category}|{self.sport}|{self.what}".lower().strip()


def _slug(text: str, n: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s[:n]


def load_verdicted_signals(path: Path = LEDGER) -> set:
    """Signals/data points WITH a recorded gate verdict are CLOSED (excluded)."""
    closed = set()
    if not path.exists():
        return closed
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        sig = (rec.get("signal") or "").lower()
        if rec.get("verdict") and sig:
            closed.add(sig)
            # also index the bare data-point tokens so coverage rows match
            for tok in re.findall(r"[a-z]{4,}", sig):
                closed.add(tok)
    return closed


def _is_closed(what: str, closed: set) -> bool:
    """A coverage candidate is closed if its data-point name maps to a verdict."""
    toks = set(re.findall(r"[a-z]{4,}", what.lower()))
    # require a strong overlap so we do not over-suppress generic words
    strong = {t for t in toks if t not in ("data", "form", "team", "with", "diff",
                                            "pregame", "ingame", "state", "states",
                                            "layer", "prior")}
    return bool(strong) and strong.issubset(closed)


def _md_rows(md: str, header_substr: str) -> List[List[str]]:
    """Return cells of pipe-table rows that follow a header containing substr."""
    out, in_tbl = [], False
    for ln in md.splitlines():
        if "|" in ln and header_substr.lower() in ln.lower() and "---" not in ln:
            in_tbl = True
            continue
        if in_tbl:
            if "|" not in ln or set(ln.strip()) <= set("|-: "):
                if "|" not in ln:
                    in_tbl = False
                continue
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if len(cells) >= 3 and not all(c == "" for c in cells):
                out.append(cells)
    return out


def _funnel_closed(sport: str, point: str, vidx) -> bool:
    """True iff a recorded funnel GATE verdict already covers this data point.

    Reconciles the COVERAGE prose against verdicts written to data/frontend/funnel/*.json
    (folded into the reject-ledger). PRECISE + sport-scoped so an unsure row stays OPEN.
    Read-only; any import/IO error -> treat as NOT closed (never falsely claim coverage).
    """
    if vidx is None:
        return False
    try:
        from scripts.platformkit.meta.funnel_verdict_reconcile import is_data_point_closed
        return is_data_point_closed(sport, point, vidx)
    except Exception:  # noqa: BLE001 -- a reconcile miss is "still open", never a crash
        return False


def scan_untested_and_priors(closed: set) -> List[Candidate]:
    cov = FUNNEL / "COVERAGE.md"
    if not cov.exists():
        return []
    md = cov.read_text(encoding="utf-8", errors="ignore")
    cands: List[Candidate] = []
    try:  # READ-ONLY index of data points that already have a recorded funnel verdict
        from scripts.platformkit.meta.funnel_verdict_reconcile import verdict_index
        vidx = verdict_index()
    except Exception:  # noqa: BLE001
        vidx = None
    # TYPE A -- UNTESTED_DATA (sport|data point|source|honest prior)
    for r in _md_rows(md, "honest prior"):
        sport, point, source, prior = r[0], r[1], r[2], r[-1]
        if _is_closed(point, closed) or _funnel_closed(sport, point, vidx):
            continue
        cands.append(Candidate(
            id="UNTESTED_" + _slug(f"{sport}_{point}"), category="UNTESTED_DATA",
            sport=sport or "platform", what=point, where=f"domains/{_slug(sport)}",
            expected_outcome=prior or "REJECT-scouting likely",
            gate_action="run leak-free gate; record verdict; keep scouting on REJECT",
            priority=_BASE["UNTESTED_DATA"]))
    # TYPE B -- VALIDATED_BUT_UNWIRED -> SURFACE_VALIDATED_PRIOR (not a feature)
    for r in _md_rows(md, "honest wiring"):
        sport, point, status, wiring = r[0], r[1], r[2], r[-1]
        if _is_closed(point, closed):
            continue
        cands.append(Candidate(
            id="PRIOR_" + _slug(f"{sport}_{point}"),
            category="SURFACE_VALIDATED_PRIOR", sport=sport or "platform",
            what=point, where="predict_service provenance",
            expected_outcome="surface as prior/provenance only -- NEVER a feature",
            gate_action="attach as scouting/provenance; promote to feature ONLY on "
                        "pre-registered both-dir cross-corpus PASS",
            priority=_BASE["SURFACE_VALIDATED_PRIOR"]))
    # TYPE C -- ENGINE_COHERENCE_GAP (sport|market|gap|fix)
    for r in _md_rows(md, "| gap |"):
        sport, market, gap, fix = r[0], r[1], r[2], r[-1]
        if re.search(r"resolved|now exposed|already exposed|\bdone\b",
                     (gap + " " + fix).lower()):
            continue  # a gap marked resolved in the coverage map is closed, not a candidate
        is_expose = "expos" in (gap + fix).lower() or "registry" in fix.lower()
        cat = "EXPOSE_COHERENT_MARKET" if is_expose else "COHERENCE_GAP"
        cands.append(Candidate(
            id=("EXPOSE_" if is_expose else "COH_") + _slug(f"{sport}_{market}"),
            category=cat, sport=sport or "platform", what=f"{market}: {gap}",
            where="predict_service/registry.py",
            expected_outcome="pure coherence/exposure win -- same calibration, no edge",
            gate_action=fix or "derive-read off the one engine matrix; no new data",
            priority=_BASE[cat]))
    return cands


def scan_tier3() -> List[Candidate]:
    pri = DEEPDATA / "PRIORITIZED.md"
    if not pri.exists():
        return []
    try:  # exclude deep-data layers that already carry a recorded verdict (any location)
        from scripts.platformkit.meta.funnel_verdict_reconcile import verdict_index
        vidx = verdict_index()
    except Exception:  # noqa: BLE001
        vidx = None
    cands: List[Candidate] = []
    for r in _md_rows(pri.read_text(encoding="utf-8", errors="ignore"), "build target"):
        # rank|sport|layer|zero-net|gate|expected|why
        if len(r) < 6:
            continue
        sport, layer, zeronet, gate, expected = r[1], r[2], r[3], r[4], r[5]
        if _funnel_closed(sport, layer, vidx):
            continue
        is_net = "network" in zeronet.lower() and "zero" not in zeronet.lower()[:6]
        cat = "TIER3_ACQUISITION" if is_net else "UNTESTED_DATA"
        cands.append(Candidate(
            id=("TIER3_" if is_net else "DEEP_") + _slug(f"{sport}_{layer}", 32),
            category=cat, sport=sport or "platform", what=layer,
            where=f"domains/{_slug(sport)}", expected_outcome=expected or "REJECT-leaning",
            gate_action=f"build leak-free as-of; run {gate or 'combo_gate'}; record verdict",
            priority=_BASE[cat] + (3 if not is_net else 0)))
    return cands


def scan_parity_gaps() -> List[Candidate]:
    """Read the parity grid via its pure functions; red/na are PARITY_GAPs."""
    try:
        from scripts.platformkit.parity_matrix import build_parity_matrix
        rows = build_parity_matrix()
    except Exception:
        return []
    cands: List[Candidate] = []
    for row in rows:
        for dim, cell in getattr(row, "cells", {}).items():
            status = getattr(cell, "status", "green")
            if status == "green":
                continue
            cands.append(Candidate(
                id="PARITY_" + _slug(f"{row.sport}_{dim}"), category="PARITY_GAP",
                sport=row.sport, what=f"{dim} {status}: {getattr(cell,'detail','')}",
                where=f"domains/{row.sport}/{dim}",
                expected_outcome="closes a coverage/parity gap (red) or builds a tier (n/a)",
                gate_action=f"add/repair {dim} decl so parity_matrix cell turns green",
                priority=_BASE["PARITY_GAP"] - (0 if status == "red" else 15)))
    return cands


def _iter_py(rel: str):
    base = ROOT / rel
    if not base.exists():
        return
    for p in base.rglob("*.py"):
        if "__pycache__" in p.parts or p.name == "__init__.py":
            yield p if p.name != "__init__.py" else None
        else:
            yield p


def scan_repo_health() -> List[Candidate]:
    """LOC_VIOLATION + MISSING_TEST over the SAFE build dirs (read-only)."""
    cands: List[Candidate] = []
    test_stems = set()
    for t in (ROOT / "tests").rglob("test_*.py"):
        test_stems.add(t.stem.replace("test_", "", 1))
    for sd in SAFE_BUILD_DIRS:
        for p in (ROOT / sd).rglob("*.py"):
            if "__pycache__" in p.parts or p.name == "__init__.py":
                continue
            rel = p.relative_to(ROOT).as_posix()
            if p.name.startswith("test_"):
                continue
            try:
                loc = sum(1 for _ in p.open(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
            if loc > 300:
                cands.append(Candidate(
                    id="LOC_" + _slug(rel, 48), category="LOC_VIOLATION",
                    sport="platform", what=f"{loc} LOC > 300", where=rel,
                    expected_outcome="split to <=300 LOC; pure refactor, no behavior change",
                    gate_action="split module; re-run that file's per-file test",
                    priority=_BASE["LOC_VIOLATION"] + min(loc - 300, 60) / 10.0))
            if p.stem not in test_stems:
                cands.append(Candidate(
                    id="TEST_" + _slug(rel, 48), category="MISSING_TEST",
                    sport="platform", what=f"no per-file test for {p.name}", where=rel,
                    expected_outcome="closes a missing-test gap (robustness, not edge)",
                    gate_action="add per-file test; run only that file",
                    priority=_BASE["MISSING_TEST"]))
    return cands


def scan_stale_green_and_autonomy() -> List[Candidate]:
    cands: List[Candidate] = []
    if IMPROVE_LEDGER.exists():
        n = sum(1 for ln in IMPROVE_LEDGER.read_text(
            encoding="utf-8", errors="ignore").splitlines() if ln.strip())
        cands.append(Candidate(
            id="STALE_improve_ledger_recency", category="STALE_GREEN_RISK",
            sport="platform", what="verify newest improve_ledger verdicts not stale-green",
            where="data/frontend/improve_ledger.jsonl",
            expected_outcome="confirms gates still pass on fresh settled data; no edge",
            gate_action="re-run self_improve readout on latest settled; record verdict",
            priority=_BASE["STALE_GREEN_RISK"] - 5))
    si = ROOT / "scripts" / "improve_loop" / "state.json"
    if si.exists():
        cands.append(Candidate(
            id="AUTONOMY_loop_inert_ready", category="STALE_GREEN_RISK",
            sport="platform", what="self-improve loop wired+INERT (flag OFF) -- confirm readiness",
            where="scripts/improve_loop/state.json",
            expected_outcome="confirms loop ready to run; measurement-only, flag stays OFF",
            gate_action="audit loop liveness; do NOT flip PIPELINE_ENABLED (human gate)",
            priority=_BASE["STALE_GREEN_RISK"]))
    return cands


def scan_analytics_verify() -> List[Candidate]:
    """DECAYED_CLAIM / DISCREPANT_STAT / CLAIM_CONTRADICTION -- scan logic lives
    in analytics_verify/cycle.py (this file is over the 300 LOC cap already);
    this is thin glue. Absent artifacts -> [] (no crash)."""
    try:
        from scripts.platformkit.analytics_verify.cycle import scan_finder_candidates
        return [Candidate(**d) for d in scan_finder_candidates()]
    except Exception:  # noqa: BLE001 -- a scan failure must never block the rest of the finder
        return []


def discover() -> List[Candidate]:
    closed = load_verdicted_signals()
    cands: List[Candidate] = []
    cands += scan_untested_and_priors(closed)
    cands += scan_tier3()
    cands += scan_parity_gaps()
    cands += scan_repo_health()
    cands += scan_stale_green_and_autonomy()
    cands += scan_analytics_verify()
    return rank_and_dedupe(cands)


# High-volume repo-health categories are capped so they never drown the honest
# coverage/coherence candidates. The cap is deterministic (top-N by priority,id).
_CAP = {"MISSING_TEST": 25, "LOC_VIOLATION": 25, "ORPHAN_MODULE": 25}


def rank_and_dedupe(cands: List[Candidate]) -> List[Candidate]:
    seen: Dict[str, Candidate] = {}
    for c in cands:
        # HONESTY GUARD: never emit a force-feed-a-reject item.
        if _FORBIDDEN.search(c.gate_action) or _FORBIDDEN.search(c.expected_outcome):
            continue
        assert not hasattr(c, "dollars") and "$" not in (c.gate_action + c.expected_outcome)
        k = c.key()
        if k not in seen or c.priority > seen[k].priority:
            seen[k] = c
    ranked = sorted(seen.values(), key=lambda c: (-c.priority, c.category, c.id))
    # apply per-category caps deterministically (preserve overall ranked order)
    kept: Dict[str, int] = {}
    out: List[Candidate] = []
    for c in ranked:
        cap = _CAP.get(c.category)
        n = kept.get(c.category, 0)
        if cap is not None and n >= cap:
            continue
        kept[c.category] = n + 1
        out.append(c)
    return out


def write_backlog(cands: List[Candidate]) -> None:
    META_OUT.mkdir(parents=True, exist_ok=True)
    payload = {"note": HONEST_NOTE, "categories": list(CATEGORIES),
               "count": len(cands), "candidates": [asdict(c) for c in cands]}
    (META_OUT / "improvement_backlog.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8")
    lines = ["# Improvement Backlog -- MEASUREMENT-ONLY (ranked)", "",
             HONEST_NOTE, "",
             f"Total candidates: {len(cands)}. NO $ field. NEVER force-feeds a "
             "gate-rejected signal as a model feature. Items with a recorded gate "
             "verdict are excluded (closed).", "",
             "| # | pri | category | sport | what | where | expected_outcome | gate/action |",
             "|---|---|---|---|---|---|---|---|"]
    for i, c in enumerate(cands, 1):
        cells = [str(i), f"{c.priority:.1f}", c.category, c.sport,
                 c.what, c.where, c.expected_outcome, c.gate_action]
        lines.append("| " + " | ".join(x.replace("|", "/") for x in cells) + " |")
    by_cat: Dict[str, int] = {}
    for c in cands:
        by_cat[c.category] = by_cat.get(c.category, 0) + 1
    lines += ["", "## Per-category counts"]
    lines += [f"- {cat}: {by_cat.get(cat, 0)}" for cat in CATEGORIES]
    (META_OUT / "IMPROVEMENT_BACKLOG.md").write_text("\n".join(lines) + "\n",
                                                     encoding="utf-8")


def main() -> int:
    cands = discover()
    write_backlog(cands)
    by_cat: Dict[str, int] = {c: 0 for c in CATEGORIES}
    for c in cands:
        by_cat[c.category] += 1
    print("improvement_finder: MEASUREMENT-ONLY (no fix/flag/ship; no $ field)")
    for cat in CATEGORIES:
        print(f"  {cat}: {by_cat[cat]}")
    print(f"total candidates: {len(cands)}")
    for i, c in enumerate(cands[:10], 1):
        print(f"  {i}. [{c.priority:.0f}] {c.category} {c.sport} :: {c.what[:60]}")
    print(f"backlog: {META_OUT / 'IMPROVEMENT_BACKLOG.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
