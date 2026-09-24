"""Sealed family identity, validation, and idempotent charge receipts (S396 Q1/Q2).
The allowance divisor is n_declared_evaluable; every member/contrast/window is counted.
Registry builders bind features:<signal_id>; catalog declarations bind build(ctx).
A digest is charged once. Explicit failure resume reuses its original ledger K.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Sequence
from scripts.platformkit.eval_gate.walkforward import TEST_VIEW_KEYS
from scripts.platformkit.clv_ledger_io import ledger_lock
SOURCES = ("catalog", "registry")
TARGET = "settled home-win outcome"
HORIZON = "pregame close"
REFERENCE = "devigged close p_close"
LINK = "logit(p_close) + beta * z(signal)"
FEATURE_NS = "features:"
EVALUABLE = "EVALUABLE"
NE_PLAYER = "NOT_EVALUABLE:registry entity is player; the gate corpus carries no leak-free per-state player feature"
NE_SCOUTING = "NOT_EVALUABLE:registry consumer is scouting; not an input to the pregame-close decision horizon"
NE_FORMULA = "NOT_EVALUABLE:formula not computable from the state allowed keys; %s is absent from the corpus feature keys"
REGISTRY_COLUMNS = ("signal_id", "entity", "domain", "granularity", "source", "formula", "leak_rule", "consumer", "ev_tier", "coverage_pct", "status")
MEMBER_FIELDS = ("member_key", "signal_id", "source", "hypothesis", "feature_builder", "evaluability", "declares", "alias_of")
MANIFEST_COUNTS = ("n_members", "n_declared_evaluable", "n_not_evaluable", "n_contrasts", "n_windows", "n_hypotheses_counted", "n_allowance_divisor")
FIXED_FIELDS = (("target", TARGET), ("horizon", HORIZON), ("reference", REFERENCE),
                ("link", LINK), ("state_allowed_keys", list(TEST_VIEW_KEYS)))
def strict_int(value: object, field: str) -> int:
    """Counts are strict ints: a bool, a float or a numeric string is refused."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("%s must be a strict int, got %r (%s)" % (field, value, type(value).__name__))
    return int(value)
def write_text_atomic(path: Path, text: str) -> Path:
    """Write ASCII text so a crash leaves either the whole old file or the whole new one."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="ascii", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path
def builder_name(signal_id: str) -> str:
    return FEATURE_NS + str(signal_id)
def resolve_builder(name: str) -> Callable[[dict], float]:
    """The per-state feature builder for a declared `features:<key>` name, the ONLY namespace. The value must already sit on the state's vintage-checked `features` channel -- that is what makes it leak-free -- and a missing key, a bool or a non-finite value is refused, never zeroed."""
    text = str(name)
    if not text.startswith(FEATURE_NS) or not text[len(FEATURE_NS):]:
        raise ValueError("unknown feature builder %r; only %s<key> is declared" % (name, FEATURE_NS))
    key = text[len(FEATURE_NS):]
    def build(state: dict) -> float:
        features = state.get("features")
        if not isinstance(features, dict) or key not in features:
            raise KeyError("feature %r absent from state %r" % (key, state.get("game_id")))
        raw = features[key]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise TypeError("feature %r is %r, not a real number" % (key, raw))
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError("feature %r is not finite in state %r" % (key, state.get("game_id")))
        return value
    return build
def hypothesis_line(signal_id: str, sport: str, start: str, end: str) -> str:
    return "adding %s to the devigged close lowers walk-forward Brier on %s %s..%s" % (signal_id, sport, start, end)
def make_member(signal_id: str, source: str, evaluability: str, sport: str, start: str,
                end: str, *, declares: dict | None = None, builder: str | None = None, alias_of: str | None = None) -> dict:
    """One manifest member. `declares` records what the SOURCE declares (and is what `rederive` re-checks the mark against); `builder` overrides the `features:` namespace."""
    if source not in SOURCES:
        raise ValueError("source must be one of %s, got %r" % (list(SOURCES), source))
    signal_id = str(signal_id).strip()
    if not signal_id:
        raise ValueError("a member needs a non-empty signal_id")
    return {"member_key": source + ":" + signal_id, "signal_id": signal_id, "source": source,
            "hypothesis": hypothesis_line(signal_id, sport, start, end),
            "feature_builder": builder or builder_name(signal_id),
            "evaluability": evaluability, "declares": dict(declares or {}), "alias_of": alias_of}
