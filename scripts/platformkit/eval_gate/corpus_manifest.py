"""S678 closed-shard corpus manifest: full-file sha256 per closed day shard, verify, cite, prereg embed.

python -m scripts.platformkit.eval_gate.corpus_manifest build --day D --as-of T --root L=PATH ... --out-dir DIR
python -m scripts.platformkit.eval_gate.corpus_manifest verify --manifest P --root L=PATH ...
python -m scripts.platformkit.eval_gate.corpus_manifest cite --manifest P --repo-root R
python -m scripts.platformkit.eval_gate.corpus_manifest order --repo R --manifest REL --night REL [--sha S]
Layout = <root>/<sport>/<day>.jsonl (forward_qualification_inputs._archives). Each shard is hashed in
full (1 MiB chunks), so a same-size mid-shard edit that S550's head/tail identity cannot see changes
the digest. Siblings `<day>.*` other than the shard (writer quarantine files) are listed by bytes,
never hashed. Manifest bytes are canonical JSON + one LF with no host, time or absolute path, so a
rebuild over the same files is byte-identical. Roots are REQUIRED (the tick owner chooses them); a
link or reparse point anywhere from a root to a shard is refused. The manifest covers day D only:
the D+1 shard the night also reads is still open and is NOT covered (`covered_days`). Exit 0 ok,
2 bad input, 3 refused. PAPER / ARCHIVE-READ ONLY: no venue client, never writes under data/.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import stat
import sys
from datetime import date, datetime, timedelta, timezone

from scripts.platformkit.eval_gate.corpus_manifest_output import (
    durable_replace, is_registry_destination, publish, validate_manifest,
)
SCHEMA, GRACE_S, CHUNK = "s678_corpus_manifest_v1", 300, 2 ** 20
CLI_ERRORS = 0
LABEL_RE = re.compile(r"[a-z0-9_]+")
DAY_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
ASOF_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z")
SHA_RE = re.compile(r"[0-9a-f]{64}")
REPARSE = 0x400  # FILE_ATTRIBUTE_REPARSE_POINT (Windows junctions); absent attribute on Linux
SEAL_KEYS, CITE_KEYS = ("seal", "sha256"), ("corpus_manifest_path", "corpus_manifest_sha256", "covered_days")


class BadInput(Exception):
    """Malformed request: exit 2."""


class Refused(Exception):
    """A named refusal: exit 3, no manifest written."""


def canonical(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")


def parse_day(day: str) -> date:
    if not isinstance(day, str) or not DAY_RE.fullmatch(day):
        raise BadInput(f"bad_day {day!r}")
    try:
        return date(*map(int, day.split("-")))
    except ValueError:
        raise BadInput(f"bad_day {day!r}") from None


def parse_as_of(as_of: str) -> datetime:
    if not isinstance(as_of, str) or not ASOF_RE.fullmatch(as_of):
        raise BadInput(f"bad_as_of {as_of!r} (explicit UTC, Z suffix)")
    fmt = "%Y-%m-%dT%H:%M:%S.%fZ" if "." in as_of else "%Y-%m-%dT%H:%M:%SZ"
    try:
        return datetime.strptime(as_of, fmt).replace(tzinfo=timezone.utc)
    except ValueError:
        raise BadInput(f"bad_as_of {as_of!r}") from None


def is_closed(day: str, as_of: str, grace_s: int = GRACE_S) -> bool:
    d = parse_day(day)
    boundary = datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(days=1, seconds=grace_s)
    return parse_as_of(as_of) >= boundary


def parse_roots(roots) -> dict:
    """{label: path}; label ~ [a-z0-9_]+ so no path text ever reaches the manifest."""
    if isinstance(roots, (list, tuple)):
        pairs = [r.split("=", 1) if "=" in r else (r, None) for r in roots]
        roots = {}
        for label, path in pairs:
            if path is None or label in roots:
                raise BadInput(f"bad_root {label!r}")
            roots[label] = path
    if not isinstance(roots, dict) or not roots:
        raise BadInput("roots_required")
    for label, path in roots.items():
        if not isinstance(label, str) or not LABEL_RE.fullmatch(label) or not isinstance(path, str) or not path:
            raise BadInput(f"bad_root {label!r}")
    return dict(roots)


def _is_link(path: str) -> bool:
    st = os.lstat(path)
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & REPARSE)


def _check_links(root: str, *parts: str) -> None:
    """Refuse a link/reparse point on the root or any component below it, or a realpath escape."""
    cur = root
    if _is_link(cur):
        raise Refused("link_in_path")
    for part in parts:
        cur = os.path.join(cur, part)
        if _is_link(cur):
            raise Refused("link_in_path")
    real_root = os.path.realpath(root)
    if os.path.commonpath([real_root, os.path.realpath(cur)]) != real_root:
        raise Refused("link_in_path")


def hash_shard(path: str) -> dict:
    """Full-file sha256, bytes, LF count and torn-tail bytes; refuse if the file moved while hashed."""
    before = os.lstat(path)
    digest, size, last_end, lines = hashlib.sha256(), 0, 0, 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            digest.update(chunk)
            nl = chunk.rfind(b"\n")
            if nl >= 0:
                last_end = size + nl + 1
            lines += chunk.count(b"\n")
            size += len(chunk)
    after = os.lstat(path)
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or after.st_size != size:
        raise Refused("shard_unstable")
    return {"bytes": size, "lines": lines, "sha256": digest.hexdigest(), "torn_tail_bytes": size - last_end}


def enumerate_day(day: str, roots: dict) -> tuple:
    """(roots_meta, shards, sidecars) for exactly <root>/<sport>/<day>.jsonl; nested files ignored."""
    parse_day(day)
    roots = parse_roots(roots)
    meta, shards, sidecars = [], [], []
    name = day + ".jsonl"
    for label in sorted(roots):
        root = roots[label]
        if not os.path.lexists(root) or not (os.path.isdir(root) or _is_link(root)):
            meta.append({"label": label, "root_present": False})
            continue
        _check_links(root)
        meta.append({"label": label, "root_present": True})
        for sport in sorted(os.listdir(root)):
            sport_dir = os.path.join(root, sport)
            if _is_link(sport_dir):
                raise Refused("link_in_path")
            if not os.path.isdir(sport_dir):
                continue
            for entry in sorted(os.listdir(sport_dir)):
                if not entry.startswith(day + "."):
                    continue
                full = os.path.join(sport_dir, entry)
                _check_links(root, sport, entry)
                if not os.path.isfile(full):
                    continue
                rel = sport + "/" + entry
                if entry == name:
                    shards.append(dict(label=label, relpath=rel, **hash_shard(full)))
                else:
                    sidecars.append({"label": label, "relpath": rel, "bytes": os.lstat(full).st_size})
    return meta, shards, sidecars


def build(day: str, roots, as_of: str, grace_s: int = GRACE_S) -> dict:
    """Manifest dict for a CLOSED day; refuses an open day or a torn shard."""
    if not is_closed(day, as_of, grace_s):
        raise Refused("day_not_closed")
    meta, shards, sidecars = enumerate_day(day, roots)
    if any(s["torn_tail_bytes"] for s in shards):
        raise Refused("torn_tail")
    return {"schema": SCHEMA, "day": day, "covered_days": [day],
            "closed_rule": f"as_of >= {day}+1d T00:00:00Z + {grace_s} s",
            "roots": meta, "n_shards": len(shards), "shards": shards, "sidecars": sidecars}


def write(manifest: dict, out_dir: str) -> str:
    """Write <out_dir>/<day>.json atomically; identical bytes = no-op; different bytes refused."""
    if is_registry_destination(out_dir): raise Refused("registry_destination")
    data = canonical(manifest)
    path = os.path.join(out_dir, parse_day(manifest["day"]).isoformat() + ".json")
    return publish(data, path, Refused)


def load(path: str) -> tuple:
    """(manifest, LF-normalized canonical bytes); refuses malformed or foreign-schema files."""
    with open(path, "rb") as f:
        raw = f.read().replace(b"\r\n", b"\n")
    try:
        manifest = json.loads(raw.decode("ascii"))
    except (UnicodeDecodeError, ValueError):
        raise Refused("manifest_unparsed") from None
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA or canonical(manifest) != raw:
        raise Refused("manifest_not_canonical")
    validate_manifest(manifest, SCHEMA, Refused)
    return manifest, raw


def verify(manifest: dict, roots) -> list:
    """Sorted refusal reasons (empty = every digest reproduced and nothing appeared or vanished)."""
    validate_manifest(manifest, SCHEMA, Refused)
    roots = parse_roots(roots)
    if sorted(roots) != sorted(r["label"] for r in manifest["roots"]):
        raise BadInput("root_labels_differ")
    meta, shards, sidecars = enumerate_day(manifest["day"], roots)
    reasons = set()
    old = {(s["label"], s["relpath"]): s for s in manifest["shards"]}
    new = {(s["label"], s["relpath"]): s for s in shards}
    for key, s in old.items():
        cur = new.get(key)
        if cur is None:
            reasons.add("shard_missing")
        elif cur["bytes"] != s["bytes"]:
            reasons.add("shard_resized")
        elif cur["sha256"] != s["sha256"]:
            reasons.add("shard_rehash_mismatch")
    if set(new) - set(old):
        reasons.add("shard_unlisted")
    if any(s["torn_tail_bytes"] for s in shards):
        reasons.add("torn_tail")
    if sorted(map(canonical, sidecars)) != sorted(map(canonical, manifest["sidecars"])):
        reasons.add("sidecar_changed")
    return sorted(reasons)


def cite(manifest_path: str, repo_root: str) -> dict:
    """The night citation: repo-relative POSIX path, LF-canonical sha256, covered_days [D] only."""
    manifest, raw = load(manifest_path)
    rel = os.path.relpath(os.path.realpath(manifest_path), os.path.realpath(repo_root))
    if rel.startswith("..") or os.path.isabs(rel):
        raise Refused("manifest_outside_repo")
    return {"corpus_manifest_path": rel.replace(os.sep, "/"),
            "corpus_manifest_sha256": hashlib.sha256(raw).hexdigest(),
            "covered_days": list(manifest["covered_days"])}


def embed_into_prereg(prereg: dict, citations: list) -> dict:
    """A NEW unsealed prereg dict carrying `corpus_manifests`; the input is never mutated or written."""
    if not isinstance(prereg, dict):
        raise Refused("prereg_not_dict")
    if any(k in prereg for k in SEAL_KEYS):
        raise Refused("prereg_already_sealed")
    if "corpus_manifests" in prereg:
        raise Refused("corpus_manifests_present")
    if not isinstance(citations, list) or not citations:
        raise BadInput("citations_required")
    for c in citations:
        if (not isinstance(c, dict) or sorted(c) != sorted(CITE_KEYS)
                or not SHA_RE.fullmatch(str(c["corpus_manifest_sha256"]))):
            raise BadInput("bad_citation")
    out = copy.deepcopy(prereg)
    out["corpus_manifests"] = sorted(copy.deepcopy(citations), key=lambda c: c["corpus_manifest_path"])
    return out


def main(argv=None) -> int:
    global CLI_ERRORS
    ap = argparse.ArgumentParser(prog="corpus_manifest")
    sub = ap.add_subparsers(dest="cmd", required=True)
    spec = {"build": ("day", "as-of", "out-dir", "root"), "verify": ("manifest", "root"),
            "cite": ("manifest", "repo-root"), "order": ("repo", "manifest", "night")}
    for cmd, flags in spec.items():
        p = sub.add_parser(cmd)
        for flag in flags:
            p.add_argument("--" + flag, required=True, action="append" if flag == "root" else "store")
    sub.choices["order"].add_argument("--sha")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "build":
            m = build(a.day, a.root, a.as_of)
            path = write(m, a.out_dir)
            print(f"WROTE {os.path.basename(path)} n_shards={m['n_shards']} sha256={hashlib.sha256(canonical(m)).hexdigest()}")
        elif a.cmd == "verify":
            reasons = verify(load(a.manifest)[0], a.root)
            print("OK" if not reasons else "REFUSED " + ",".join(reasons))
            return 3 if reasons else 0
        elif a.cmd == "cite":
            print(json.dumps(cite(a.manifest, a.repo_root), sort_keys=True))
        else:
            from scripts.platformkit.eval_gate.corpus_manifest_git import committed_before
            ok, reason = committed_before(a.repo, a.manifest, a.night, a.sha)
            print(("BEFORE " if ok else "NOT_BEFORE ") + reason)
            return 0 if ok else 3
    except (BadInput, OSError) as exc:
        CLI_ERRORS += 1
        print(f"BAD_INPUT {exc}")
        return 2
    except Refused as exc:
        CLI_ERRORS += 1
        print(f"REFUSED {exc}")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
