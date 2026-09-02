"""S13: the FWER charge ledger's five optional fields are ADDITIVE.

Every case runs on a COPY of the real ledger placed under tmp_path. The real file
data/cache/eval_gate/backtest_fwer.jsonl is read once per case and never opened for
writing, so this file charges nothing to the cumulative-K audit trail.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.platformkit.eval_gate import backtest_runner
from scripts.platformkit.eval_gate.ledger import FWER_OPTIONAL_FIELDS, load_fwer

REAL_LEDGER = (Path(__file__).resolve().parents[3] / "data" / "cache" / "eval_gate"
               / "backtest_fwer.jsonl")


@pytest.fixture()
def ledger_copy(tmp_path: Path) -> Path:
    """A per-test scratch copy of the real ledger; the original is never the write target."""
    if not REAL_LEDGER.is_file():
        pytest.skip("real ledger absent (data/ is gitignored): %s" % REAL_LEDGER)
    dest = tmp_path / "backtest_fwer.jsonl"
    shutil.copyfile(REAL_LEDGER, dest)
    return dest


def _raw(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="ascii").splitlines() if line.strip()]


def test_real_rows_load_unchanged_with_optional_fields_none(ledger_copy: Path) -> None:
    """(1) Every row on disk loads (>= 13 -- the ledger only grows); k_cumulative is exactly the on-disk sequence."""
    on_disk = _raw(ledger_copy)
    rows = load_fwer(ledger_copy)
    assert len(rows) == len(on_disk) >= 13
    assert [r["k_cumulative"] for r in rows] == [r["k_cumulative"] for r in on_disk]
    for loaded, raw in zip(rows, on_disk):
        # the loader adds the five keys as None and changes nothing else
        assert all(loaded[field] is None for field in FWER_OPTIONAL_FIELDS)
        assert {k: v for k, v in loaded.items() if k not in FWER_OPTIONAL_FIELDS} == raw


def test_legacy_charge_writes_no_new_keys(ledger_copy: Path) -> None:
    """(2) A pre-S13 call site charges row 14 with the old six keys and nothing else."""
    before = _raw(ledger_copy)
    prior = max(r["k_cumulative"] for r in before)
    row = backtest_runner._charge_ledger(ledger_copy, "pkg.mod:pred", "nba", "2025-10-21", "2026-04-12")
    assert row["k_cumulative"] == prior + 1
    assert [f for f in FWER_OPTIONAL_FIELDS if f in row] == []
    assert set(_raw(ledger_copy)[-1]) == {"at", "predictor", "sport", "start", "end", "k_cumulative"}
    rows = load_fwer(ledger_copy)
    assert len(rows) == len(before) + 1 and all(rows[-1][f] is None for f in FWER_OPTIONAL_FIELDS)


def test_k_family_counts_within_a_family_and_k_cumulative_stays_monotone(ledger_copy: Path) -> None:
    """(3) Two rows of f1 and one of f2 -> k_family 1, 2, 1; global K keeps climbing by one."""
    charged = [backtest_runner._charge_ledger(ledger_copy, "pkg.mod:p%d" % i, "nba",
                                              "2025-10-21", "2026-04-12", family=fam)
               for i, fam in enumerate(("f1", "f1", "f2"))]
    assert [r["k_family"] for r in charged] == [1, 2, 1]
    ks = [r["k_cumulative"] for r in load_fwer(ledger_copy)]
    assert ks == sorted(ks) == list(range(1, len(ks) + 1))  # ledger only grows; the on-disk count moves


def test_five_optional_fields_round_trip_through_the_loader(ledger_copy: Path) -> None:
    """(4) family / k_family / hypothesis_hash / tier / prereg_sha256 survive write -> load."""
    written = backtest_runner._charge_ledger(
        ledger_copy, "pkg.mod:pred", "mlb", "2026-06-28", "2026-07-12",
        family="rest_family", hypothesis_hash="a" * 64, tier="T2", prereg_sha256="b" * 64)
    loaded = load_fwer(ledger_copy)[-1]
    assert loaded["family"] == "rest_family" and loaded["k_family"] == 1
    assert loaded["hypothesis_hash"] == "a" * 64
    assert loaded["tier"] == "T2" and loaded["prereg_sha256"] == "b" * 64
    assert all(loaded[f] == written[f] for f in FWER_OPTIONAL_FIELDS)


def test_unknown_tier_raises_before_anything_is_written(ledger_copy: Path) -> None:
    """(5) tier is T2|T3 only; a rejected charge must not leave a row behind."""
    before = ledger_copy.read_bytes()
    with pytest.raises(ValueError):
        backtest_runner._charge_ledger(ledger_copy, "pkg.mod:pred", "nba",
                                       "2025-10-21", "2026-04-12", tier="T1")
    assert ledger_copy.read_bytes() == before


def test_next_k_family_counts_aliased_rows_s89():
    """S89: the write path counts aliased in-game arm rows (rows 15/16 -> ingame_arms_mlb = 3 next)."""
    import json
    from pathlib import Path
    from scripts.platformkit.eval_gate.ledger import next_k_family
    path = Path("data/cache/eval_gate/backtest_fwer.jsonl")
    if not path.exists():
        return
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert next_k_family(rows, "ingame_arms_mlb") == 3
    assert next_k_family(rows, "soccer_gate") == 2
    assert next_k_family(rows, None) is None
