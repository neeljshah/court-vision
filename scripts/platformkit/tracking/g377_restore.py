"""G377 restore and byte verification: off-pod sources into an isolated scratch tree.

Sealed in g377_prereg_2026-09-10.md sections 4 and 5.  Sources are tried in priority order
S1..S6; a file found nowhere is MISSING and is NAMED, never inferred and never re-fetched.
Every restored file is verified by git object identity (V1), by a content digest read back
from disk (V2) and, where the pod still holds the path, against the live copy (V3).

Nothing is deleted, moved or written outside the scratch root, and the pod is read only.

Usage:
    python -m scripts.platformkit.tracking.g377_restore --repo <path> --manifest <csv>
        --scratch <dir> --out <dir> [--pod <ssh target>] [--pod-port <n>]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
import subprocess
from pathlib import Path

from scripts.platformkit.tracking.g377_manifest import FILE_STATUSES, POD_ABSOLUTE

REFS = ("master", "pod/track-a7", "pod/track-a13", "pod/track-a10", "pod/track-a18",
        "private/track-a7", "private/track-a13", "private/track-a10", "private/track-a18")
POD_ROOTS = ("/workspace/nba-ai-system", "/workspace/wt/a7", "/workspace/wt/a13",
             "/workspace/wt/a10", "/workspace/wt/a18")
BACKUPS = ("data/pod_backup_2026-09-10", "data/pod_backup_2026-09-08")
POD_ABSENT = "POD_ABSENT"
POD_UNREACHABLE = "POD_UNREACHABLE"
FIELDS = ("closure", "path", "source", "git_oid_expected", "git_oid_restored",
          "sha256_source", "sha256_restored", "sha256_pod", "bytes", "verdict")
MISSING_FIELDS = ("closure", "path", "role", "status", "required_by", "searched", "disables")
EYE_FIELDS = ("closure", "eye_file", "committed_path", "draw", "pixel_kind", "sha256_restored",
              "sha256_pod", "bytes", "verdict")
STEMS = {"G363": "g363_ball_coverage_2026-09-09", "G364": "g364_learned_court_presence_2026-09-09",
         "G367": "g367_init_symmetry_2026-09-09", "G370": "g370_admission_v0_2026-09-09"}


def blob_oid(data: bytes) -> str:
    """The git object id of these bytes, computed in process (git hash-object --no-filters)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def refs_present(repo: Path) -> list[str]:
    """Every search ref that actually exists in this repository, in priority order."""
    out = []
    for ref in REFS:
        done = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", ref],
                              capture_output=True, text=True)
        if done.returncode == 0:
            out.append(ref)
    return out


def backup_refs(repo: Path) -> list[str]:
    """The private remote's backup/track-* refs, listed read only for the receipt."""
    done = subprocess.run(["git", "-C", str(repo), "ls-remote", "private", "refs/heads/backup/*"],
                          capture_output=True, text=True)
    if done.returncode != 0:
        return []
    return sorted(line.split("\t")[-1] for line in done.stdout.splitlines() if line.strip())


def from_git(repo: Path, ref: str, path: str) -> bytes | None:
    """The committed blob at <ref>:<path>, or None when that ref does not carry it."""
    done = subprocess.run(["git", "-C", str(repo), "cat-file", "blob", "%s:%s" % (ref, path)],
                          capture_output=True)
    return done.stdout if done.returncode == 0 else None


def pod_mapping(path: str) -> list[str]:
    """Repository-relative candidates in the synced backups for one pod-absolute path."""
    marker = "/workspace/data/tracking/"
    if not path.startswith(marker):
        return []
    tail = path[len(marker):]
    out = []
    for root in BACKUPS:
        out.append("%s/tracking/%s" % (root, tail))
        if "/" not in tail:
            out.append("%s/%s" % (root, tail))
    return out


