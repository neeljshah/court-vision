"""S174 construct: an opt-in historical drop view cannot change live readers.

Run only this file with:
python -m pytest tests/platformkit/foundry/test_s174_frozen_spec_v2.py -q
"""
import json
import subprocess
import sys
import types
from dataclasses import asdict
from pathlib import Path

from scripts.platformkit.eval_gate.family_bars import SPEC_PATH, git_blob_id, load_families
from scripts.platformkit.eval_gate.frozen_family_versions import (
    DROP_REASON, S14_V1_PIN, S14_V2, s14_v2_pin)


DEFAULT_VERSION = "s144-families-v4"
DEFAULT_PIN = "9e05a449ed313feb08dd54559d1e9328ed1dbbb7"
V2_PIN = "df461f2744a8d6754f7ef643e79abf2ecefeee0614599f64b7c7f42714114ae1"
DROPPED = ("mlb_inning", "nba_quarter_shape")
READERS = (
    "scripts/platformkit/foundry/promotion_report.py",
    "scripts/platformkit/foundry/run_ingame_screen.py",
    "scripts/platformkit/foundry/screen_predictor_supply.py",
    "scripts/platformkit/foundry/seed_queue.py",
    "scripts/platformkit/ops/factory_source_manifest.py",
)


def _snapshot(spec) -> bytes:
    return json.dumps({"spec_version": spec.spec_version, "q": spec.q_within_family,
                       "path": spec.spec_path, "pin": spec.prereg_sha256,
                       "families": [asdict(family) for family in spec.families]},
                      sort_keys=True, separators=(",", ":")).encode("ascii")


def _master_family_bars_module():
    source = subprocess.run(["git", "show", "master:scripts/platformkit/eval_gate/family_bars.py"],
                            capture_output=True, check=True).stdout.decode("ascii")
    module = types.ModuleType("s174_master_family_bars")
    sys.modules[module.__name__] = module
    exec(compile(source, "master:family_bars.py", "exec"), module.__dict__)
    return module


def test_s174_v1_pin_v2_full_history_and_default_view_are_sealed():
    """The opt-in v2 record retains all 37 v1 records and drops exactly 2/21."""
    default = load_families()
    assert (default.spec_version, default.prereg_sha256, len(default.families)) == (
        DEFAULT_VERSION, DEFAULT_PIN, 41)
    assert default.prereg_sha256 == git_blob_id(SPEC_PATH)
    assert _snapshot(default) == _snapshot(_master_family_bars_module().load_families())

    v1 = load_families(version="s14-families-v1")
    v2 = load_families(version=S14_V2)
    v2_all = load_families(version=S14_V2, dropped=True)
    dropped = [family for family in v2_all.families
               if getattr(family, "status", "ACTIVE") == "DROPPED"]

    assert (v1.spec_version, v1.prereg_sha256, len(v1.families)) == (
        "s14-families-v1", S14_V1_PIN, 37)
    assert [family.name for family in v2_all.families] == [family.name for family in v1.families]
    assert [family.name for family in dropped] == list(DROPPED)
    assert all(family.reason == DROP_REASON for family in dropped)
    assert v2_all.get("mlb_inning").status == "DROPPED"
    assert v2_all.get("nba_quarter_shape").status == "DROPPED"
    assert sum(len(family.members) for family in dropped) == 21
    assert len(v2.families) == len(v1.families) - len(dropped) == 35
    assert not set(DROPPED) & {family.name for family in v2.families}
    assert v2.prereg_sha256 == s14_v2_pin(v1.families) == V2_PIN


def test_s174_readers_do_not_opt_into_the_versioned_view():
    """Every production importer retains the no-argument default call site."""
    for relative in READERS:
        text = Path(relative).read_text(encoding="ascii")
        assert "load_families(version=" not in text, relative
        assert "load_families(dropped=" not in text, relative