def registry_evaluability(row: dict, feature_keys: Iterable[str]) -> str:
    """EVALUABLE or the exact NOT_EVALUABLE reason for one registry row."""
    signal_id = str(row.get("signal_id") or "").strip()
    if not signal_id:
        raise ValueError("registry row without signal_id: %r" % (row,))
    if str(row.get("entity") or "").strip().lower() == "player":
        return NE_PLAYER
    if "scouting" in {p.strip().lower() for p in str(row.get("consumer") or "").replace(";", ",").split(",")}:
        return NE_SCOUTING
    if signal_id not in set(feature_keys):
        return NE_FORMULA % builder_name(signal_id)
    return EVALUABLE
def registry_declares(row: dict, keys: Iterable[str]) -> dict:
    """The registry fields evaluability is derived from, SEALED so it can be re-derived."""
    return {"entity": str(row.get("entity") or ""), "consumer": str(row.get("consumer") or ""),
            "feature_keys": sorted({str(key) for key in keys})}
def registry_members(rows, feature_keys: Iterable[str], sport: str, start: str, end: str) -> List[dict]:
    keys = set(feature_keys)
    return [make_member(row["signal_id"], "registry", registry_evaluability(row, keys), sport,
                        start, end, declares=registry_declares(row, keys)) for row in rows]
def build_manifest(family: str, sport: str, start: str, end: str, tier: str,
                   members: Iterable[dict]) -> dict:
    """Assemble the manifest in canonical member order (input order never matters)."""
    ordered = sorted((dict(m) for m in members), key=lambda m: m["member_key"])
    keys = [m["member_key"] for m in ordered]
    if duplicates := sorted({key for key in keys if keys.count(key) > 1}):
        raise ValueError("%d duplicate member key(s) refused (never merged): %s"
                         % (len(duplicates), duplicates))
    n_evaluable = sum(1 for m in ordered if m["evaluability"] == EVALUABLE)
    manifest = {"schema_version": 1, "family": str(family), "sport": str(sport),
                "target": TARGET, "horizon": HORIZON, "reference": REFERENCE, "link": LINK,
                "start": str(start), "end": str(end), "tier": str(tier),
                "state_allowed_keys": list(TEST_VIEW_KEYS), "members": ordered,
                "n_members": len(ordered), "n_declared_evaluable": n_evaluable,
                "n_not_evaluable": len(ordered) - n_evaluable, "n_contrasts": 1,
                "n_windows": 1, "n_hypotheses_counted": len(ordered) + 1 + 1,
                "n_allowance_divisor": n_evaluable}
    return validate_manifest(manifest)
def rederive(member: dict, sport: str) -> tuple:
    """What a member's OWN sealed declarations imply -- never disk (Q1): its evaluability, declares dict and signal_id. Any inequality with what was sealed is refused, so a member whose target, scope, interface, module or registry fields contradict its mark is stopped."""
    if member["source"] == SOURCES[0]:                       # catalog
        from scripts.platformkit.eval_gate import signal_audit_catalog as catalog
        return catalog.recheck(member, sport)
    row = dict(member["declares"], signal_id=member["signal_id"])
    if member["feature_builder"] != builder_name(member["signal_id"]):
        raise ValueError("registry builder contradicts sealed identity")
    if not isinstance(keys := row.get("feature_keys"), list):
        raise ValueError("registry member %r seals no feature_keys" % member["member_key"])
    return registry_evaluability(row, keys), registry_declares(row, keys), member["signal_id"]
