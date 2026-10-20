"""scripts.platformkit.eval_gate.model_card_check -- model-card inventory gate (register S674).

Reads docs/evidence/model_cards/INDEX.json and fails (exit 1, one `file:line: message` per
finding) when:

  - an INDEX entry points to a card file that does not exist;
  - a card in the directory is not listed in INDEX.json;
  - a card lacks one of the INDEX `required_sections` (a `## <section>` heading);
  - a card has no `Last verified: YYYY-MM-DD` line, or an INDEX / artifact `as_of` is not a date;
  - an artifact's recorded sha256 is not printed in its card;
  - an artifact path exists on this box and its recorded sha256 is missing, null, empty,
    not 64 hex chars, or differs from the bytes (an absent path is skipped and listed as
    such in the output: data/ and engine files are not in every clone);
  - a banned word (edge / ROI / profit language) or a retracted figure appears in a card.

Calibration documentation only; no figure is computed here.
CLI:  python -m scripts.platformkit.eval_gate.model_card_check [--cards-dir DIR] [--repo-root .]
Test: python -m pytest scripts/platformkit/eval_gate/test_model_card_check.py -q
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

CARDS_REL = "docs/evidence/model_cards"
_HEX64 = re.compile(r"[0-9a-f]{64}")
_VERIFIED = re.compile(r"^Last verified:\s*(\S+)", re.M)
# Banned regardless of framing: cards describe calibration, never a wagering result.
BANNED = [
    (re.compile(r"\bedge\b", re.I), "edge language"),
    (re.compile(r"\bROI\b"), "ROI language"),
    (re.compile(r"\bprofit", re.I), "profit language"),
    (re.compile(r"\bBEATS_CLOSE\b"), "beats-the-close language"),
    # Retracted figures (docs/JOB_EVIDENCE_PACKET.md section 4): never printed on a card at all.
    (re.compile(r"(?<![\d.])(18\.38|0\.1191?|78\.11|8\.94|54\.57)(?!\d)"), "retracted figure"),
    (re.compile(r"\+54\s*%"), "retracted figure"),
]


def _is_date(value: object) -> bool:
    try:
        dt.date.fromisoformat(str(value))
        return True
    except ValueError:
        return False


def _sha_matches(path: Path, want: str) -> bool:
    """Raw bytes, or CRLF->LF bytes (the git-blob basis the PREREG seals pin on Windows)."""
    # ponytail: the LF fallback could in theory mask a binary file whose only change is
    # CRLF<->LF; add a per-artifact `basis` field if a binary artifact ever needs strictness.
    raw = path.read_bytes()
    return want in (hashlib.sha256(raw).hexdigest(),
                    hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest())


def check(cards_dir: Path, repo_root: Path, skipped: list[str] | None = None) -> list[str]:
    """Return every finding as `file:line: message`; empty means green.

    Artifacts absent on this box are appended to `skipped` (not findings)."""
    skipped = [] if skipped is None else skipped
    index_path = cards_dir / "INDEX.json"
    if not index_path.is_file():
        return [f"{index_path}:1: INDEX.json missing"]
    index = json.loads(index_path.read_text(encoding="utf-8"))
    idx_lines = index_path.read_text(encoding="utf-8").splitlines()

    def idx_line(token: str) -> int:
        return next((i for i, s in enumerate(idx_lines, 1) if token in s), 1)

    out: list[str] = []
    required = index.get("required_sections") or []
    if not required:
        out.append(f"{index_path}:1: required_sections missing or empty")
    listed = set()
    for entry in index.get("cards", []):
        card_rel = entry.get("card", "")
        listed.add(card_rel)
        card = cards_dir / card_rel
        if not _is_date(entry.get("as_of")):
            out.append(f"{index_path}:{idx_line(card_rel)}: {card_rel}: as_of is not a date")
        if not card.is_file():
            out.append(f"{index_path}:{idx_line(card_rel)}: card missing: {card_rel}")
            continue
        text = card.read_text(encoding="utf-8")
        lines = text.splitlines()
        headings = {s[3:].strip().lower() for s in lines if s.startswith("## ")}
        for sec in required:
            if sec.lower() not in headings:
                out.append(f"{card}:1: missing section '## {sec}'")
        m = _VERIFIED.search(text)
        if not m or not _is_date(m.group(1)):
            out.append(f"{card}:1: missing or invalid 'Last verified: YYYY-MM-DD' line")
        for art in entry.get("artifacts", []):
            path, want = art.get("path", ""), art.get("sha256")
            where = f"{index_path}:{idx_line(path)}"
            if "as_of" in art and not _is_date(art["as_of"]):
                out.append(f"{where}: {path}: as_of is not a date")
            target = repo_root / path
            if not target.is_file():
                skipped.append(f"{where}: {path}: absent on this box, sha256 not verified")
                continue
            if not isinstance(want, str) or not _HEX64.fullmatch(want):
                out.append(f"{where}: {path}: sha256 missing or not 64 hex chars")
                continue
            if want not in text:
                out.append(f"{card}:1: sha256 of {path} recorded in INDEX but not printed in card")
            if not _sha_matches(target, want):
                out.append(f"{where}: sha256 mismatch for {path}")
        for no, line in enumerate(lines, 1):
            for rx, why in BANNED:
                if rx.search(line):
                    out.append(f"{card}:{no}: banned {why}: {rx.search(line).group(0)!r}")
    for card in sorted(cards_dir.glob("*.md")):
        if card.name not in listed:
            out.append(f"{card}:1: card not listed in INDEX.json")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--cards-dir", type=Path, default=None)
    args = ap.parse_args(argv)
    cards_dir = args.cards_dir or args.repo_root / CARDS_REL
    skipped: list[str] = []
    findings = check(cards_dir, args.repo_root, skipped)
    for f in findings:
        print(f)
    for s in skipped:
        print(f"skipped: {s}")
    n_cards = len(list(cards_dir.glob("*.md"))) if cards_dir.is_dir() else 0
    print(f"model_card_check: {n_cards} cards, {len(findings)} findings, "
          f"{len(skipped)} artifacts absent on this box")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
