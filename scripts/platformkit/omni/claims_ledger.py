"""scripts.platformkit.omni.claims_ledger -- OMNI claims ledger (P2).

journal.jsonl (append-only, source of truth) + claims.parquet (rebuildable
dual-index view). Every lifecycle event -- a new claim, a lifecycle flip, a
downstream flag -- is one append_jsonl_atomic row; claims.parquet is replayed
from the journal on demand, never hand-edited.

Claim shape (see .planning/omni/handoff/P2_schema.md for the full column
mapping against data/registry/signal_lab_registry.parquet):
    statement, type, scope{sport,entity_type,entity_ids,context,seasons,
        regime,market_families}, topic, effect{...}, lifecycle, evidence{...},
        provenance{...}, links{parent_claims,child_claims,...}, review{...}

INVARIANTS: pandas/pyarrow + stdlib only. <=300 LOC. ASCII stdout. Never
writes data/registry/. No $/edge claims -- claims here are calibration
mechanisms/effects, not bets.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import tempfile
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from scripts.platformkit.io_atomic import append_jsonl_atomic, write_text_atomic

_CLAIMS_DIR = pathlib.Path("data/omni/claims")
_JOURNAL_NAME = "journal.jsonl"
_PARQUET_NAME = "claims.parquet"

_FLAT_COLS = [
    "claim_id", "statement", "type", "scope_json", "effect_json", "lifecycle",
    "evidence_json", "provenance_json", "links_json", "review_json",
    "sport", "regime", "entity_ids_flat", "topic",
]

_EMPTY_DICT_FIELDS = ("effect", "evidence", "provenance", "links", "review")


def _dir(base_dir: pathlib.Path | str | None) -> pathlib.Path:
    return pathlib.Path(base_dir) if base_dir is not None else _CLAIMS_DIR


def _journal_path(base_dir=None) -> pathlib.Path:
    return _dir(base_dir) / _JOURNAL_NAME


def _parquet_path(base_dir=None) -> pathlib.Path:
    return _dir(base_dir) / _PARQUET_NAME


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_claim_id(statement: str, scope: dict) -> str:
    sig = statement + json.dumps(scope or {}, sort_keys=True, default=str)
    return hashlib.sha1(sig.encode("utf-8")).hexdigest()[:16]


def add_claim(claim: dict, base_dir=None) -> str:
    """Journal an "add" event for *claim*, rebuild the parquet view, return claim_id.

    Required: statement (str), type (str), scope (dict with at least 'sport').
    Everything else defaults to {} / 'proposed' if absent.
    """
    statement = claim["statement"]
    ctype = claim["type"]
    scope = claim.get("scope") or {}
    if "sport" not in scope:
        raise ValueError("claim.scope must include 'sport'")
    claim_id = claim.get("claim_id") or make_claim_id(statement, scope)
    row = {
        "event": "add", "claim_id": claim_id, "ts": _utc_now_iso(),
        "statement": statement, "type": ctype, "scope": scope,
        "topic": claim.get("topic", ""),
        "lifecycle": claim.get("lifecycle", "proposed"),
    }
    for f in _EMPTY_DICT_FIELDS:
        row[f] = claim.get(f) or {}
    append_jsonl_atomic(_journal_path(base_dir), row)
    rebuild_parquet(base_dir)
    return claim_id


def set_lifecycle(claim_id: str, state: str, review: dict | None = None, base_dir=None) -> None:
    """Append a lifecycle-flip event; rebuild parquet so query() reflects it."""
    row = {
        "event": "lifecycle", "claim_id": claim_id, "ts": _utc_now_iso(),
        "lifecycle": state, "review": review or {},
    }
    append_jsonl_atomic(_journal_path(base_dir), row)
    rebuild_parquet(base_dir)


def _replay_journal(base_dir=None) -> dict[str, dict]:
    """Replay journal.jsonl into {claim_id: full_row}. Source-of-truth read path."""
    path = _journal_path(base_dir)
    state: dict[str, dict] = {}
    if not path.is_file():
        return state
    with open(path, encoding="ascii") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            ev = json.loads(line)
            cid = ev["claim_id"]
            if ev["event"] == "add":
                row = {k: ev.get(k) for k in
                       ("statement", "type", "scope", "topic", "lifecycle",
                        *_EMPTY_DICT_FIELDS)}
                row["claim_id"] = cid
                state[cid] = row
            elif ev["event"] in ("lifecycle", "flag"):
                if cid not in state:
                    continue  # ponytail: orphan event (add row lost/out of order) -- skip, don't crash a rebuild
                state[cid]["lifecycle"] = ev["lifecycle"]
                if ev.get("review"):
                    state[cid]["review"] = {**state[cid].get("review", {}), **ev["review"]}
    return state


def _write_parquet_atomic(path: pathlib.Path, df: pd.DataFrame) -> None:
    """tmp-in-same-dir + os.replace -- mirrors omni.feature_store's binary-parquet
    discipline (that helper is module-private there too; a third call site
    should promote both into one shared scripts.platformkit.io_atomic helper)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".parquet")
    os.close(fd)
    tmp = pathlib.Path(tmp_name)
    try:
        df.to_parquet(tmp, index=False)
        os.replace(str(tmp), str(path))
    except BaseException:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise


