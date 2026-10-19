"""S678 output-path and artifact safeguards shared by the corpus manifest writer."""
from __future__ import annotations

import os
import re
import stat
import tempfile
from datetime import date
from pathlib import Path

from scripts.platformkit.ops.atomic_replace import replace_with_retry


def _is_under(path: str, parent: str) -> bool:
    """Whether normalized path is parent or below it, without crossing drives on Windows."""
    path, parent = os.path.normcase(os.path.normpath(path)), os.path.normcase(os.path.normpath(parent))
    if os.path.splitdrive(path)[0] != os.path.splitdrive(parent)[0]:
        return False
    return os.path.commonpath([path, parent]) == parent


def is_registry_destination(out_dir: str) -> bool:
    """Protect both the caller's and this repository's lexical/resolved registry paths."""
    lexical = os.path.abspath(out_dir)
    registries = (os.path.abspath(os.path.join("data", "registry")),
                  str(Path(__file__).resolve().parents[3] / "data" / "registry"))
    return any(_is_under(lexical, registry)
               or _is_under(os.path.realpath(lexical), os.path.realpath(registry))
               for registry in registries)


def durable_replace(temporary: str, target: str) -> None:
    """Replace via the shared durable Windows retry helper."""
    replace_with_retry(Path(temporary), Path(target), durable=True)


def publish(data: bytes, path: str, refuse: type[Exception]) -> str:
    """Publish under an exclusive destination lock; contention and stale locks fail closed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lock = path + ".lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise refuse("manifest_locked") from None
    temporary = None
    try:
        os.close(descriptor)
        if os.path.lexists(path):
            st = os.lstat(path)
            if stat.S_ISLNK(st.st_mode) or getattr(st, "st_file_attributes", 0) & 0x400:
                raise refuse("link_in_path")
            with open(path, "rb") as stream:
                if stream.read().replace(b"\r\n", b"\n") == data:
                    return path
            raise refuse("manifest_exists_different")
        descriptor, temporary = tempfile.mkstemp(prefix=Path(path).name + ".", suffix=".tmp",
                                                  dir=os.path.dirname(path))
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        durable_replace(temporary, path)
        return path
    finally:
        try:
            if temporary is not None and os.path.lexists(temporary):
                os.unlink(temporary)
        finally:
            os.unlink(lock)


def validate_manifest(manifest: dict, schema: str, refuse: type[Exception]) -> None:
    """Reject ambiguous identities and malformed or inconsistent manifest metadata."""
    if not isinstance(manifest, dict) or manifest.get("schema") != schema:
        raise refuse("manifest_metadata")
    day = manifest.get("day")
    if not isinstance(day, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day):
        raise refuse("manifest_metadata")
    try:
        date.fromisoformat(day)
    except ValueError:
        raise refuse("manifest_metadata") from None
    rule = manifest.get("closed_rule")
    if (manifest.get("covered_days") != [day] or not isinstance(rule, str)
            or not re.fullmatch(re.escape(f"as_of >= {day}+1d T00:00:00Z + ") + r"[0-9]+ s", rule)
            or any(not isinstance(manifest.get(key), list) for key in ("roots", "shards", "sidecars"))
            or type(manifest.get("n_shards")) is not int
            or manifest["n_shards"] != len(manifest["shards"])):
        raise refuse("manifest_metadata")
    roots = {}
    for root in manifest["roots"]:
        if (not isinstance(root, dict) or not isinstance(root.get("label"), str)
                or not re.fullmatch(r"[a-z0-9_]+", root["label"])
                or root["label"] in roots or type(root.get("root_present")) is not bool):
            raise refuse("manifest_metadata")
        roots[root["label"]] = root["root_present"]
    if not roots:
        raise refuse("manifest_metadata")
    for kind in ("shards", "sidecars"):
        seen = set()
        for item in manifest[kind]:
            if (not isinstance(item, dict) or not isinstance(item.get("label"), str)
                    or not roots.get(item["label"]) or not isinstance(item.get("relpath"), str)):
                raise refuse("manifest_metadata")
            identity = item["label"], item["relpath"]
            if identity in seen:
                raise refuse("duplicate_shard_identity" if kind == "shards" else "duplicate_sidecar_identity")
            seen.add(identity)
            parts = item["relpath"].split("/")
            if (len(parts) != 2 or parts[0] in ("", ".", "..") or "\\" in item["relpath"]
                    or not parts[1].startswith(day + ".")
                    or (parts[1] == day + ".jsonl") != (kind == "shards")):
                raise refuse("manifest_metadata")
            fields = ("bytes", "lines", "torn_tail_bytes") if kind == "shards" else ("bytes",)
            if any(type(item.get(key)) is not int or item[key] < 0 for key in fields):
                raise refuse("manifest_metadata")
            if kind == "shards" and (not isinstance(item.get("sha256"), str)
                    or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
                    or item["lines"] > item["bytes"] or item["torn_tail_bytes"] != 0):
                raise refuse("manifest_metadata")
