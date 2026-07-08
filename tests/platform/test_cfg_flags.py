"""P0-E-001 -- tests for the 10 CV_CFG_* kernel-extraction config flags.

Registry-only diff (src/brain/flags.py): each flag is default-OFF and
flag_allowed_on=False until its recorded gate verdict (EXTRACTION_PLAN
Sec2.1.3 gate text). This file asserts the registration contract only --
no behavior is exercised (the flags have no reader wiring yet).
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))  # for `brain.flags`

from brain.flags import FLAGS, assert_registered, is_on  # noqa: E402

CV_CFG_FLAGS = (
    "CV_CFG_STATS",
    "CV_CFG_PBP",
    "CV_CFG_COURT",
    "CV_CFG_CLOCK",
    "CV_CFG_LEAGUE_CLIENT",
    "CV_CFG_ROSTER",
    "CV_CFG_SPEED",
    "CV_CFG_GAMESTATE",
    "CV_CFG_ENTITIES",
    "CV_CFG_ATLAS",
)


def test_all_ten_cfg_flags_registered():
    for flag in CV_CFG_FLAGS:
        assert flag in FLAGS, f"{flag} missing from FLAGS registry"
    assert len(CV_CFG_FLAGS) == 10


def test_all_ten_cfg_flags_default_off():
    for flag in CV_CFG_FLAGS:
        assert FLAGS[flag]["default"] is False, f"{flag} default must be False"


def test_all_ten_cfg_flags_read_off_by_default():
    # env unset -> is_on() reads False regardless of registry entry
    for flag in CV_CFG_FLAGS:
        os.environ.pop(flag, None)
        assert is_on(flag) is False, f"{flag} must read OFF with env unset"


def test_all_ten_cfg_flags_allowed_on_is_false():
    # No dedicated schema field for flag_allowed_on (matches existing
    # DATA_BLOCKED_UNTIL_2SEASON_PBP-style entries); it is asserted via the
    # gate text, per the repo's established convention.
    for flag in CV_CFG_FLAGS:
        gate = FLAGS[flag]["gate"]
        assert "flag_allowed_on=FALSE" in gate, f"{flag} gate text must record flag_allowed_on=FALSE"


def test_unknown_flag_lookup_still_raises():
    try:
        assert_registered("CV_CFG_DOES_NOT_EXIST")
    except KeyError:
        pass
    else:
        raise AssertionError("assert_registered should raise KeyError for an unknown flag")


def test_registered_cfg_flags_do_not_raise():
    for flag in CV_CFG_FLAGS:
        assert_registered(flag)  # must not raise


def test_no_cv_kernel_or_cv_domain_namespace_collision():
    # MASTER_PLAN R9: no CV_KERNEL_* names; CV_DOMAIN_<SPORT> reserved for
    # sport enablement -- neither namespace was created by this registration.
    for flag in CV_CFG_FLAGS:
        assert not flag.startswith("CV_KERNEL_")
        assert not flag.startswith("CV_DOMAIN_")
