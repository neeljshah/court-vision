"""scripts.platformkit.reject_ledger -- the signal GRAVEYARD (institutional memory).

Append-only record of every SIGNAL verdict the leak-free gate returns, so a discovery
loop never re-tests a known-dead signal and humans remember WHAT WAS KILLED AND WHY.
`source`: signal_proof (V3 gate) / recal_ratchet (improve_ledger) / signal_discovery
(_DISCOVERED_LEDGER) / manual. A REJECT is honest market-efficiency EVIDENCE, not failure
(calibration != edge, no $ claim), REVISITABLE once the corpus grows (stale_after_days).
Store: data/frontend/reject_ledger.jsonl (gitignored). stdlib only; ASCII; no secrets.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

_HERE = Path(__file__).resolve().parent
_FRONTEND = _HERE.parents[1] / "data" / "frontend"
DEFAULT_LEDGER = _FRONTEND / "reject_ledger.jsonl"
DEFAULT_IMPROVE_LEDGER = _FRONTEND / "improve_ledger.jsonl"
# The discovery loop's own ledger (src/loop/discovery.py::_DISCOVERED_LEDGER); local-only.
DEFAULT_DISCOVERED_LEDGER = _HERE.parents[1] / ".planning" / "loop" / "discovered_signals.jsonl"

CALIBRATION_NOTE = ("A REJECT is honest market-efficiency evidence, not a failure; "
                    "calibration != edge (no $ claim).")

# Verdicts that mean "this signal did NOT survive the gate" -> graveyard members.
REJECT_VERDICTS = {"REJECT", "DEFER", "BUNDLE_ERROR", "GATE_ERROR"}
VALID_SOURCES = {"signal_proof", "recal_ratchet", "signal_discovery",
                 "funnel_gate", "manual"}

_PROOF_METRIC_KEYS = (  # run_v3 verdict-row metric keys carried into the ledger
    "p_value", "wf_folds", "wf_all_improve", "ablation_delta", "ablation_pass",
    "null_pass", "calibration_ok", "clv", "expected", "passed_expected",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    s = str(ts).strip().replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d


def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # tolerate a partial trailing write
    return rows


def _append(path: Path, rec: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")


def record(sport: str, signal: str, verdict: str, reason: str = "", *,
           corpus: Optional[str] = None, metrics: Optional[Dict[str, Any]] = None,
           source: str = "signal_proof", ts: Optional[str] = None,
           ledger_path: Optional[Path] = None, append: bool = True) -> Dict[str, Any]:
    """Append one signal verdict; return the record (appended unless append=False)."""
    rec = {
        "ts": ts or _now_iso(),
        "sport": _norm(sport),
        "signal": str(signal).strip(),
        "verdict": str(verdict).strip().upper(),
        "reason": str(reason or "")[:400],
        "corpus": corpus,
        "source": source if source in VALID_SOURCES else "manual",
        "metrics": metrics or {},
        "note": CALIBRATION_NOTE,
    }
    if append:
        _append(Path(ledger_path) if ledger_path else DEFAULT_LEDGER, rec)
    return rec


def record_proof_verdicts(sport: str, verdict_rows: Iterable[Dict[str, Any]], *,
                          corpus: Optional[str] = None, source: str = "signal_proof",
                          ledger_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Bulk-ingest run_v3-shaped rows (signal/actual/reason/wf_*/p_value/...)."""
    out: List[Dict[str, Any]] = []
    for r in verdict_rows:
        name = r.get("signal") or r.get("name")
        if not name:
            continue
        metrics = {k: r[k] for k in _PROOF_METRIC_KEYS if k in r}
        out.append(record(
            sport, name, r.get("actual") or r.get("verdict") or "REJECT",
            r.get("reason", ""), corpus=corpus, metrics=metrics, source=source,
            ledger_path=ledger_path,
        ))
    return out


