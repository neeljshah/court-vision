"""Per-file tests for ingame_sigma_serve.py.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_sigma_serve.py -q

Acceptance criteria (from BACKLOG.md ig-freshness-sigma-serve):
  (a) served sigma matches table value per (stat, bucket)
  (b) (stat, bucket) absent from table -> None (not fabricated/interpolated)
  (c) table missing -> graceful None, no exception

Additional correctness checks:
  - serve_sigma() always returns a dict, never raises
  - sigma_found matches whether calibrated_sigma is not None
  - all numeric fields have the right Python type
  - honesty field is ASCII and does not contain any retracted numbers or $ text
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict

import pytest

from scripts.platformkit.ingame.ingame_sigma_serve import (
    _HONESTY_NOTICE,
    get_sigma,
    load_sigma_table,
    serve_sigma,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_STATS = ["pts", "reb", "ast"]
_BUCKETS = [
    "02min(earlyQ1)",
    "04min(earlyQ1)",
    "06min(midQ1)",
    "12min(endQ1)",
    "18min(midQ2)",
    "24min(endQ2/half)",
    "30min(midQ3)",
    "36min(endQ3)",
    "42min(midQ4)",
    "44min(lateQ4)",
    "46min(lateQ4)",
]

# Minimal synthetic table -- mirrors schema of the real table
_SYNTHETIC_TABLE: Dict[str, Any] = {
    "sigma_table": {
        "pts": {
            "24min(endQ2/half)": {
                "elapsed_min": 24.0,
                "n": 36554,
                "bias": -0.0342,
                "mae": 3.3451,
                "std": 4.3853,
                "rob_sigma": 3.661,
                "calibrated_sigma": 3.8326,
                "p95_sigma": 8.8555,
                "coverage_at_1sig": 0.68,
                "coverage_at_2sig": 0.9209,
            },
            "36min(endQ3)": {
                "elapsed_min": 36.0,
                "n": 37082,
                "bias": -0.0362,
                "mae": 2.3611,
                "std": 3.1473,
                "rob_sigma": 2.2326,
                "calibrated_sigma": 2.5463,
                "p95_sigma": 6.4084,
                "coverage_at_1sig": 0.68,
                "coverage_at_2sig": 0.9126,
            },
        },
        "reb": {
            "24min(endQ2/half)": {
                "elapsed_min": 24.0,
                "n": 36554,
                "calibrated_sigma": 1.5671,
                "coverage_at_1sig": 0.68,
            },
        },
    },
    "bucket_order": _BUCKETS,
    "bucket_elapsed_min": {b: float(i * 2) for i, b in enumerate(_BUCKETS)},
    "generated_from": "test_fixture",
    "n_games": 1000,
    "n_rows": 50000,
    "sigma_definition": "p68 of abs(pred - truth)",
    "note": "synthetic fixture for tests",
}


def _write_table(d: Dict, tmpdir: str) -> str:
    path = os.path.join(tmpdir, "ingame_sigma_table.json")
    with open(path, "w", encoding="ascii") as fh:
        json.dump(d, fh)
    return path


# ---------------------------------------------------------------------------
# load_sigma_table
# ---------------------------------------------------------------------------

class TestLoadSigmaTable:
    def test_returns_none_when_file_absent(self, tmp_path):
        result = load_sigma_table(path=str(tmp_path / "nonexistent.json"))
        assert result is None

    def test_returns_none_on_invalid_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("NOT JSON {{{{", encoding="ascii")
        assert load_sigma_table(path=str(p)) is None

    def test_returns_none_on_json_array(self, tmp_path):
        p = tmp_path / "arr.json"
        p.write_text("[1, 2, 3]", encoding="ascii")
        assert load_sigma_table(path=str(p)) is None

    def test_loads_valid_table(self, tmp_path):
        path = _write_table(_SYNTHETIC_TABLE, str(tmp_path))
        result = load_sigma_table(path=path)
        assert isinstance(result, dict)
        assert "sigma_table" in result

    def test_loads_real_table_if_present(self):
        """If the real sigma table exists on disk, it should load cleanly."""
        repo = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )
        real_path = os.path.join(repo, "data", "models", "ingame_sigma_table.json")
        if not os.path.exists(real_path):
            pytest.skip("real ingame_sigma_table.json not present on this machine")
        tbl = load_sigma_table(path=real_path)
        assert tbl is not None
        assert "sigma_table" in tbl
        assert isinstance(tbl["sigma_table"], dict)


# ---------------------------------------------------------------------------
# get_sigma: acceptance (a) - served sigma matches table value
# ---------------------------------------------------------------------------

class TestGetSigmaMatchesTable:
    def test_pts_halfpoint_matches_expected(self, tmp_path):
        """Acceptance (a): get_sigma returns the calibrated_sigma from the table."""
        path = _write_table(_SYNTHETIC_TABLE, str(tmp_path))
        tbl = load_sigma_table(path=path)
        sigma = get_sigma("pts", "24min(endQ2/half)", table=tbl)
        assert sigma == pytest.approx(3.8326, rel=1e-4)

    def test_pts_endq3_matches_expected(self, tmp_path):
        path = _write_table(_SYNTHETIC_TABLE, str(tmp_path))
        tbl = load_sigma_table(path=path)
        sigma = get_sigma("pts", "36min(endQ3)", table=tbl)
        assert sigma == pytest.approx(2.5463, rel=1e-4)

    def test_reb_halfpoint_matches_expected(self, tmp_path):
        path = _write_table(_SYNTHETIC_TABLE, str(tmp_path))
        tbl = load_sigma_table(path=path)
        sigma = get_sigma("reb", "24min(endQ2/half)", table=tbl)
        assert sigma == pytest.approx(1.5671, rel=1e-4)

    def test_returns_float(self, tmp_path):
        path = _write_table(_SYNTHETIC_TABLE, str(tmp_path))
        tbl = load_sigma_table(path=path)
        sigma = get_sigma("pts", "24min(endQ2/half)", table=tbl)
        assert isinstance(sigma, float)


# ---------------------------------------------------------------------------
# get_sigma: acceptance (b) - absent (stat,bucket) -> None
# ---------------------------------------------------------------------------

class TestGetSigmaAbsentReturnsNone:
    def test_absent_stat_returns_none(self, tmp_path):
        """Acceptance (b): unknown stat -> None, not an interpolated value."""
        path = _write_table(_SYNTHETIC_TABLE, str(tmp_path))
        tbl = load_sigma_table(path=path)
        assert get_sigma("blk", "24min(endQ2/half)", table=tbl) is None

    def test_absent_bucket_returns_none(self, tmp_path):
        """Acceptance (b): known stat, unknown bucket -> None."""
        path = _write_table(_SYNTHETIC_TABLE, str(tmp_path))
        tbl = load_sigma_table(path=path)
        assert get_sigma("pts", "99min(fake)", table=tbl) is None

    def test_absent_stat_and_bucket_returns_none(self, tmp_path):
        path = _write_table(_SYNTHETIC_TABLE, str(tmp_path))
        tbl = load_sigma_table(path=path)
        assert get_sigma("stl", "99min(fake)", table=tbl) is None

    def test_ast_not_in_synthetic_table_returns_none(self, tmp_path):
        """ast is absent from our minimal synthetic table -- must not fabricate."""
        path = _write_table(_SYNTHETIC_TABLE, str(tmp_path))
        tbl = load_sigma_table(path=path)
        assert get_sigma("ast", "24min(endQ2/half)", table=tbl) is None

    def test_entry_without_calibrated_sigma_returns_none(self, tmp_path):
        """If entry exists but lacks calibrated_sigma key, return None."""
        bad_table = {
            "sigma_table": {
                "pts": {
                    "24min(endQ2/half)": {
                        "elapsed_min": 24.0,
                        "n": 1000,
                        # calibrated_sigma intentionally absent
                    }
                }
            }
        }
        path = _write_table(bad_table, str(tmp_path))
        tbl = load_sigma_table(path=path)
        assert get_sigma("pts", "24min(endQ2/half)", table=tbl) is None


# ---------------------------------------------------------------------------
# get_sigma: acceptance (c) - table missing -> graceful None, no exception
# ---------------------------------------------------------------------------

class TestGetSigmaTableMissing:
    def test_missing_file_returns_none_not_exception(self, tmp_path):
        """Acceptance (c): table file absent -> None, no exception raised."""
        result = get_sigma("pts", "24min(endQ2/half)",
                           path=str(tmp_path / "does_not_exist.json"))
        assert result is None

    def test_corrupt_file_returns_none_not_exception(self, tmp_path):
        p = tmp_path / "corrupt.json"
        p.write_bytes(b"\xff\xfe bad binary data")
        result = get_sigma("pts", "36min(endQ3)", path=str(p))
        assert result is None

    def test_empty_file_returns_none_not_exception(self, tmp_path):
        p = tmp_path / "empty.json"
        p.write_text("", encoding="ascii")
        result = get_sigma("pts", "36min(endQ3)", path=str(p))
        assert result is None


# ---------------------------------------------------------------------------
# serve_sigma: correctness + honesty checks
# ---------------------------------------------------------------------------

class TestServeSigma:
    def test_returns_dict_always(self, tmp_path):
        """serve_sigma never raises; always returns a dict."""
        path = _write_table(_SYNTHETIC_TABLE, str(tmp_path))
        tbl = load_sigma_table(path=path)
        result = serve_sigma("pts", "24min(endQ2/half)", table=tbl)
        assert isinstance(result, dict)

    def test_sigma_found_true_when_present(self, tmp_path):
        path = _write_table(_SYNTHETIC_TABLE, str(tmp_path))
        tbl = load_sigma_table(path=path)
        result = serve_sigma("pts", "24min(endQ2/half)", table=tbl)
        assert result["sigma_found"] is True
        assert result["calibrated_sigma"] == pytest.approx(3.8326, rel=1e-4)

    def test_sigma_found_false_when_stat_absent(self, tmp_path):
        path = _write_table(_SYNTHETIC_TABLE, str(tmp_path))
        tbl = load_sigma_table(path=path)
        result = serve_sigma("blk", "24min(endQ2/half)", table=tbl)
        assert result["sigma_found"] is False
        assert result["calibrated_sigma"] is None

    def test_sigma_found_false_when_bucket_absent(self, tmp_path):
        path = _write_table(_SYNTHETIC_TABLE, str(tmp_path))
        tbl = load_sigma_table(path=path)
        result = serve_sigma("pts", "99min(fake)", table=tbl)
        assert result["sigma_found"] is False
        assert result["calibrated_sigma"] is None

    def test_sigma_found_false_when_table_missing(self, tmp_path):
        result = serve_sigma("pts", "24min(endQ2/half)",
                             path=str(tmp_path / "no_file.json"))
        assert result["sigma_found"] is False
        assert result["calibrated_sigma"] is None

    def test_stat_and_bucket_echoed_in_result(self, tmp_path):
        path = _write_table(_SYNTHETIC_TABLE, str(tmp_path))
        tbl = load_sigma_table(path=path)
        result = serve_sigma("reb", "24min(endQ2/half)", table=tbl)
        assert result["stat"] == "reb"
        assert result["bucket"] == "24min(endQ2/half)"

    def test_elapsed_min_populated_when_present(self, tmp_path):
        path = _write_table(_SYNTHETIC_TABLE, str(tmp_path))
        tbl = load_sigma_table(path=path)
        result = serve_sigma("pts", "36min(endQ3)", table=tbl)
        assert result["elapsed_min"] == pytest.approx(36.0, rel=1e-6)

    def test_n_populated_when_present(self, tmp_path):
        path = _write_table(_SYNTHETIC_TABLE, str(tmp_path))
        tbl = load_sigma_table(path=path)
        result = serve_sigma("pts", "36min(endQ3)", table=tbl)
        assert result["n"] == 37082
        assert isinstance(result["n"], int)

    def test_coverage_at_1sig_populated_when_present(self, tmp_path):
        path = _write_table(_SYNTHETIC_TABLE, str(tmp_path))
        tbl = load_sigma_table(path=path)
        result = serve_sigma("pts", "24min(endQ2/half)", table=tbl)
        assert result["coverage_at_1sig"] == pytest.approx(0.68, rel=1e-6)

    def test_honesty_field_is_ascii(self, tmp_path):
        path = _write_table(_SYNTHETIC_TABLE, str(tmp_path))
        tbl = load_sigma_table(path=path)
        result = serve_sigma("pts", "24min(endQ2/half)", table=tbl)
        h = result["honesty"]
        assert isinstance(h, str)
        h.encode("ascii")  # raises UnicodeEncodeError if not ASCII

    def test_honesty_does_not_contain_dollar_sign(self, tmp_path):
        path = _write_table(_SYNTHETIC_TABLE, str(tmp_path))
        tbl = load_sigma_table(path=path)
        result = serve_sigma("pts", "24min(endQ2/half)", table=tbl)
        h = result["honesty"]
        assert "$" not in h
        assert "roi" not in h.lower()
        # "profit" is allowed only inside a "not a profit" disclaimer, never as a claim
        if "profit" in h.lower():
            assert "not" in h.lower(), "honesty field mentions profit without a negation"

    def test_serve_sigma_does_not_raise_on_missing_table(self, tmp_path):
        """serve_sigma must not raise even when table file is absent."""
        try:
            serve_sigma("pts", "24min(endQ2/half)",
                        path=str(tmp_path / "missing.json"))
        except Exception as exc:
            pytest.fail(f"serve_sigma raised unexpectedly: {exc}")

    def test_elapsed_min_is_none_when_absent(self, tmp_path):
        minimal = {
            "sigma_table": {
                "pts": {
                    "24min(endQ2/half)": {"calibrated_sigma": 3.5}
                }
            }
        }
        path = _write_table(minimal, str(tmp_path))
        tbl = load_sigma_table(path=path)
        result = serve_sigma("pts", "24min(endQ2/half)", table=tbl)
        assert result["elapsed_min"] is None
        assert result["n"] is None
        assert result["coverage_at_1sig"] is None
        assert result["calibrated_sigma"] == pytest.approx(3.5)

    def test_real_table_all_known_keys_match(self):
        """Spot-check a handful of (stat,bucket) entries against the real table."""
        repo = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )
        real_path = os.path.join(repo, "data", "models", "ingame_sigma_table.json")
        if not os.path.exists(real_path):
            pytest.skip("real ingame_sigma_table.json not present on this machine")
        tbl = load_sigma_table(path=real_path)
        assert tbl is not None
        sigma_sec = tbl["sigma_table"]
        spot_checks = [
            ("pts", "24min(endQ2/half)"),
            ("pts", "36min(endQ3)"),
            ("reb", "24min(endQ2/half)"),
            ("ast", "12min(endQ1)"),
        ]
        for stat, bucket in spot_checks:
            direct = sigma_sec.get(stat, {}).get(bucket, {}).get("calibrated_sigma")
            via_api = get_sigma(stat, bucket, table=tbl)
            if direct is None:
                assert via_api is None, f"Expected None for ({stat},{bucket})"
            else:
                assert via_api == pytest.approx(float(direct), rel=1e-5), (
                    f"Mismatch for ({stat},{bucket}): api={via_api} table={direct}"
                )

    def test_sigma_found_consistent_with_calibrated_sigma(self, tmp_path):
        """sigma_found must be True iff calibrated_sigma is not None."""
        path = _write_table(_SYNTHETIC_TABLE, str(tmp_path))
        tbl = load_sigma_table(path=path)
        for stat in ["pts", "reb", "blk", "ast"]:
            for bucket in ["24min(endQ2/half)", "99min(fake)"]:
                result = serve_sigma(stat, bucket, table=tbl)
                assert result["sigma_found"] == (result["calibrated_sigma"] is not None), (
                    f"sigma_found/calibrated_sigma inconsistency for ({stat},{bucket})"
                )
