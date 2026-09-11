"""G407 eye cards and the delivered byte-domain digest inventory.

Cards are drawn exact-even over each measured class's full decision set, including
silence and failures. A retained source yields a native frame; a pruned source yields a
metadata card that names the absence instead of hiding it.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.g397_census import sha256_file
from scripts.platformkit.tracking.g407_tables import QUOTA

SELF_REFERENTIAL = ("q6_scan.json", "repeats.json", "SHA256SUMS")


def render_cards(rows: list[dict[str, Any]], out: Path, ffmpeg: str = "ffmpeg") -> list[dict]:
    """One exact-even card per class over its full decision set, silence and failures included."""
    renders = out / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(row["measured_class"], []).append(row)
    cards = []
    for name in sorted(groups):
        ordered = sorted(groups[name], key=lambda row: (row["competition"],
                                                        row["canonical_game"],
                                                        row["section_identity"]))
        count = min(QUOTA, len(ordered))
        picks = [ordered[0]] if count == 1 else [
            ordered[int(index * (len(ordered) - 1) / (count - 1) + .5)] for index in range(count)]
        for ordinal, row in enumerate(picks):
            stem = "%s__%02d__%s" % (name, ordinal, row["section_identity"])
            card, kind = renders / (stem + ".jpg"), "NATIVE_FRAME"
            source, start = row.get("receiver_path", ""), row.get("sealed_start_pts", "")
            if row["retained"] == 1 and source and Path(source).exists() and start != "":
                code = subprocess.run([ffmpeg, "-v", "error", "-ss", str(start), "-i", source,
                                       "-frames:v", "1", "-vf", "scale=320:-2", "-q:v", "8",
                                       "-y", str(card)], capture_output=True).returncode
                if code != 0 or not card.exists():
                    kind = "NATIVE_FRAME_FAILED"
            else:
                kind = "METADATA_CARD"
            if kind != "NATIVE_FRAME":
                card = renders / (stem + ".txt")
                card.write_text("\n".join("%s=%s" % (key, row.get(key, "")) for key in (
                    "section_identity", "measured_class", "retention_status", "status",
                    "requested_format_id", "itag_consistency", "source_height", "source_fps",
                    "decoded_frames", "evaluated_frames")) + "\n",
                    encoding="utf-8", newline="\n")
            cards.append({"measured_class": name, "ordinal": ordinal,
                          "section_identity": row["section_identity"], "card_kind": kind,
                          "card": card.name, "class_decision_set": len(ordered),
                          "cards_for_class": count})
    return cards


def sha256sums(out: Path) -> int:
    """Write the byte-domain digest inventory over every delivered file."""
    lines = ["# byte domain: sha256 of the exact delivered bytes of each path below, "
             "relative to this directory, LF newlines, no normalization applied"]
    for path in sorted(Path(out).rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            lines.append("%s  %s" % (sha256_file(path),
                                     path.relative_to(out).as_posix()))
    (out / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return len(lines) - 1


def scan_files(out: Path, extra: tuple[Path, ...] = ()) -> list[dict[str, str]]:
    """One scannable prose record per delivered text file, typed data and digests exempted.

    The three receipts that record this scan itself are skipped because they are written after
    it; they carry only digests, counts and pattern indices and are named in the scan output.
    """
    records = []
    for path in sorted(Path(out).rglob("*")) + list(extra):
        if not path.is_file() or path.suffix.lower() not in (".md", ".csv", ".json", ".txt"):
            continue
        if path.name in SELF_REFERENTIAL:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            records.append({"path": path.name, "text": "UNREADABLE_TEXT_ARTIFACT"})
            continue
        if path.suffix.lower() == ".csv":
            cells = [cell for row in text.splitlines() for cell in row.split(",")]
            text = " ".join(cell for cell in cells if not _typed(cell))
        elif path.suffix.lower() == ".json":
            text = " ".join(token for token in re.split(r"[\s,\[\]{}]+", text)
                            if not _typed(token.strip('"')))
        else:
            text = " ".join(token for token in text.split() if not _opaque(token))
        records.append({"path": path.name, "text": text})
    return records


def _opaque(token: str) -> bool:
    """True for an exact opaque identifier such as a 64-hex digest."""
    stripped = token.strip("`,.:")
    return len(stripped) == 64 and all(char in "0123456789abcdef" for char in stripped)


def _typed(token: str) -> bool:
    """True for appropriately typed numerical data or an opaque identifier."""
    token = token.strip().strip('"')
    if _opaque(token):
        return True
    try:
        float(token)
    except ValueError:
        return False
    return True
