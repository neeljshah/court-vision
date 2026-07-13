"""Per-file tests for backfill_knowledge.py.

cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/knowledge/test_backfill_knowledge.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.knowledge import backfill_knowledge as bk

_FIXTURE_MD = """# Fixture Mechanism Ledger

## Pre-adjudicated (do NOT re-test)

### 1. Fixture rest-day penalty
- **claim**: teams on zero rest underperform.
- **status**: CONFIRMED
- **measured LOCAL magnitude**: effect -1.73, p=0.0056, n=4,732.
- **artifact link**: `some/path.py::rest_penalty` (commits 132179ca/bcaa6d7a).

## Validated 2026-07-09 (fixture batch)

### 2. Fixture persistence check
- **claim**: fixture stat is stable split-half.
- **status**: REJECTED (NULL_LOCAL) -- no relationship found.
- **measured LOCAL magnitude**: r=0.681, p=3.5e-5, n=30 teams.

### 3. Fixture blocked mechanism
- **claim**: fixture ingredient does not exist locally.
- **status**: NOT_TESTABLE -- no column on disk.
"""

_FIXTURE_LEDGER = [
    {
        "sport": "fixture_sport", "template_id": "fx_template",
        "attr_a": "attr_a", "attr_b": "attr_b", "outcome": "efg",
        "candidate_id": "fx_template::attr_a__x__attr_b",
        "corpus": "fixture_corpus", "effect": 0.0123, "n": 500,
        "verdict": "NULL", "computed_at": "2026-01-01T00:00:00+00:00",
    },
    {
        "sport": "other_sport", "template_id": "other_template",
        "attr_a": "x", "attr_b": "y", "outcome": "z",
        "candidate_id": "other_template::x__x__y",
        "corpus": "other_corpus", "effect": None, "n": None,
        "verdict": "NOT_TESTABLE", "computed_at": "2026-01-02T00:00:00+00:00",
    },
]


def test_parse_mechanisms_labels_verbatim_no_invented_numerics(tmp_path):
    md_path = tmp_path / "mechanisms.md"
    md_path.write_text(_FIXTURE_MD, encoding="ascii")
    rows = bk.parse_mechanisms(md_path, "fixture_sport")
    assert len(rows) == 3

    r1 = rows[0]
    assert r1["source"] == "mechanisms.md#1"
    assert r1["claim"] == "teams on zero rest underperform."
    assert r1["label"] == "CONFIRMED"  # verbatim, not upgraded/paraphrased
    assert r1["effect"] == -1.73
    assert r1["n"] == 4732
    assert r1["lineage"] == ["132179ca", "bcaa6d7a"]
    assert r1["last_validated"] is None  # pre-adjudicated section has no date

    r2 = rows[1]
    assert r2["label"] == "REJECTED (NULL_LOCAL) -- no relationship found."
    assert r2["effect"] == 0.681  # r= fallback used since no eff/effect present
    assert r2["n"] == 30
    assert r2["last_validated"] == "2026-07-09"

    r3 = rows[2]
    assert r3["label"] == "NOT_TESTABLE -- no column on disk."
    assert r3["effect"] is None  # never invented
    assert r3["n"] is None


def test_parse_mechanisms_heading_label_fallback(tmp_path):
    md_path = tmp_path / "mechanisms.md"
    md_path.write_text(
        "## Validated 2026-07-11 (fixture)\n\n"
        "### 42. Fixture heading-labelled mechanism -- CONFIRMED_LOCAL "
        "(2026-07-11 update, was PROVISIONAL)\n"
        "- **claim**: fixture claim with the label in the heading only.\n"
        "- **measured LOCAL magnitude**: effect 0.5, n=100.\n",
        encoding="ascii")
    rows = bk.parse_mechanisms(md_path, "fixture_sport")
    assert len(rows) == 1
    r = rows[0]
    assert r["label"] == "CONFIRMED_LOCAL"  # verbatim token, parenthetical excluded
    assert r["source"] == "mechanisms.md#42"
    assert r["effect"] == 0.5
    assert r["n"] == 100
    # status line still wins when both forms are present (fallback fires only
    # when no status line exists).
    md_path.write_text(
        "### 1. Fixture -- LOCAL NULL\n"
        "- **status**: REJECTED (NULL_LOCAL) -- fixture.\n",
        encoding="ascii")
    rows = bk.parse_mechanisms(md_path, "fixture_sport")
    assert rows[0]["label"] == "REJECTED (NULL_LOCAL) -- fixture."


def test_parse_mechanisms_missing_file_returns_empty(tmp_path):
    assert bk.parse_mechanisms(tmp_path / "absent.md", "fixture_sport") == []


def test_ledger_row_mapping(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    ledger_path.write_text(
        "\n".join(json.dumps(r) for r in _FIXTURE_LEDGER), encoding="ascii")
    rows = bk.build_sport("fixture_sport", ledger_path=ledger_path)
    # only mechanisms.md rows for this sport (no real mechanisms.md on disk
    # for "fixture_sport") plus the one matching ledger row.
    ledger_rows = [r for r in rows if r["source"].startswith("factory_ledger:")]
    assert len(ledger_rows) == 1
    row = ledger_rows[0]
    assert row["label"] == "NULL"  # verbatim verdict, never upgraded
    assert row["effect"] == 0.0123
    assert row["n"] == 500
    assert row["corpora"] == ["fixture_corpus"]
    assert row["mechanism"] == "fx_template"
    assert row["source"] == "factory_ledger:fx_template/fx_template::attr_a__x__attr_b"
    assert row["ci"] is None
    assert row["lineage"] == []

    # "other_sport" row is excluded when building "fixture_sport"
    assert not any(r["sport"] == "other_sport" for r in rows)


def test_ledger_row_missing_numerics_stay_null():
    row = bk.ledger_row(_FIXTURE_LEDGER[1])
    assert row["effect"] is None
    assert row["n"] is None
    assert row["label"] == "NOT_TESTABLE"


def test_idempotent_rewrite_same_bytes(tmp_path, monkeypatch):
    md_dir = tmp_path / "domains" / "fixture_sport" / "knowledge"
    md_dir.mkdir(parents=True)
    (md_dir / "mechanisms.md").write_text(_FIXTURE_MD, encoding="ascii")
    ledger_path = tmp_path / "ledger.jsonl"
    ledger_path.write_text(
        "\n".join(json.dumps(r) for r in _FIXTURE_LEDGER), encoding="ascii")

    monkeypatch.setattr(bk, "REPO", tmp_path)
    bk.write_sport("fixture_sport", ledger_path=ledger_path)
    out_path = md_dir / "knowledge.jsonl"
    first_bytes = out_path.read_bytes()

    bk.write_sport("fixture_sport", ledger_path=ledger_path)
    second_bytes = out_path.read_bytes()
    assert first_bytes == second_bytes

    lines = [l for l in first_bytes.decode("ascii").split("\n") if l]
    assert len(lines) == 4  # 3 mechanisms.md rows + 1 matching ledger row
    for line in lines:
        row = json.loads(line)
        assert set(row.keys()) == {
            "claim", "mechanism", "sport", "effect", "ci", "n",
            "corpora", "label", "lineage", "last_validated", "source"}


def test_real_sport_mechanisms_row_counts_positive():
    for sport in bk.SPORTS:
        mech_path = bk.REPO / "domains" / sport / "knowledge" / "mechanisms.md"
        assert mech_path.exists(), sport
        rows = bk.parse_mechanisms(mech_path, sport)
        assert len(rows) > 0, sport