def load(sport: Optional[str] = None, *, source: Optional[str] = None,
         ledger_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """All ledger rows, optionally filtered by sport and/or source."""
    sp = _norm(sport) if sport else None
    out: List[Dict[str, Any]] = []
    for r in _read_jsonl(Path(ledger_path) if ledger_path else DEFAULT_LEDGER):
        if sp and _norm(r.get("sport")) != sp:
            continue
        if source and r.get("source") != source:
            continue
        out.append(r)
    return out


def lookup(sport: str, signal: str, *, corpus: Optional[str] = None,
           ledger_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Latest verdict record for (sport, signal[, corpus]); None if never tested."""
    sig = str(signal).strip()
    cand = [r for r in load(sport, ledger_path=ledger_path)
            if str(r.get("signal", "")).strip() == sig
            and (corpus is None or r.get("corpus") == corpus)]
    return max(cand, key=lambda r: str(r.get("ts", ""))) if cand else None


def is_known_reject(sport: str, signal: str, *, corpus: Optional[str] = None,
                    stale_after_days: Optional[float] = None,
                    ledger_path: Optional[Path] = None) -> bool:
    """True iff this signal's LATEST verdict is a reject -- the discovery-loop skip test.

    A reject older than `stale_after_days` is treated as revisitable (returns False) so a
    grown corpus can resurrect it: the graveyard remembers without forbidding forever.
    """
    rec = lookup(sport, signal, corpus=corpus, ledger_path=ledger_path)
    if rec is None or rec.get("verdict") not in REJECT_VERDICTS:
        return False
    if stale_after_days is not None:
        ts = _parse_ts(rec.get("ts", ""))
        if ts is not None:
            age = (datetime.now(timezone.utc) - ts).total_seconds() / 86400.0
            if age > stale_after_days:
                return False
    return True


def graveyard(sport: Optional[str] = None, *, source: Optional[str] = None,
              ledger_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Latest verdict per (sport, signal); keep only those whose latest is a reject."""
    latest: Dict[tuple, Dict[str, Any]] = {}
    for r in load(sport, source=source, ledger_path=ledger_path):
        key = (_norm(r.get("sport")), str(r.get("signal", "")).strip())
        cur = latest.get(key)
        if cur is None or str(r.get("ts", "")) > str(cur.get("ts", "")):
            latest[key] = r
    dead = [r for r in latest.values() if r.get("verdict") in REJECT_VERDICTS]
    return sorted(dead, key=lambda r: (_norm(r.get("sport")), str(r.get("signal", ""))))


def ingest_improve_ledger(*, improve_path: Optional[Path] = None,
                          ledger_path: Optional[Path] = None) -> int:
    """Fold REJECT rows from improve_ledger.jsonl in as recal_ratchet members.

    Idempotent on (sport, ts): a recal REJECT already present is not duplicated.
    """
    src = _read_jsonl(Path(improve_path) if improve_path else DEFAULT_IMPROVE_LEDGER)
    have = {(_norm(r.get("sport")), str(r.get("ts", "")))
            for r in load(source="recal_ratchet", ledger_path=ledger_path)}
    n = 0
    for r in src:
        if str(r.get("verdict", "")).upper() != "REJECT":
            continue
        key = (_norm(r.get("sport")), str(r.get("ts", "")))
        if key in have:
            continue
        record(r.get("sport", ""), "recalibrator", "REJECT", r.get("reason", ""),
               source="recal_ratchet", ts=r.get("ts"), ledger_path=ledger_path,
               metrics={"delta_brier": r.get("delta_brier"), "dm_p": r.get("dm_p")})
        have.add(key)
        n += 1
    return n


def ingest_discovered_ledger(*, discovered_path: Optional[Path] = None,
                             ledger_path: Optional[Path] = None, sport: str = "nba") -> int:
    """Fold REJECT/DEFER rows from the discovery loop's _DISCOVERED_LEDGER in as
    signal_discovery members. The loop already skips re-rolling tried FAMILIES; this only
    SURFACES its rejects into the cross-sport graveyard. Idempotent on (sport, signal, ts).
    """
    src = _read_jsonl(Path(discovered_path) if discovered_path else DEFAULT_DISCOVERED_LEDGER)
    have = {(_norm(sport), str(r.get("signal", "")).strip(), str(r.get("ts", "")))
            for r in load(source="signal_discovery", ledger_path=ledger_path)}
    n = 0
    for r in src:
        name = str(r.get("name", "")).strip()
        if not name or str(r.get("verdict", "")).upper() not in REJECT_VERDICTS:
            continue
        ts = str(r.get("date", ""))
        if (_norm(sport), name, ts) in have:
            continue
        metrics = {k: r[k] for k in ("family_key", "target", "kind", "screen_score",
                                     "wf_all_improve", "null_z") if k in r}
        record(sport, name, str(r.get("verdict")).upper(),
               f"discovered transform target={r.get('target', '?')} null_z={r.get('null_z', '?')}",
               source="signal_discovery", ts=ts, metrics=metrics, ledger_path=ledger_path)
        have.add((_norm(sport), name, ts))
        n += 1
    return n


def format_graveyard(rows: Sequence[Dict[str, Any]]) -> str:
    out = [
        "SIGNAL GRAVEYARD -- latest verdict per signal that did NOT survive the gate",
        CALIBRATION_NOTE,
        "-" * 92,
        f"{'sport':<7}{'signal':<32}{'verdict':<8}{'source':<18}{'when':<12}reason",
        "-" * 92,
    ]
    for r in rows:
        out.append(
            f"{_norm(r.get('sport')):<7}{str(r.get('signal', ''))[:30]:<32}"
            f"{str(r.get('verdict', '')):<8}{str(r.get('source', '')):<18}"
            f"{str(r.get('ts', ''))[:10]:<12}{str(r.get('reason', ''))[:24]}"
        )
    if not rows:
        out.append("(graveyard empty -- no rejected signals recorded yet)")
    out += ["-" * 92, f"ledger: {DEFAULT_LEDGER}"]
    return "\n".join(out)


def _cli_record(args: argparse.Namespace) -> int:
    rec = record(args.sport, args.signal, args.verdict, args.reason or "",
                 corpus=args.corpus, source=(args.source or "manual"))
    print(f"recorded {rec['sport']}/{rec['signal']} -> {rec['verdict']} ({rec['source']})")
    return 0


def _cli_ingest(kind: str) -> int:
    if kind == "discovered":
        n, label = ingest_discovered_ledger(), "discovery"
    else:
        n, label = ingest_improve_ledger(), "recal-ratchet"
    print(f"folded {n} {label} REJECT row(s) into the graveyard")
    print(format_graveyard(graveyard()))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Signal reject ledger -- the graveyard.")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("show", help="print the graveyard (default)")
    s.add_argument("--sport")
    s.add_argument("--source", choices=sorted(VALID_SOURCES))
    r = sub.add_parser("record", help="hand-record one verdict")
    r.add_argument("sport")
    r.add_argument("signal")
    r.add_argument("verdict")
    r.add_argument("--reason")
    r.add_argument("--corpus")
    r.add_argument("--source", choices=sorted(VALID_SOURCES))
    sub.add_parser("ingest-improve", help="fold improve_ledger REJECTs into the graveyard")
    sub.add_parser("ingest-discovered", help="fold discovery-loop REJECTs into the graveyard")
    args = p.parse_args(argv)
    if args.cmd == "record":
        return _cli_record(args)
    if args.cmd == "ingest-improve":
        return _cli_ingest("improve")
    if args.cmd == "ingest-discovered":
        return _cli_ingest("discovered")
    print(format_graveyard(graveyard(getattr(args, "sport", None),
                                     source=getattr(args, "source", None))))
    return 0


__all__ = [
    "record", "record_proof_verdicts", "load", "lookup", "is_known_reject", "graveyard",
    "ingest_improve_ledger", "ingest_discovered_ledger", "format_graveyard",
    "DEFAULT_LEDGER", "DEFAULT_DISCOVERED_LEDGER", "REJECT_VERDICTS", "CALIBRATION_NOTE",
]


if __name__ == "__main__":
    raise SystemExit(main())
