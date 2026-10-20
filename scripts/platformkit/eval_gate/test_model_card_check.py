"""Per-file test for model_card_check (register S674).

python -m pytest scripts/platformkit/eval_gate/test_model_card_check.py -q
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.platformkit.eval_gate.model_card_check import check, main

REPO = Path(__file__).resolve().parents[3]
SECTIONS = ["Intended use", "Artifacts", "Owner and last verified"]


def _card(sha: str, drop: str | None = None) -> str:
    body = {s: f"## {s}\n\ntext\n" for s in SECTIONS}
    body["Artifacts"] = f"## Artifacts\n\n- art.bin sha256 {sha}\n"
    body["Owner and last verified"] = "## Owner and last verified\n\nLast verified: 2026-10-20\n"
    return "# Card\n\n" + "".join(v for k, v in body.items() if k != drop)


def _fixture(tmp: Path, *, missing_field=False, missing_card=False, wrong_sha=False,
             banned=False) -> Path:
    cards = tmp / "cards"
    cards.mkdir()
    (tmp / "art.bin").write_bytes(b"artifact bytes\n")
    sha = hashlib.sha256(b"artifact bytes\n").hexdigest()
    recorded = "0" * 64 if wrong_sha else sha
    entries = [{"id": "good", "card": "good.md", "as_of": "2026-10-20",
                "artifacts": [{"path": "art.bin", "sha256": recorded}]}]
    text = _card(recorded) + ("\nThis has an edge.\n" if banned else "")
    (cards / "good.md").write_text(text, encoding="utf-8")
    if missing_field:
        (cards / "thin.md").write_text(_card(sha, drop="Intended use"), encoding="utf-8")
        entries.append({"id": "thin", "card": "thin.md", "as_of": "2026-10-20", "artifacts": []})
    if missing_card:
        entries.append({"id": "ghost", "card": "ghost.md", "as_of": "not-a-date", "artifacts": []})
    (cards / "INDEX.json").write_text(json.dumps(
        {"required_sections": SECTIONS, "cards": entries}, indent=1), encoding="utf-8")
    return cards


def test_good_fixture_passes(tmp_path):
    assert check(_fixture(tmp_path), tmp_path) == []


def test_missing_field_fails(tmp_path):
    out = check(_fixture(tmp_path, missing_field=True), tmp_path)
    assert len(out) == 1 and "thin.md:1: missing section '## Intended use'" in out[0]


def test_index_to_missing_card_fails(tmp_path):
    out = check(_fixture(tmp_path, missing_card=True), tmp_path)
    assert any("card missing: ghost.md" in f for f in out)
    assert any("ghost.md: as_of is not a date" in f for f in out)
    assert all("INDEX.json:" in f for f in out)


def test_wrong_sha_fails(tmp_path):
    out = check(_fixture(tmp_path, wrong_sha=True), tmp_path)
    index = tmp_path / "cards" / "INDEX.json"
    line = next(i for i, s in enumerate(index.read_text().splitlines(), 1) if "art.bin" in s)
    assert out == [f"{index}:{line}: sha256 mismatch for art.bin"]


def test_banned_word_fails_with_line(tmp_path):
    out = check(_fixture(tmp_path, banned=True), tmp_path)
    assert len(out) == 1 and "good.md:" in out[0] and "banned edge language" in out[0]


def test_unlisted_card_fails(tmp_path):
    cards = _fixture(tmp_path)
    (cards / "stray.md").write_text("# stray\n", encoding="utf-8")
    assert check(cards, tmp_path) == [f"{cards / 'stray.md'}:1: card not listed in INDEX.json"]


def test_real_cards_pass(capsys):
    assert main(["--repo-root", str(REPO)]) == 0, capsys.readouterr().out


def _set_sha(cards: Path, value) -> Path:
    index = json.loads((cards / "INDEX.json").read_text(encoding="utf-8"))
    art = index["cards"][0]["artifacts"][0]
    if value == "DROP":
        del art["sha256"]
    else:
        art["sha256"] = value
    (cards / "INDEX.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    return cards


def test_missing_null_empty_sha_on_existing_artifact_fails(tmp_path):
    for i, value in enumerate(["DROP", None, "", "abc"]):
        root = tmp_path / str(i)
        root.mkdir()
        out = check(_set_sha(_fixture(root), value), root)
        assert any("sha256 missing or not 64 hex chars" in f for f in out), (value, out)


def test_absent_artifact_is_skipped_and_reported(tmp_path, capsys):
    cards = _set_sha(_fixture(tmp_path), None)
    (tmp_path / "art.bin").unlink()
    skipped: list[str] = []
    assert check(cards, tmp_path, skipped) == []
    assert len(skipped) == 1 and "absent on this box" in skipped[0]
    assert main(["--repo-root", str(tmp_path), "--cards-dir", str(cards)]) == 0
    assert "1 artifacts absent on this box" in capsys.readouterr().out
