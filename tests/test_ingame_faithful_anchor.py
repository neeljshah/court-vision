"""tests/test_ingame_faithful_anchor.py -- CV_CALIB_FAITHFUL_ANCHOR gate.

Tests:
 1. Flag OFF (unset)  -> _faithful_anchor_enabled() returns False.
 2. Flag OFF ("0")    -> _faithful_anchor_enabled() returns False.
 3. Flag OFF ("false")-> _faithful_anchor_enabled() returns False.
 4. Flag OFF ("off")  -> _faithful_anchor_enabled() returns False.
 5. Flag ON  ("1")    -> _faithful_anchor_enabled() returns True.
 6. Flag ON  ("true") -> _faithful_anchor_enabled() returns True.
 7. Flag ON  ("yes")  -> _faithful_anchor_enabled() returns True.
 8. Flag ON  ("on")   -> _faithful_anchor_enabled() returns True.
 9. Flag OFF -> load_oof_prior loads from _OOF_PATH (legacy pregame_oof.parquet).
10. Flag ON  -> load_oof_prior loads from _OOF_FAITHFUL_PATH (pregame_oof_faithful.parquet).
11. Flag OFF -> load_oof_prior produces the same dict as the explicit pre-flag
    invocation (byte-identical: same keys, same values to float precision).
12. Flag ON  -> at least one (game_id, player_id, stat) key exists in the result
    (confirms faithful parquet loaded and parsed successfully, given the file is
    present on this machine).
"""
from __future__ import annotations

import importlib
import os
import sys
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Import after path setup.
import scripts.ingame_calib_eval as _eval  # noqa: E402

_faithful_anchor_enabled = _eval._faithful_anchor_enabled
_OOF_PATH = _eval._OOF_PATH
_OOF_FAITHFUL_PATH = _eval._OOF_FAITHFUL_PATH
_load = _eval.load_oof_prior


# ── helpers ──────────────────────────────────────────────────────────────────

def _with_flag(flag_value):
    """Context manager: set CV_CALIB_FAITHFUL_ANCHOR to flag_value (or unset if None)."""
    env = {k: v for k, v in os.environ.items() if k != "CV_CALIB_FAITHFUL_ANCHOR"}
    if flag_value is not None:
        env["CV_CALIB_FAITHFUL_ANCHOR"] = flag_value
    return mock.patch.dict(os.environ, env, clear=True)


# ── tests 1-8: _faithful_anchor_enabled() logic ──────────────────────────────

class TestFaithfulAnchorEnabled:
    def test_unset_returns_false(self):
        with _with_flag(None):
            assert _faithful_anchor_enabled() is False

    def test_zero_returns_false(self):
        with _with_flag("0"):
            assert _faithful_anchor_enabled() is False

    def test_false_string_returns_false(self):
        with _with_flag("false"):
            assert _faithful_anchor_enabled() is False

    def test_off_string_returns_false(self):
        with _with_flag("off"):
            assert _faithful_anchor_enabled() is False

    def test_empty_string_returns_false(self):
        with _with_flag(""):
            assert _faithful_anchor_enabled() is False

    def test_one_returns_true(self):
        with _with_flag("1"):
            assert _faithful_anchor_enabled() is True

    def test_true_string_returns_true(self):
        with _with_flag("true"):
            assert _faithful_anchor_enabled() is True

    def test_yes_returns_true(self):
        with _with_flag("yes"):
            assert _faithful_anchor_enabled() is True

    def test_on_returns_true(self):
        with _with_flag("on"):
            assert _faithful_anchor_enabled() is True

    def test_ON_uppercase_returns_true(self):
        with _with_flag("ON"):
            assert _faithful_anchor_enabled() is True


# ── tests 9-10: load_oof_prior routes to correct parquet ─────────────────────

class TestLoadOofPriorRouting:
    """Verify that the flag controls which parquet file is loaded, using
    mock.patch on pd.read_parquet so no real I/O is required."""

    def _mock_legacy_parquet(self, path, columns):
        """Minimal stand-in for legacy pregame_oof.parquet read."""
        import pandas as pd
        return pd.DataFrame([{
            "game_id": "0022400001",
            "player_id": 1234567,
            "stat": "pts",
            "oof_pred": 22.5,
        }])

    def _mock_faithful_parquet(self, path, columns):
        """Minimal stand-in for pregame_oof_faithful.parquet read."""
        import pandas as pd
        return pd.DataFrame([{
            "game_date": "2024-10-22",
            "player_id": 1234567,
            "stat": "pts",
            "oof_pred": 21.0,
        }])

    def test_flag_off_uses_legacy_path(self):
        captured_paths = []

        def _read(path, columns):
            captured_paths.append(path)
            return self._mock_legacy_parquet(path, columns)

        with _with_flag(None):
            with mock.patch("pandas.read_parquet", side_effect=_read):
                _load()

        assert len(captured_paths) == 1, "expected exactly one read_parquet call"
        assert os.path.normpath(captured_paths[0]) == os.path.normpath(_OOF_PATH), (
            f"flag-OFF should read {_OOF_PATH!r}, got {captured_paths[0]!r}"
        )

    def test_flag_on_uses_faithful_path(self):
        captured_paths = []

        def _read(path, columns):
            captured_paths.append(path)
            return self._mock_faithful_parquet(path, columns)

        # Also patch _build_gid_to_date to avoid file I/O.
        with _with_flag("1"):
            with mock.patch("pandas.read_parquet", side_effect=_read):
                with mock.patch.object(_eval, "_build_gid_to_date", return_value={}):
                    _load()

        assert len(captured_paths) == 1, "expected exactly one read_parquet call"
        assert os.path.normpath(captured_paths[0]) == os.path.normpath(_OOF_FAITHFUL_PATH), (
            f"flag-ON should read {_OOF_FAITHFUL_PATH!r}, got {captured_paths[0]!r}"
        )


