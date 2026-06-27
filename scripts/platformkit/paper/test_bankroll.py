"""Per-file test: scripts.platformkit.paper.bankroll (units-only bankroll model)."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.paper import bankroll as bk


def test_default_config_units_only(tmp_path: Path) -> None:
    cfg = bk.default_config(100.0)
    assert cfg["start_units"] == 100.0
    assert cfg["current_units"] == 100.0
    assert cfg["edge_claimed"] is False
    # No banned $ keys anywhere.
    for k in ("pnl", "roi", "profit", "dollars", "bankroll", "stake"):
        assert k not in cfg


def test_init_and_read_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "paper_bankroll.json"
    written = bk.init_bankroll(100.0, p)
    assert p.exists()
    assert written["start_units"] == 100.0
    back = bk.read_config(p)
    assert back["start_units"] == 100.0
    assert back["current_units"] == 100.0


def test_read_missing_file_returns_default(tmp_path: Path) -> None:
    p = tmp_path / "nope.json"
    cfg = bk.read_config(p)
    assert cfg["start_units"] == bk.DEFAULT_START_UNITS


def test_apply_settled_accumulates_unit_results(tmp_path: Path) -> None:
    p = tmp_path / "bk.json"
    bk.init_bankroll(100.0, p)
    settled = [
        {"unit_result": 1.5, "outcome": "win"},
        {"unit_result": -1.0, "outcome": "loss"},
        {"unit_result": 0.0, "outcome": "push"},
        {"unit_result": None, "outcome": "void"},  # skipped, not coerced
    ]
    cfg = bk.apply_settled(settled, path=p)
    assert cfg["current_units"] == 100.5
    assert cfg["net_units"] == 0.5
    # Idempotent: re-apply same set recomputes from start, never doubles.
    cfg2 = bk.apply_settled(settled, path=p)
    assert cfg2["current_units"] == 100.5


def test_apply_settled_no_persist(tmp_path: Path) -> None:
    p = tmp_path / "bk.json"
    bk.init_bankroll(100.0, p)
    cfg = bk.apply_settled([{"unit_result": 2.0}], path=p, persist=False)
    assert cfg["current_units"] == 102.0
    # On-disk file unchanged because persist=False.
    assert bk.read_config(p)["current_units"] == 100.0


def test_write_config_strips_banned_keys(tmp_path: Path) -> None:
    p = tmp_path / "bk.json"
    dirty = bk.default_config(100.0)
    dirty["pnl"] = 25.34
    dirty["profit"] = 10.0
    dirty["bankroll"] = 999.0
    bk.write_config(dirty, p)
    raw = json.loads(p.read_text(encoding="utf-8"))
    for k in ("pnl", "profit", "bankroll", "roi", "dollars"):
        assert k not in raw


def test_read_strips_stale_dollar_field(tmp_path: Path) -> None:
    p = tmp_path / "bk.json"
    p.write_text(json.dumps(
        {"start_units": 100.0, "current_units": 105.0, "pnl": 5.0}),
        encoding="utf-8")
    cfg = bk.read_config(p)
    assert "pnl" not in cfg
    assert cfg["current_units"] == 105.0