def rebuild_parquet(base_dir=None) -> pd.DataFrame:
    """Replay the journal and rewrite claims.parquet as a flat dual-index view."""
    state = _replay_journal(base_dir)
    rows = []
    for cid, r in state.items():
        scope = r.get("scope") or {}
        entity_ids = scope.get("entity_ids") or []
        rows.append({
            "claim_id": cid,
            "statement": r.get("statement", ""),
            "type": r.get("type", ""),
            "scope_json": json.dumps(scope, sort_keys=True, default=str),
            "effect_json": json.dumps(r.get("effect") or {}, sort_keys=True, default=str),
            "lifecycle": r.get("lifecycle", "proposed"),
            "evidence_json": json.dumps(r.get("evidence") or {}, sort_keys=True, default=str),
            "provenance_json": json.dumps(r.get("provenance") or {}, sort_keys=True, default=str),
            "links_json": json.dumps(r.get("links") or {}, sort_keys=True, default=str),
            "review_json": json.dumps(r.get("review") or {}, sort_keys=True, default=str),
            "sport": scope.get("sport", ""),
            "regime": scope.get("regime", ""),
            "entity_ids_flat": ";".join(str(e) for e in entity_ids),
            "topic": r.get("topic", ""),
        })
    df = pd.DataFrame(rows, columns=_FLAT_COLS)
    _write_parquet_atomic(_parquet_path(base_dir), df)
    return df


def query(sport=None, entity=None, topic=None, lifecycle=None, type=None, base_dir=None) -> pd.DataFrame:
    """Filter the parquet dual-index view. Rebuilds first if the view is missing."""
    path = _parquet_path(base_dir)
    df = pd.read_parquet(path) if path.is_file() else rebuild_parquet(base_dir)
    if sport is not None:
        df = df[df["sport"] == sport]
    if entity is not None:
        df = df[df["entity_ids_flat"].str.contains(rf"(?:^|;){entity}(?:;|$)", regex=True, na=False)]
    if topic is not None:
        df = df[df["topic"] == topic]
    if lifecycle is not None:
        df = df[df["lifecycle"] == lifecycle]
    if type is not None:
        df = df[df["type"] == type]
    return df.reset_index(drop=True)


def flag_downstream(claim_id: str, base_dir=None) -> list[str]:
    """Walk links_json.child_claims transitively from *claim_id* and journal a
    'flag' lifecycle event on every descendant (cycle-safe). Returns the
    flagged claim_ids.

    # ponytail: local BFS over links_json.child_claims -- effect_graph.py
    (scripts/platformkit/answers/effect_graph.py) is a different composed
    artifact sourced from validation_ledger/factory_ledger rows, not claims;
    it has no claims-parent/child edge model to extend. If effect_graph grows
    a generic node/edge walker, point this at it instead of duplicating BFS.
    """
    state = _replay_journal(base_dir)
    flagged: list[str] = []
    seen = {claim_id}
    frontier = [claim_id]
    while frontier:
        nxt = []
        for cid in frontier:
            children = (state.get(cid, {}).get("links") or {}).get("child_claims") or []
            for child in children:
                if child in seen:
                    continue
                seen.add(child)
                nxt.append(child)
                flagged.append(child)
        frontier = nxt
    for cid in flagged:
        row = {
            "event": "flag", "claim_id": cid, "ts": _utc_now_iso(),
            "lifecycle": "flagged", "review": {"flagged_by_parent": claim_id},
        }
        append_jsonl_atomic(_journal_path(base_dir), row)
    if flagged:
        rebuild_parquet(base_dir)
    return flagged


def add_claims_batch(claims, base_dir=None):
    """Add many claims in ONE atomic journal rewrite + ONE parquet rebuild.
    ~150x faster than per-claim add_claim() at sweep volume (6k claims: 13s
    vs ~25min — measured by the k_sweep_playprofile lane, promoted here so
    every sweep benefits). Content-hash idempotent like add_claim.
    Returns (added_count, claim_ids_of_added)."""
    path = _journal_path(base_dir)
    existing = path.read_text(encoding="ascii") if path.is_file() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    try:
        existing_ids = set(query(base_dir=base_dir)["claim_id"])
    except Exception:
        existing_ids = set()
    lines, added_ids = [], []
    for claim in claims:
        claim_id = make_claim_id(claim["statement"], claim["scope"])
        if claim_id in existing_ids:
            continue
        row = {
            "event": "add", "claim_id": claim_id, "ts": _utc_now_iso(),
            "statement": claim["statement"], "type": claim["type"],
            "scope": claim["scope"], "topic": claim.get("topic", ""),
            "lifecycle": claim.get("lifecycle", "proposed"),
        }
        for f in ("effect", "evidence", "provenance", "links", "review"):
            row[f] = claim.get(f) or {}
        lines.append(json.dumps(row, ensure_ascii=True, sort_keys=True, default=str))
        existing_ids.add(claim_id)
        added_ids.append(claim_id)
    if lines:
        write_text_atomic(path, existing + "\n".join(lines) + "\n", encoding="ascii")
        rebuild_parquet(base_dir)
    return len(added_ids), added_ids


__all__ = [
    "make_claim_id", "add_claim", "set_lifecycle", "rebuild_parquet",
    "query", "flag_downstream", "add_claims_batch",
]