def validate_manifest(manifest: dict) -> dict:
    """Refuse a manifest whose family definition, counts, order, fields, member identities or evaluability are wrong: every fixed field is REQUIRED and equality-checked, and every member is RE-DERIVED from its own sealed declarations (`rederive`)."""
    if missing := [k for k in ("family", "sport", "start", "end", "tier", "members") + MANIFEST_COUNTS if k not in manifest]:
        raise ValueError("manifest is missing %r" % missing[0])
    for key, value in FIXED_FIELDS:
        if manifest.get(key) != value:
            raise ValueError("manifest %s must be %r, got %r" % (key, value, manifest.get(key)))
    members = manifest["members"]
    if not isinstance(members, list):
        raise TypeError("members must be a list")
    keys = [m["member_key"] for m in members]
    if keys != sorted(keys) or len(set(keys)) != len(keys):
        raise ValueError("members must be in canonical member_key order with no duplicates")
    for member in members:
        if set(member) != set(MEMBER_FIELDS):
            raise ValueError("member %r has fields %s"
                             % (member.get("member_key"), sorted(member)))
        if not isinstance(member["declares"], dict):
            raise TypeError("declares must be a dict, got %r" % (member["declares"],))
        mark = member["evaluability"]
        if mark != EVALUABLE and not str(mark).startswith("NOT_EVALUABLE:"):
            raise ValueError("evaluability must be %s or NOT_EVALUABLE:<reason>, got %r"
                             % (EVALUABLE, mark))
        identity = (member["source"] + ":" + member["signal_id"], hypothesis_line(
            member["signal_id"], manifest["sport"], manifest["start"], manifest["end"]))
        if (member["member_key"], member["hypothesis"]) != identity or member[
                "source"] not in SOURCES or not str(member["feature_builder"]).strip():
            raise ValueError("member %r does not match its sealed identity %r" % (member.get("member_key"), identity))
        target = member
        if member["alias_of"] is not None:
            target = next((m for m in members if m["member_key"] == member["alias_of"]), None)
            if target is None or target["alias_of"] is not None or any(
                    member[k] != target[k] for k in ("source", "feature_builder", "evaluability", "declares")):
                raise ValueError("alias contradicts sealed identity")
        if (derived := rederive(target, manifest["sport"])) != (
                target["evaluability"], target["declares"], target["signal_id"]):
            raise ValueError("member %r contradicts its own sealed declarations, which re-derive"
                             " %r" % (member["member_key"], derived))
    counts = {name: strict_int(manifest[name], name) for name in MANIFEST_COUNTS}
    n_evaluable = sum(1 for m in members if m["evaluability"] == EVALUABLE)
    expected = {"n_members": len(members), "n_declared_evaluable": n_evaluable,
                "n_not_evaluable": len(members) - n_evaluable, "n_contrasts": 1, "n_windows": 1,
                "n_hypotheses_counted": len(members) + 1 + 1, "n_allowance_divisor": n_evaluable}
    if counts != expected:
        raise ValueError("manifest counts %r do not match the members %r" % (counts, expected))
    return manifest
def canonical_json(manifest: dict) -> str:
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
def digest_path(manifest_path: Path) -> Path:
    return Path(manifest_path).with_name(Path(manifest_path).name + ".sha256")
def seal(manifest_path: Path) -> str:
    """Write the canonical compact JSON ONCE plus a sibling .sha256; return the digest."""
    path = Path(manifest_path)
    sidecar = digest_path(path)
    if sidecar.exists():
        raise FileExistsError("%s is already sealed; a revision is a NEW manifest and a NEW "
                              "charge, never a re-seal" % path)
    manifest = validate_manifest(json.loads(path.read_text(encoding="ascii")))
    write_text_atomic(path, canonical_json(manifest))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    write_text_atomic(sidecar, sha + "\n")
    return sha
def check_seal(manifest_path: Path, raw: bytes | None = None) -> str:
    """Return the sealed digest, refusing an edited manifest or a missing sidecar."""
    path = Path(manifest_path)
    sidecar = digest_path(path)
    if not sidecar.exists():
        raise FileNotFoundError("no seal beside %s; seal the manifest before any run" % path)
    recorded = sidecar.read_text(encoding="ascii").strip()
    raw = path.read_bytes() if raw is None else raw
    actual = hashlib.sha256(raw).hexdigest()
    if actual != recorded:
        raise ValueError("manifest %s was edited after sealing: %s != %s" % (path, actual, recorded))
    validate_manifest(json.loads(raw))
    return actual
