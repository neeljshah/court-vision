"""scripts.platformkit.autoloop.propose_gate_job -- zero-LLM SELF-PROPOSAL
cycle (autoloop job #10 / M10). Per cycle: PROPOSE up to K novel interaction-
factory candidates (round-robin across sports, via the EXISTING generator +
knowledge_intake -- never a new grammar), refuse every already-tested
hypothesis identity and every CLOSED class, then run each survivor through
runner.run_batch's REAL leak-free gate, which appends the honest verdict rows
(SURVIVES_PREREG_PROVISIONAL / NULL / NOT_TESTABLE, hypothesis_source =
'blind' or 'knowledge') to the cumulative-K ledger itself.

DEDUP (never re-test, never re-open):
 * ledger identity -- (template_id, unordered attr pair, entity_class) across
   every prior TERMINAL ledger row (NOT_TESTABLE excluded -- see generator.
   tested_ids's own exclusion; a builder/data-unavailable candidate re-enters
   once its builder lands), so a pair tested under a '::src=knowledge' id is
   never re-proposed blind (candidate_id-only dedup would miss that).
 * closed classes -- (a) reject-ledger REJECT signals: a candidate naming a
   REJECTed signal as either attr for that sport is refused; (b) NULL_LOCAL
   mechanism families (latest verdict per hypothesis in domains/*/knowledge/
   validation_ledger.jsonl) are refused via their declared KNOWN_MAPPINGS
   (template, pair) identities. Generator's own GLOBAL_BLOCKLIST still applies
   upstream inside enumerate_candidates.

BUDGETS: M07 self-caps via corpus-mtime watermark gating; proposal has no
corpus watermark, so M10's analog is an explicit per-cycle WALL-CLOCK cap
checked before each template group's gate run (deferred groups are reported,
never silently dropped) -- autoloop must never starve its sibling jobs.
DRY-CYCLE counter: a template pool producing ONLY NOT_TESTABLE rows for 3
consecutive cycles is logged EXHAUSTED (human-queue row) and rotated out of
future draws; the next template in that sport takes over automatically.

INVARIANTS: ledger/queue append only (the gate's own append path, byte-
identical to a manual run_batch); no promotion, no flag flip, no
data/registry/ write, no edge claim. State lives in the runner's watermarks
dict under STATE_KEY (same convention as M02/M07/M08).

Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autoloop/test_propose_gate_job.py -q
"""
from __future__ import annotations

import json
import time as _time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from scripts.platformkit.interaction_factory import generator as GEN
from scripts.platformkit.interaction_factory import knowledge_intake as KI

_REPO = Path(__file__).resolve().parents[3]
REJECT_LEDGER_PATH = _REPO / "data" / "frontend" / "reject_ledger.jsonl"

STATE_KEY = "M10_propose_gate"
DEFAULT_K = 8
DEFAULT_WALL_CLOCK_CAP_SEC = 300.0
DRY_CYCLES_TO_EXHAUST = 3
# reject-ledger verdicts that CLOSE a class (declared; DEFER/SHIP_REVIEW etc do not)
CLOSED_VERDICTS = frozenset({"REJECT"})
# reject ledger says "nba"; the factory grammar says "basketball_nba"
_SPORT_ALIAS = {"nba": "basketball_nba"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _identity(template_id: str, attr_a: str, attr_b: str,
              entity_class: Optional[str] = None) -> str:
    """Hypothesis identity key: template + UNORDERED attr pair + class scope.
    Source-suffix-free, so blind and '::src=knowledge' ids collide on purpose."""
    pair = "__x__".join(sorted([str(attr_a), str(attr_b)]))
    tail = "::class=%s" % entity_class if entity_class else ""
    return "%s::%s%s" % (template_id, pair, tail)


def _row_identity(row: Dict[str, Any]) -> str:
    cid = str(row.get("candidate_id") or "")
    cls = cid.split("::class=", 1)[1] if "::class=" in cid else None
    return _identity(str(row.get("template_id")), str(row.get("attr_a")),
                     str(row.get("attr_b")), cls)


def _reject_closed_attrs(path: Optional[Path]) -> Set[Tuple[str, str]]:
    """(factory_sport, signal) pairs whose reject-ledger verdict closes the
    class. Exact-match on the signal name -- fuzzy matching would over-block."""
    p = path or REJECT_LEDGER_PATH
    out: Set[Tuple[str, str]] = set()
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("verdict")) in CLOSED_VERDICTS:
            sport = str(row.get("sport") or "")
            out.add((_SPORT_ALIAS.get(sport, sport), str(row.get("signal") or "")))
    return out


