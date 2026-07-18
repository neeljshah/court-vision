"""Synthetic tests for scripts.platformkit.pod_sprint.regen_manifest -- no
data/ needed, everything is resolved by importing/regexing real repo source
files (domains/, scripts/platformkit/intel_validation/) that already exist
in a clean checkout."""
from __future__ import annotations

from scripts.platformkit.pod_sprint import regen_manifest as rm


def test_family_for_producer_bespoke_single_family():
    assert rm.family_for_producer(
        "scripts/platformkit/intel_validation/nba_canonical_shooter_claims.py"
    ) == ["nba_canonical_shooter_claims"]


def test_family_for_producer_claims_grid_returns_whole_sport_grid():
    families = rm.family_for_producer("domains/mlb/claims_grid.py")
    assert set(families) == {
        "mlb_batter_rate", "mlb_pitcher_rate", "mlb_team_rate", "mlb_bullpen_fatigue_chains",
    }


def test_family_for_producer_multi_family_bespoke_module():
    assert rm.family_for_producer("domains/mlb/claims_shift_framing.py") == [
        "mlb_framing_claims", "mlb_shift_vulnerability_claims",
    ]


def test_family_for_producer_shared_factory_returns_every_auto_grid_family():
    # claims_factory.py's own logic backs every auto-grid family across every sport.
    families = set(rm.family_for_producer("scripts/platformkit/intel_validation/claims_factory.py"))
    assert {"nba_player_box_rate", "nba_team_box_rate", "mlb_batter_rate"} <= families


def test_family_for_producer_support_builder_returns_empty():
    # nba_fit_ingredient_builders.py writes only a parquet snapshot, no
    # distinct intel_claims family of its own -- honest [], not a guess.
    assert rm.family_for_producer(
        "scripts/platformkit/intel_validation/nba_fit_ingredient_builders.py"
    ) == []


def test_regen_command_auto_grid_family():
    cmd = rm.regen_command_for_family("nba_player_box_rate")
    assert cmd == (
        "python -m scripts.platformkit.intel_validation.claims_factory "
        "--sport basketball_nba --family nba_player_box_rate"
    )


def test_regen_command_bespoke_family():
    cmd = rm.regen_command_for_family("nba_canonical_shooter_claims")
    assert cmd == "python -m scripts.platformkit.intel_validation.nba_canonical_shooter_claims"


def test_regen_command_unknown_family_is_none():
    assert rm.regen_command_for_family("totally_made_up_family_xyz") is None


def test_regen_command_unresolvable_shared_ledger_is_none():
    # prereg_hypothesis_ledger.jsonl has a dozen independent writers across
    # sports -- no single regen command is honest, so this must stay None.
    assert rm.regen_command_for_family("prereg_hypothesis_ledger") is None


def test_overrides_entries_resolve():
    assert set(rm.OVERRIDES) == {
        "mlb_framing_claims", "mlb_shift_vulnerability_claims", "nba_quality_claims",
    }
    for family, module in rm.OVERRIDES.items():
        assert rm.regen_command_for_family(family) == f"python -m {module}"