@contextmanager
def charged_run(ledger: Path, out: Path, manifest: dict, digest: str, prior: int, commit: str | None,
                resume_charge: str | None, resume_from: Path | None, charger, loader, writer, spec: str):
    """Serialize digest checks and charge recovery; K is the ledger's unique row id.
    Resume reads a prior failure beside its receipt, under --out's parent by default or
    explicitly under --resume-from. Both records must identify this ledger and digest.
    """
    with ledger_lock(Path(str(ledger) + ".signal-audit")):
        matches = [r for r in loader(ledger) if r.get("hypothesis_hash") == digest]
        charge = matches[0] if len(matches) == 1 else None
        if matches:
            if charge is None or str(charge["k_cumulative"]) != resume_charge:
                raise ValueError("charge_exists")
            failures = [Path(resume_from) / "failure.json"] if resume_from else out.parent.glob("*/failure.json")
            valid = False
            for failure in failures:
                receipt = failure.with_name("charge.json")
                if not failure.is_file() or not receipt.is_file() or failure.parent.resolve() == out.resolve():
                    continue
                old, proof = json.loads(failure.read_text()), json.loads(receipt.read_text())
                valid |= (old.get("charge", {}).get("k_cumulative") == charge["k_cumulative"]
                          and old.get("charge", {}).get("hypothesis_hash") == digest
                          and proof.get("hypothesis_hash") == digest
                          and proof.get("k_at_launch") == charge["k_cumulative"]
                          and Path(proof["ledger_path"]).resolve() == ledger.resolve())
            if not valid:
                raise ValueError("charge_exists: resume_failure_missing")
        elif resume_charge is not None:
            raise ValueError("resume_charge_unknown")
        def receipt():
            writer(out / "charge.json", json.dumps({"charge": charge, "k_at_launch": charge["k_cumulative"],
                "charge_row_id": str(charge["k_cumulative"]), "prior_max_k": prior,
                "ledger_path": str(ledger.resolve()), "hypothesis_hash": digest,
                "manifest_committed": commit is not None, "manifest_commit": commit}, sort_keys=True) + "\n")
        try:
            if charge is None:
                try:
                    charge = charger(ledger, spec, manifest["sport"], manifest["start"], manifest["end"],
                                     family=manifest["family"], hypothesis_hash=digest, tier=manifest["tier"])
                except BaseException:
                    charge = next((r for r in loader(ledger) if r.get("hypothesis_hash") == digest), None)
                    raise
            receipt()
            yield charge
        except BaseException as exc:
            if charge is not None:
                if not (out / "charge.json").exists():
                    receipt()
                writer(out / "failure.json", json.dumps({"charge": charge, "k_at_launch": charge["k_cumulative"],
                    "error": "%s: %s" % (type(exc).__name__, exc),
                    "note": "the charge stands; resume explicitly into a new --out"}, sort_keys=True) + "\n")
            raise
def read_registry_rows(parquet_path: Path) -> List[dict]:
    """READ-ONLY read of the declared registry columns. The registry is never written."""
    import pyarrow.parquet as pq
    return [dict(row) for row in pq.read_table(str(parquet_path), columns=list(REGISTRY_COLUMNS)).to_pylist()]
def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="signal_audit_family",
                                     description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, help="manifest JSON path to write")
    parser.add_argument("--family", required=True)
    parser.add_argument("--sport", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--tier", required=True, help="T2 or T3 (the ledger tier vocabulary)")
    parser.add_argument("--registry", default=None, help="READ-ONLY signal registry parquet")
    parser.add_argument("--feature-key", action="append", default=[], help="a per-state key")
    parser.add_argument("--catalog-domain", action="append", default=[], help="domains; all")
    parser.add_argument("--seal", action="store_true", help="seal the manifest after writing it")
    return parser
def main(argv: Sequence[str] | None = None) -> int:
    from scripts.platformkit.eval_gate import signal_audit_catalog as catalog
    args = _parser().parse_args(argv)
    if (out := Path(args.out)).exists() or digest_path(out).exists():
        raise FileExistsError("%s or its seal already exists; a revision is a NEW manifest and a "
                              "NEW charge, so NOTHING is written here" % out)
    members = catalog.members(args.sport, args.start, args.end, domains=args.catalog_domain)
    if args.registry:
        members += registry_members(read_registry_rows(Path(args.registry)),
                                    args.feature_key, args.sport, args.start, args.end)
    manifest = build_manifest(args.family, args.sport, args.start, args.end, args.tier, members)
    write_text_atomic(out, canonical_json(manifest))
    sha = seal(out) if args.seal else "NOT SEALED"
    print("\n".join("%s %d" % (name, manifest[name]) for name in MANIFEST_COUNTS)
          + "\nmanifest %s\nsha256 %s" % (out.as_posix(), sha))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