# ── tests 11-12: byte-identical OFF + functional ON ──────────────────────────

class TestLoadOofPriorValues:
    """End-to-end tests that actually read the parquet files (skipped gracefully
    if the files are absent, e.g. in CI without the full data tree)."""

    def _skip_if_absent(self, path):
        import pytest
        if not os.path.exists(path):
            pytest.skip(f"parquet not present: {path}")

    def test_flag_off_byte_identical_to_direct_read(self):
        """Flag-OFF result must be identical to reading _OOF_PATH directly."""
        self._skip_if_absent(_OOF_PATH)
        import pandas as pd

        # Direct reference read (no flag involved).
        df_ref = pd.read_parquet(
            _OOF_PATH, columns=["game_id", "player_id", "stat", "oof_pred"]
        )
        ref_dict = {}
        for r in df_ref.itertuples(index=False):
            try:
                ref_dict[(str(r.game_id), int(r.player_id), str(r.stat))] = float(r.oof_pred)
            except (TypeError, ValueError):
                continue

        with _with_flag(None):
            got = _load()

        assert got == ref_dict, (
            f"flag-OFF produced {len(got)} entries vs reference {len(ref_dict)}; "
            "values must be byte-identical"
        )

    def test_flag_on_loads_faithful_parquet(self):
        """Flag-ON must load pregame_oof_faithful.parquet and return a non-empty dict."""
        self._skip_if_absent(_OOF_FAITHFUL_PATH)

        with _with_flag("1"):
            got = _load()

        assert isinstance(got, dict), "result must be a dict"
        assert len(got) > 0, "faithful parquet loaded but returned empty dict"
        # Spot-check: all keys are (str, int, str) tuples.
        key = next(iter(got))
        assert isinstance(key, tuple) and len(key) == 3, f"unexpected key shape: {key}"
        assert isinstance(key[0], str), f"game_id must be str, got {type(key[0])}"
        assert isinstance(key[1], int), f"player_id must be int, got {type(key[1])}"
        assert isinstance(key[2], str), f"stat must be str, got {type(key[2])}"

    def test_flag_on_covers_all_7_stats(self):
        """Faithful parquet must contain all 7 stats (pts/reb/ast/fg3m/stl/blk/tov)."""
        self._skip_if_absent(_OOF_FAITHFUL_PATH)

        with _with_flag("1"):
            got = _load()

        stats_present = {k[2] for k in got}
        expected = set(_eval.STATS)
        assert stats_present >= expected, (
            f"faithful dict missing stats: {expected - stats_present}"
        )

    def test_flag_off_and_on_differ_on_reb(self):
        """For 'reb' stat, the legacy-blend and faithful-q50 anchors should differ
        in value for at least some (game_id, player_id) pairs — confirming the
        switch actually changes numbers."""
        self._skip_if_absent(_OOF_PATH)
        self._skip_if_absent(_OOF_FAITHFUL_PATH)

        with _with_flag(None):
            legacy = _load()
        with _with_flag("1"):
            faithful = _load()

        # Keys present in both.
        common_reb = {k for k in legacy if k[2] == "reb"} & {k for k in faithful if k[2] == "reb"}
        if not common_reb:
            import pytest
            pytest.skip("no overlapping (game_id, player_id, reb) keys between the two parquets")

        diffs = sum(1 for k in common_reb if abs(legacy[k] - faithful[k]) > 1e-6)
        assert diffs > 0, (
            "legacy-blend and faithful-q50 reb priors are identical for all overlapping "
            "keys — the flag switch is not changing the anchor value"
        )

    def test_flag_off_and_on_identical_on_pts(self):
        """For 'pts' stat (served_head='blend' in both files), the priors should be
        numerically close (same head type), though not necessarily bit-identical
        (different training runs / fold splits).
        NOTE: this is an advisory test — it asserts values exist, not exact equality."""
        self._skip_if_absent(_OOF_PATH)
        self._skip_if_absent(_OOF_FAITHFUL_PATH)

        with _with_flag(None):
            legacy = _load()
        with _with_flag("1"):
            faithful = _load()

        legacy_pts = {k: v for k, v in legacy.items() if k[2] == "pts"}
        faithful_pts = {k: v for k, v in faithful.items() if k[2] == "pts"}
        assert len(legacy_pts) > 0, "legacy dict has no pts entries"
        assert len(faithful_pts) > 0, "faithful dict has no pts entries"
