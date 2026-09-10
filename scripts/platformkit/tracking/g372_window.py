"""G372 phase-A sealed window: attempt set, even k-th sample, failure-retaining collection.

Every rule here is fixed by `g372_prereg_amendment_A2_2026-09-10.md`
(SEAL 4dd969f54ba526f71348da37ffeb7cb462f3dd977984c07ed36543b114bc5131): the
attempt set is EVERY unique game_id in ledger rows 856+ of the archived
snapshot, not only the sections whose bytes survived; the sample is all of them
when n <= 40 and otherwise every k-th index from a digest-derived start; and an
attempt whose bytes are gone keeps its manifest row with a status so it stays in
the denominator (contract B1/B7).
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("/workspace/data")
LOCATIONS = ("footage_bridge", "footage_corpus", "footage_quarantine")
FRESH_FROM_ROW = 856
SAMPLE_TARGET = 40
UNKNOWN = "UNKNOWN"
SAMPLE_FIELDS = ("index", "game_id", "sport", "first_claim_utc")
MANIFEST_FIELDS = ("index", "game_id", "sport", "first_claim_utc", "location", "src_path",
                   "src_bytes", "copy_status", "reason", "scratch_path", "scratch_bytes")


def utc(stamp: float) -> str:
    """Render a ledger epoch as the stable UTC string used across this lane."""
    return datetime.fromtimestamp(float(stamp), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ascii_only(text: str, limit: int = 120) -> str:
    """Keep diagnostics printable on the cp1252 console and in ASCII CSVs."""
    return text.encode("ascii", "replace").decode("ascii")[:limit]


def snapshot_sha256(path: Path) -> str:
    """Digest the archived ledger snapshot; this also seeds the sample start."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def grouped_window(snapshot: Path) -> dict:
    """Group the sealed window's rows by game_id, each group in ledger order."""
    lines = [s for s in snapshot.read_text(encoding="utf-8").splitlines() if s.strip()]
    grouped: dict = {}
    for line in lines[FRESH_FROM_ROW - 1:]:
        row = json.loads(line)
        grouped.setdefault(row.get("game_id"), []).append(row)
    for entries in grouped.values():
        entries.sort(key=lambda item: float(item.get("finished_at") or 0))
    return grouped


def attempts(snapshot: Path) -> list:
    """Order every unique game_id in the window and give it its sealed index."""
    items = []
    for game_id, entries in grouped_window(snapshot).items():
        first = entries[0]
        claim = float(first.get("finished_at") or 0) - float(first.get("seconds") or 0)
        items.append({"game_id": game_id, "sport": first.get("sport", ""),
                      "first_claim_utc": utc(claim),
                      "source_variants": first.get("source_variants") or []})
    items.sort(key=lambda item: (item["first_claim_utc"], item["game_id"]))
    for index, item in enumerate(items):
        item["index"] = index
    return items


def even_sample(n: int, seed_hex: str, target: int = SAMPLE_TARGET) -> tuple:
    """Return (k, start, indices) spread over the WHOLE window, never a head slice.

    n <= target takes every attempt. Otherwise k = floor(n / target) and the
    indices are start, start+k, start+2k, ... with the start taken from the
    sealed snapshot digest, so it cannot be re-drawn after seeing a result.
    """
    if n <= 0:
        return 0, 0, []
    if n <= target:
        return 1, 0, list(range(n))
    k = n // target
    start = int(seed_hex[:8], 16) % k
    return k, start, list(range(start, n, k))


def locate(sport: str, game_id: str, variants: list) -> tuple:
    """Find a section's bytes under any footage location, probing .failed renames."""
    names = ["%s__%s.mp4" % (sport, game_id)] + [str(item) for item in variants or []]
    for folder in LOCATIONS:
        for name in names:
            for candidate in ((DATA / folder / name), (DATA / folder / (name + ".failed"))):
                if candidate.is_file():
                    return folder.split("_")[-1].upper(), str(candidate)
    return "GONE", ""


def collect(sampled: list, scratch: Path, cap_bytes: int) -> list:
    """Freeze one scratch copy per sampled attempt; a failure keeps its row."""
    scratch.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in sampled:
        location, src = locate(item["sport"], item["game_id"], item["source_variants"])
        row = {key: item[key] for key in SAMPLE_FIELDS}
        row.update(location=location, src_path=src, src_bytes=UNKNOWN,
                   copy_status="BYTES_GONE", reason="no file under " + "|".join(LOCATIONS),
                   scratch_path="", scratch_bytes=UNKNOWN)
        if src:
            row.update(copy_status="OK", reason="")
            source, dest = Path(src), scratch / Path(src).name
            try:
                row["src_bytes"] = size = source.stat().st_size
                if size > cap_bytes:
                    row.update(copy_status="SKIP_OVER_CAP", reason="over per-file cap")
                else:
                    partial = dest.with_suffix(".part")
                    shutil.copyfile(source, partial)
                    partial.replace(dest)
                    row.update(scratch_path=str(dest), scratch_bytes=dest.stat().st_size)
            except OSError as exc:
                row.update(copy_status="ERROR_" + type(exc).__name__,
                           reason=ascii_only(str(exc)), scratch_path="", scratch_bytes=UNKNOWN)
        rows.append(row)
    return rows