def locate(repo: Path, row: dict[str, str], refs: list[str]) -> tuple[str, bytes] | None:
    """First off-pod source holding this path, as (source label, bytes). None means MISSING."""
    path = row["path"]
    if row["status"] != POD_ABSOLUTE:
        for ref in refs:
            data = from_git(repo, ref, path)
            if data is not None:
                return ("S1:" + ref if ref == "master" else "S2:" + ref), data
        local = repo / path
        if local.is_file():
            return "S6:UNCOMMITTED_LOCAL", local.read_bytes()
        return None
    for index, candidate in enumerate(pod_mapping(path)):
        local = repo / candidate
        if local.is_file():
            return "S%d:%s" % (4 + index // 2, candidate), local.read_bytes()
    return None


def pod_digests(target: str, port: str, paths: list[str]) -> dict[str, str]:
    """One read-only sha256sum pass per pod root; absent paths simply do not answer."""
    found: dict[str, str] = {}
    payload = "\n".join(paths).encode("ascii", "ignore")
    for root in POD_ROOTS:
        command = ["ssh", "-o", "ConnectTimeout=20", "-o", "BatchMode=yes", "-p", port, target,
                   "cd %s 2>/dev/null && xargs -r -d '\\n' sha256sum 2>/dev/null" % root]
        done = subprocess.run(command, input=payload, capture_output=True)
        if done.returncode not in (0, 123, 1):
            raise OSError("pod unreachable: %s" % done.stderr.decode("ascii", "ignore")[:200])
        for line in done.stdout.decode("ascii", "ignore").splitlines():
            digest, _sep, name = line.partition("  ")
            if name and name not in found:
                found[name] = digest
    return found


def disabled_by(row: dict[str, str]) -> str:
    """The row a missing file disables: its closure plus every reader that opens it."""
    readers = sorted({reference.split(":")[0].rsplit("/", 1)[-1]
                      for reference in row["required_by"].split("|")
                      if reference.endswith(tuple(str(n) for n in range(10)))
                      and reference.split(":")[0].endswith(".py")})
    return "%s (%s)" % (row["closure"], ", ".join(readers) if readers
                        else "memo-only reference, no reader opens it")


def restore(repo: Path, rows: list[dict[str, str]], scratch: Path,
            refs: list[str], pod: dict[str, str], reachable: bool) -> tuple[list, list]:
    """Write every locatable file into the scratch tree and verify it three ways."""
    verified: list[dict[str, object]] = []
    missing: list[dict[str, object]] = []
    for row in rows:
        found = locate(repo, row, refs)
        if found is None:
            missing.append({"closure": row["closure"], "path": row["path"], "role": row["role"],
                            "status": row["status"], "required_by": row["required_by"],
                            "searched": "S1-S6", "disables": disabled_by(row)})
            continue
        source, data = found
        target = scratch / row["closure"] / row["path"].lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        readback = target.read_bytes()
        expected = row.get("oid", "")
        entry = {"closure": row["closure"], "path": row["path"], "source": source,
                 "git_oid_expected": expected, "git_oid_restored": blob_oid(readback),
                 "sha256_source": hashlib.sha256(data).hexdigest(),
                 "sha256_restored": hashlib.sha256(readback).hexdigest(),
                 "sha256_pod": pod.get(row["path"], POD_ABSENT if reachable else POD_UNREACHABLE),
                 "bytes": len(readback), "verdict": ""}
        checks = [entry["sha256_source"] == entry["sha256_restored"]]
        if expected:
            checks.append(entry["git_oid_restored"] == expected)
        if entry["sha256_pod"] not in (POD_ABSENT, POD_UNREACHABLE):
            checks.append(entry["sha256_pod"] == entry["sha256_restored"])
        entry["verdict"] = "VERIFIED" if all(checks) else "MISMATCH"
        verified.append(entry)
    return verified, missing


def eye_pick(rows: list[dict[str, str]], closure: str) -> list[str]:
    """The sealed even draw: native-pixel paths in sorted order, index 0 and floor(n/2)."""
    pixels = sorted(row["path"] for row in rows
                    if row["closure"] == closure and row["role"] == "native_pixels")
    if len(pixels) < 2:
        return pixels
    return [pixels[0], pixels[len(pixels) // 2]]


def eye_supplement(closure: str, stem: str, tracked: dict[str, tuple[str, int]]) -> list[dict]:
    """Manifest-shaped rows for a closure whose manifest names no restorable native pixel.

    Disclosed, not sealed: the draw is the same even rule over the closure's own committed
    image tree.  It is reported separately from the sealed draw and never enters the manifest.
    """
    base = "docs/evidence/tracking/" + stem + "/"
    images = sorted(name for name in tracked
                    if name.startswith(base) and name.endswith((".jpg", ".png", ".svg")))
    picks = [images[0], images[len(images) // 2]] if len(images) >= 2 else images
    return [{"closure": closure, "path": name, "role": "native_pixels",
             "status": "RESOLVED_TRACKED", "required_by": "eye supplement", "bytes": "",
             "oid": tracked[name][0]} for name in picks]


def eye_check(picks: list[tuple[str, str, str]], verified: list[dict[str, object]],
              scratch: Path, out: Path) -> list[dict[str, object]]:
    """Copy the chosen restored native-pixel files beside their committed digests."""
    digests = {(row["closure"], row["path"]): row for row in verified}
    out.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []
    for closure, path, draw in picks:
        entry = digests.get((closure, path))
        if entry is None:
            continue
        index = sum(1 for row in manifest if row["closure"] == closure)
        name = "%s_eye_%d_%s" % (closure.lower(), index, path.rsplit("/", 1)[-1])
        shutil.copyfile(scratch / closure / path, out / name)
        manifest.append({"closure": closure, "eye_file": name, "committed_path": path,
                         "draw": draw, "pixel_kind": "svg" if path.endswith(".svg") else "raster",
                         "sha256_restored": entry["sha256_restored"],
                         "sha256_pod": entry["sha256_pod"], "bytes": entry["bytes"],
                         "verdict": entry["verdict"]})
    return manifest


def write_csv(rows: list[dict[str, object]], fields: tuple, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="G377 restore and byte verification")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--pod", default="root@213.192.2.120")
    parser.add_argument("--pod-port", default="40117")
    args = parser.parse_args()
    with args.manifest.open(encoding="ascii", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["status"] in FILE_STATUSES]
    sizes = {}
    listing = subprocess.run(["git", "-C", str(args.repo), "ls-tree", "-r", "-l", "master"],
                             capture_output=True, text=True, check=True).stdout
    for line in listing.splitlines():
        meta, _tab, path = line.partition("\t")
        parts = meta.split()
        if len(parts) == 4 and parts[1] == "blob":
            sizes[path] = (parts[2], int(parts[3]))
    for row in rows:
        row["oid"] = sizes.get(row["path"], ("", 0))[0]
    refs = refs_present(args.repo)
    print("REFS available: %s" % " ".join(refs))
    print("BACKUP refs on private: %s" % (" ".join(backup_refs(args.repo)) or "none"))
    reachable, pod = True, {}
    try:
        pod = pod_digests(args.pod, args.pod_port, sorted({row["path"] for row in rows}))
    except OSError as problem:
        reachable = False
        print("POD %s -- %s" % (POD_UNREACHABLE, problem))
    print("POD paths answering: %d" % len(pod))
    verified, missing = restore(args.repo, rows, args.scratch, refs, pod, reachable)
    for key in sorted({row["closure"] for row in rows}):
        named = [row for row in rows if row["closure"] == key]
        got = [row for row in verified if row["closure"] == key]
        on_pod = [row for row in got if row["sha256_pod"] not in (POD_ABSENT, POD_UNREACHABLE)]
        print("PREMISE %s named=%d off_pod=%d on_pod=%d bytes=%d mismatch=%d missing=%d" % (
            key, len(named), len(got), len(on_pod), sum(int(row["bytes"]) for row in got),
            sum(1 for row in got if row["verdict"] == "MISMATCH"),
            sum(1 for row in missing if row["closure"] == key)))
    write_csv(verified, FIELDS, args.out / "restore_hashes.csv")
    write_csv(missing, MISSING_FIELDS, args.out / "missing.csv")
    picks, extra = [], []
    for closure in sorted(STEMS):
        chosen = [path for path in eye_pick(rows, closure)
                  if (closure, path) in {(row["closure"], row["path"]) for row in verified}]
        picks.extend((closure, path, "sealed_manifest") for path in chosen)
        if len(chosen) < 2:
            supplement = eye_supplement(closure, STEMS[closure], sizes)
            extra.extend(supplement)
            picks.extend((closure, row["path"], "disclosed_supplement") for row in supplement)
            print("EYE supplement %s: manifest names no restorable native pixel" % closure)
    more, _absent = restore(args.repo, extra, args.scratch, refs, pod, reachable)
    eyes = eye_check(picks, verified + more, args.scratch, args.out / "eye")
    write_csv(eyes, EYE_FIELDS, args.out / "eye" / "eye_manifest.csv")
    print("EYE files=%d" % len(eyes))
    print("RESTORE verified=%d missing=%d scratch=%s" % (
        len(verified), len(missing), args.scratch.as_posix()))
    return 0


def demo() -> None:
    """Self-check: the git object id matches git's own, and the pod mapping is exact."""
    assert blob_oid(b"") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
    assert blob_oid(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"
    assert pod_mapping("/workspace/wt/a7") == []
    mapped = pod_mapping("/workspace/data/tracking/track_daemon_ledger.jsonl")
    assert "data/pod_backup_2026-09-10/track_daemon_ledger.jsonl" in mapped
    assert mapped[0] == "data/pod_backup_2026-09-10/tracking/track_daemon_ledger.jsonl"
    named = disabled_by({"closure": "G370", "required_by": "a/g370_scorer.py:138|b/memo.md:4"})
    assert named == "G370 (g370_scorer.py)"
    assert "no reader" in disabled_by({"closure": "G363", "required_by": "b/memo.md:9"})
    sample = [{"closure": "C", "role": "native_pixels", "path": "p/%d.jpg" % n} for n in range(5)]
    assert eye_pick(sample, "C") == ["p/0.jpg", "p/2.jpg"]
    tree = {"docs/evidence/tracking/s/a.jpg": ("o1", 1), "docs/evidence/tracking/s/b.jpg": ("o2", 2)}
    assert [row["path"] for row in eye_supplement("G", "s", tree)] == sorted(tree)
    print("g377_restore demo OK")


if __name__ == "__main__":
    raise SystemExit(main())
