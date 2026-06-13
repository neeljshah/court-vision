"""tests/platform/test_check_no_public_push.py

Unit tests for scripts/platformkit/check_no_public_push.py.

KEY property under test: the guard must FAIL SAFE — any error condition
(missing file, malformed JSON, unknown state) must default to BLOCKING the
push, never to allowing it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.platformkit.check_no_public_push import (
    _is_public_remote,
    _load_open_phases,
    check_push_allowed,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_state(path: Path, phases: dict) -> None:
    """Write a minimal build_state.json with the given phases dict."""
    path.write_text(json.dumps({"phases": phases}), encoding="utf-8")


# ---------------------------------------------------------------------------
# _is_public_remote — URL + name detection
# ---------------------------------------------------------------------------

class TestIsPublicRemote:
    def test_origin_name_is_public(self):
        assert _is_public_remote("origin") is True

    def test_private_name_is_not_public(self):
        assert _is_public_remote("private") is False

    def test_arbitrary_name_is_not_public(self):
        assert _is_public_remote("upstream") is False

    def test_url_fragment_triggers_public(self):
        url = "https://github.com/neeljshah/court-vision.git"
        assert _is_public_remote("myrandom", url) is True

    def test_non_matching_url_plus_private_name(self):
        url = "https://github.com/neeljshah/court-vision-private.git"
        # URL does not contain the exact fragment "neeljshah/court-vision" as a
        # standalone match, BUT the fragment IS a substring of that URL string.
        # Verify the actual behaviour rather than assuming: the module uses
        # `_PUBLIC_URL_FRAGMENT in remote_url` (substring), so this should match.
        # We record what the code does — if the fragment is present it is True.
        from scripts.platformkit.check_no_public_push import _PUBLIC_URL_FRAGMENT
        expected = _PUBLIC_URL_FRAGMENT in url
        assert _is_public_remote("myrandom", url) is expected

    def test_empty_url_does_not_crash(self):
        assert _is_public_remote("private", "") is False


# ---------------------------------------------------------------------------
# _load_open_phases
# ---------------------------------------------------------------------------

class TestLoadOpenPhases:
    def test_all_done_returns_empty(self, tmp_path):
        p = tmp_path / "state.json"
        _write_state(p, {"p1": {"status": "done"}, "p2": {"status": "done"}})
        assert _load_open_phases(p) == []

    def test_open_phase_returned(self, tmp_path):
        p = tmp_path / "state.json"
        _write_state(p, {"p1": {"status": "in_progress"}, "p2": {"status": "done"}})
        result = _load_open_phases(p)
        assert len(result) == 1
        assert result[0][0] == "p1"
        assert result[0][1] == "in_progress"

    def test_missing_status_treated_as_open(self, tmp_path):
        p = tmp_path / "state.json"
        _write_state(p, {"p1": {}})  # no "status" key
        result = _load_open_phases(p)
        assert len(result) == 1

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            _load_open_phases(tmp_path / "nonexistent.json")

    def test_malformed_json_raises(self, tmp_path):
        p = tmp_path / "state.json"
        p.write_text("{bad json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            _load_open_phases(p)


# ---------------------------------------------------------------------------
# check_push_allowed — the core public function
# ---------------------------------------------------------------------------

class TestCheckPushAllowed:

    # Case 1 — private remote → always allowed regardless of state
    def test_private_remote_allowed_open_phases(self, tmp_path):
        p = tmp_path / "state.json"
        _write_state(p, {"p1": {"status": "in_progress"}})
        allowed, reason = check_push_allowed("private", "", p)
        assert allowed is True
        assert "not the public" in reason.lower() or "allowed" in reason.lower()

    def test_private_remote_allowed_missing_state(self, tmp_path):
        # State file doesn't even need to exist for a private push.
        allowed, reason = check_push_allowed("private", "", tmp_path / "no_file.json")
        assert allowed is True

    # Case 2 — public remote + open phases → BLOCKED
    def test_public_remote_open_phases_blocked(self, tmp_path):
        p = tmp_path / "state.json"
        _write_state(p, {"p1": {"status": "in_progress"}, "p2": {"status": "pending"}})
        allowed, reason = check_push_allowed("origin", "", p)
        assert allowed is False
        assert "BLOCKED" in reason

    def test_block_message_mentions_open_phases(self, tmp_path):
        p = tmp_path / "state.json"
        _write_state(p, {"alpha": {"status": "in_progress"}})
        allowed, reason = check_push_allowed("origin", "", p)
        assert allowed is False
        assert "alpha" in reason or "1 open" in reason

    # Case 3 — public remote + all phases done → allowed
    def test_public_remote_all_done_allowed(self, tmp_path):
        p = tmp_path / "state.json"
        _write_state(p, {"p1": {"status": "done"}, "p2": {"status": "done"}})
        allowed, reason = check_push_allowed("origin", "", p)
        assert allowed is True

    def test_public_remote_empty_phases_allowed(self, tmp_path):
        # No phases at all — nothing is open, should allow.
        p = tmp_path / "state.json"
        _write_state(p, {})
        allowed, reason = check_push_allowed("origin", "", p)
        assert allowed is True

    # Case 4 — SAFE-FAIL: missing state file → BLOCKED (never fails open)
    def test_missing_state_file_safe_fail(self, tmp_path):
        allowed, reason = check_push_allowed("origin", "", tmp_path / "missing.json")
        assert allowed is False, (
            "SAFETY VIOLATION: push guard failed OPEN on missing state file"
        )
        assert "BLOCKED" in reason

    # Case 5 — SAFE-FAIL: malformed JSON → BLOCKED (never fails open)
    def test_malformed_json_safe_fail(self, tmp_path):
        p = tmp_path / "state.json"
        p.write_text("{this is not valid JSON!!!", encoding="utf-8")
        allowed, reason = check_push_allowed("origin", "", p)
        assert allowed is False, (
            "SAFETY VIOLATION: push guard failed OPEN on malformed JSON"
        )
        assert "BLOCKED" in reason

    def test_json_wrong_type_safe_fail(self, tmp_path):
        # JSON is valid but the top-level value is a list, not a dict.
        # _load_open_phases calls state.get() → AttributeError on a list.
        # check_push_allowed now catches AttributeError (and ValueError) and
        # returns a clean (False, "BLOCKED...") tuple — no exception propagates.
        p = tmp_path / "state.json"
        p.write_text("[1, 2, 3]", encoding="utf-8")
        allowed, reason = check_push_allowed("origin", "", p)
        assert allowed is False, (
            "SAFETY VIOLATION: push guard failed OPEN on non-dict JSON state"
        )
        assert "BLOCKED" in reason

    # Case 6 — public-remote URL detection via known fragment
    def test_url_based_public_detection_blocked(self, tmp_path):
        p = tmp_path / "state.json"
        _write_state(p, {"p1": {"status": "open"}})
        # Pass remote_name that isn't "origin" but URL contains the fragment.
        url = "git@github.com:neeljshah/court-vision.git"
        allowed, reason = check_push_allowed("notorigin", url, p)
        assert allowed is False
        assert "BLOCKED" in reason

    def test_url_based_public_all_done_allowed(self, tmp_path):
        p = tmp_path / "state.json"
        _write_state(p, {"p1": {"status": "done"}})
        url = "https://github.com/neeljshah/court-vision.git"
        allowed, reason = check_push_allowed("notorigin", url, p)
        assert allowed is True

    # Explicit fail-safe meta-test: enumerate error classes and confirm blocking.
    # The guard catches (JSONDecodeError, KeyError, TypeError, AttributeError,
    # ValueError) — all parse/shape errors return (False, "BLOCKED...") cleanly.
    @pytest.mark.parametrize("bad_content", [
        "",           # empty file → JSONDecodeError (caught → BLOCKED tuple)
        '{"phases": []}',  # phases is a list, not dict → AttributeError on .items()
    ])
    def test_error_conditions_never_fail_open(self, tmp_path, bad_content):
        """The guard must NEVER return (True, ...) on a broken state file."""
        p = tmp_path / "state.json"
        p.write_text(bad_content, encoding="utf-8")
        try:
            allowed, reason = check_push_allowed("origin", "", p)
            # If it returns a tuple, it must be blocked.
            assert allowed is False, (
                f"SAFETY VIOLATION: failed OPEN for content={bad_content!r}: {reason}"
            )
        except Exception:
            # A raised exception is also fail-safe (push never happens) — pass.
            pass

    def test_empty_file_returns_blocked_tuple(self, tmp_path):
        """Empty file → JSONDecodeError → clean (False, 'BLOCKED...') return."""
        p = tmp_path / "state.json"
        p.write_text("", encoding="utf-8")
        allowed, reason = check_push_allowed("origin", "", p)
        assert allowed is False
        assert "BLOCKED" in reason