def _null_local_identities(ledger_paths: Optional[Dict[str, Path]],
                           mappings: Optional[Dict[str, List[Dict[str, str]]]] = None) -> Set[str]:
    """Identities closed by a NULL_LOCAL mechanism family: latest verdict per
    hypothesis (append-only ledgers -> last row wins), mapped through the
    declared KNOWN_MAPPINGS (template, pair) entries. A NULL_LOCAL hypothesis
    with no mapping closes nothing here -- it never entered the grammar."""
    last: Dict[str, str] = {}
    for path in (ledger_paths or KI.LEDGERS).values():
        for row in KI._load_ledger(path):  # noqa: SLF001 -- same-package reuse
            hyp = row.get("hypothesis")
            if hyp:
                last[str(hyp)] = str(row.get("verdict"))
    maps = mappings if mappings is not None else KI.KNOWN_MAPPINGS
    out: Set[str] = set()
    for hyp, verdict in last.items():
        if verdict != "NULL_LOCAL":
            continue
        for m in maps.get(hyp, []):
            out.add(_identity(m["template_id"], m["attr_a"], m["attr_b"]))
    return out


def _sport_pool(sport: str, k: int, ledger_rows: List[Dict[str, Any]],
                exhausted: Dict[str, bool],
                knowledge_ledgers: Optional[Dict[str, Path]]) -> List[GEN.Candidate]:
    """One sport's ordered proposal stream: knowledge-mapped candidates first
    (higher-prior hypotheses), then blind enumeration per template. Exhausted
    templates are rotated out; next_batch already dedupes candidate_id vs ledger."""
    cands: List[GEN.Candidate] = []
    try:
        cands += [c for c in KI.knowledge_candidates(knowledge_ledgers or KI.LEDGERS)
                  if c.sport == sport and not exhausted.get(c.template_id)]
    except Exception:  # noqa: BLE001 -- knowledge intake failing must not kill blind proposal
        pass
    for tid in sorted(t for t, s in GEN.TEMPLATES.items() if s["sport"] == sport):
        if exhausted.get(tid):
            continue
        cands += GEN.next_batch(tid, k, ledger_rows)
    return cands


def _draw(k: int, ledger_rows: List[Dict[str, Any]], exhausted: Dict[str, bool], *,
          reject_ledger_path: Optional[Path], knowledge_ledgers: Optional[Dict[str, Path]],
          mappings: Optional[Dict[str, List[Dict[str, str]]]]) -> Tuple[List[GEN.Candidate], int]:
    """Up to k novel candidates, ROUND-ROBIN one per sport per round, each
    deduped against every prior ledger identity and refused if closed-class.
    Returns (drawn, n_refused_closed_class)."""
    # NOT_TESTABLE is non-terminal (builder/data wasn't ready at test time) --
    # exclude those rows from BOTH dedup sets so a candidate whose only ledger
    # rows are NOT_TESTABLE re-enters the draw once its builder/data lands,
    # same exclusion generator.tested_ids applies per-template (every other
    # verdict, blind or '::src=knowledge', stays terminal).
    live_rows = [r for r in ledger_rows if r.get("verdict") != "NOT_TESTABLE"]
    prior_ids = {r.get("candidate_id") for r in live_rows}
    prior_idents = {_row_identity(r) for r in live_rows}
    closed_attrs = _reject_closed_attrs(reject_ledger_path)
    closed_idents = _null_local_identities(knowledge_ledgers, mappings)
    sports = sorted({t["sport"] for t in GEN.TEMPLATES.values()})
    streams = {s: iter(_sport_pool(s, k, ledger_rows, exhausted, knowledge_ledgers))
               for s in sports}
    drawn: List[GEN.Candidate] = []
    seen: Set[str] = set()
    refused_closed = 0
    while len(drawn) < k:
        progressed = False
        for sport in sports:
            if len(drawn) >= k:
                break
            for c in streams[sport]:
                ident = _identity(c.template_id, c.attr_a, c.attr_b, c.entity_class)
                if c.candidate_id in prior_ids or ident in prior_idents or ident in seen:
                    continue
                if (ident in closed_idents or (c.sport, c.attr_a) in closed_attrs
                        or (c.sport, c.attr_b) in closed_attrs):
                    refused_closed += 1
                    continue
                drawn.append(c)
                seen.add(ident)
                progressed = True
                break
        if not progressed:
            break
    return drawn, refused_closed


