"""Per-file contract test for scripts/view_local.ps1 (RB-E-3 + -Health).

view_local.ps1 is PowerShell, not pytest-driven, so this test asserts its DOCUMENTED
CONTRACT by reading the script text: it exposes -Stop/-Dev/-Health, NEVER registers
an autostart, and -Health CONSUMES the freshness field (reports STALE on a reachable-
but-stale producer, never GREEN-on-merely-reachable), and carries no $ figures.
"""
from __future__ import annotations

import pathlib
import re

_REPO = pathlib.Path(__file__).resolve().parents[2]
_PS = _REPO / "scripts" / "view_local.ps1"


def _text() -> str:
    return _PS.read_text(encoding="utf-8", errors="replace")


def test_script_exists():
    assert _PS.is_file()


def test_exposes_stop_dev_health_switches():
    t = _text()
    for sw in ("[switch]$Stop", "[switch]$Dev", "[switch]$Health"):
        assert sw in t, sw


def test_never_registers_autostart():
    t = _text().lower()
    # No scheduled-task / startup-registry / autostart registration whatsoever.
    for forbidden in ("register-scheduledtask", "schtasks", "new-scheduledtask",
                      "currentversion\\run", "startup"):
        assert forbidden not in t, forbidden


def test_health_consumes_freshness_not_reachable_green():
    t = _text()
    # -Health reads the canonical producer-freshness surface, not just a 200.
    assert "/api/produce/status" in t
    # It explicitly degrades a reachable-but-stale producer to STALE (not green).
    assert "stale-never-green" in t.lower()
    assert "STALE" in t
    # Monotone-DOWN intent is documented in the health path.
    assert "monotone-DOWN" in t or "monotone-down" in t.lower()


def test_health_reports_down_on_unreachable():
    t = _text()
    # Unreachable -> DOWN (red), never green.
    assert "UNREACHABLE" in t
    assert "HEALTH: DOWN" in t


def test_health_honest_exit_codes_documented():
    t = _text()
    # Documented honest exit codes: 0=READY, 3=STALE/DEGRADED, 4=DOWN.
    assert "0=READY" in t
    assert "3=STALE" in t
    assert "4=DOWN" in t


def test_no_dollar_money_value():
    # No fabricated money value ($ adjacent to a digit). "no $" disclaimers allowed.
    t = _text()
    assert not re.search(r"\$\s*\d", t)
    assert "NO dollar figures" in t


def test_local_only_no_deploy_or_push():
    t = _text().lower()
    assert "local only" in t
    for forbidden in ("git push", "railway up", "vercel deploy"):
        assert forbidden not in t, forbidden