def run_propose_gate(watermarks: Dict[str, Any], *, k: int = DEFAULT_K,
                     wall_clock_cap_sec: float = DEFAULT_WALL_CLOCK_CAP_SEC,
                     ledger_path: Optional[Path] = None,
                     reject_ledger_path: Optional[Path] = None,
                     knowledge_ledgers: Optional[Dict[str, Path]] = None,
                     mappings: Optional[Dict[str, List[Dict[str, str]]]] = None,
                     run_batch_fn: Optional[Callable[..., List[Dict[str, Any]]]] = None,
                     queue_fn: Optional[Callable[[Dict[str, Any]], Any]] = None,
                     clock: Optional[Callable[[], float]] = None) -> Dict[str, Any]:
    """One M10 tick: draw -> gate -> honest verdict rows (appended by the gate
    itself). Mutates `watermarks[STATE_KEY]` in place (dry counts + exhausted
    pools), same convention as M02/M07/M08. Never raises out of a group."""
    from scripts.platformkit.interaction_factory import runner as IFR

    _clock = clock or _time.time
    lp = ledger_path or IFR.LEDGER_PATH
    state = dict(watermarks.get(STATE_KEY) or {})
    dry: Dict[str, int] = {str(t): int(n) for t, n in (state.get("dry_cycles") or {}).items()}
    exhausted: Dict[str, bool] = {str(t): True for t in (state.get("exhausted") or [])}

    ledger_rows = IFR._load_ledger(lp)  # noqa: SLF001 -- the runner's own reader
    batch, refused_closed = _draw(k, ledger_rows, exhausted,
                                  reject_ledger_path=reject_ledger_path,
                                  knowledge_ledgers=knowledge_ledgers, mappings=mappings)
    run_fn = run_batch_fn or (
        lambda tid, kk, cands: IFR.run_batch(tid, kk, ledger_path=lp, candidates=cands))

    by_tpl: Dict[str, List[GEN.Candidate]] = {}
    for c in batch:
        by_tpl.setdefault(c.template_id, []).append(c)

    per_template: Dict[str, Any] = {}
    by_verdict: Dict[str, int] = {}
    deferred: List[str] = []
    exhausted_logged: List[str] = []
    gated_rows = 0
    t0 = _clock()
    for tid in sorted(by_tpl):
        if _clock() - t0 > float(wall_clock_cap_sec):
            deferred.append(tid)  # over budget: candidates stay untested (re-drawn next cycle)
            continue
        try:
            rows = run_fn(tid, len(by_tpl[tid]), by_tpl[tid])
        except Exception as exc:  # noqa: BLE001 -- one pool's gate failure never blocks siblings
            per_template[tid] = {"status": "error", "error": str(exc)[:200]}
            continue
        gated_rows += len(rows)
        verdicts = [str(r.get("verdict")) for r in rows]
        for v in verdicts:
            by_verdict[v] = by_verdict.get(v, 0) + 1
        only_nt = bool(verdicts) and all(v == IFR.NOT_TESTABLE for v in verdicts)
        dry[tid] = (dry.get(tid, 0) + 1) if only_nt else 0
        per_template[tid] = {"status": "ran", "n_rows": len(rows), "dry_cycles": dry[tid]}
        if dry[tid] >= DRY_CYCLES_TO_EXHAUST:
            exhausted[tid] = True
            exhausted_logged.append(tid)
            if queue_fn is not None:
                queue_fn({"kind": "POOL_EXHAUSTED", "ts": _now_iso(), "template_id": tid,
                          "sport": GEN.TEMPLATES.get(tid, {}).get("sport"),
                          "note": "%d consecutive NOT_TESTABLE-only cycles -- pool rotated out"
                                  % DRY_CYCLES_TO_EXHAUST})

    watermarks[STATE_KEY] = {"dry_cycles": {t: n for t, n in dry.items() if n > 0},
                             "exhausted": sorted(exhausted), "last_run_ts": _now_iso()}
    return {"status": "ran" if batch else "all_pools_dry", "k_declared": int(k),
            "proposed": len(batch), "gated_rows": gated_rows, "by_verdict": by_verdict,
            "refused_closed_class": refused_closed, "deferred_over_cap": deferred,
            "exhausted_logged": exhausted_logged, "per_template": per_template,
            "wall_clock_sec": round(_clock() - t0, 3)}


__all__ = ["run_propose_gate", "STATE_KEY", "DEFAULT_K", "DEFAULT_WALL_CLOCK_CAP_SEC",
           "DRY_CYCLES_TO_EXHAUST", "CLOSED_VERDICTS", "REJECT_LEDGER_PATH"]
