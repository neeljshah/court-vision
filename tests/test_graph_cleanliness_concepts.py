"""tests/test_graph_cleanliness_concepts.py — concept-slug FP regression tests.

Companion to test_graph_cleanliness.py. Asserts BOTH directions of the concept-
slug fix: (1) every generated Driver/Mechanism concept slug + the archetype-dir
exemption PASS (no player_node / player_link); (2) a synthetic REAL player name
still FLAGS. tmp_path only — no network, no vault/ reads.
Run: pytest tests/test_graph_cleanliness_concepts.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.graph_cleanliness import (  # noqa: E402
    _is_player_filename,
    _under_concept_dir,
    scan_file,
    scan_vault,
)

# Every generated Driver/Mechanism concept slug (NBA/MLB/Soccer/Tennis). These are
# two-lowercase-word combos that previously tripped the first_last player regex.
_CONCEPT_SLUGS = [
    "balanced", "free_throws", "rebounding", "shooting", "turnovers",
    "pace_x_rebounding_weight", "pace_x_shooting_dominance",
    "shooting_margin_structure", "big_inning", "blowout", "bullpen_swing",
    "late_comeback", "routine", "sp_duel", "big_inning_x_total_runs",
    "sp_hand_x_game_mode", "dominant_but_drew", "finishing_variance",
    "ht_collapse", "red_card_swing", "territorial_control",
    "ht_lead_x_result_stability", "red_card_x_finishing", "bp_conversion_edge",
    "broke_late", "three_set_grind", "tiebreak_swing",
    "surface_x_bp_conversion", "surface_x_serve_hold",
]


# ── concept-slug false positives (the bug this fix closes) ────────────────────

class TestConceptSlugsNotPlayers:
    def test_concept_slug_filename_in_concept_dir_clean(self, tmp_path):
        # Every generated Driver/Mechanism slug, placed under a concept dir,
        # must produce ZERO player_node violations.
        for slug in _CONCEPT_SLUGS:
            f = tmp_path / "Drivers" / f"{slug}.md"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(f"# {slug}\n\n[[_Index]]\n", encoding="utf-8")
        rep = scan_vault(tmp_path)
        assert rep["player_nodes"] == 0, rep["violations"]
        assert rep["clean"] is True

    def test_shooting_margin_structure_wikilink_clean(self, tmp_path):
        # The _Mechanisms.md hub links [[shooting_margin_structure]] — concept,
        # not a player link (margin/structure are concept tokens).
        f = tmp_path / "Mechanisms" / "_Mechanisms.md"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("See [[shooting_margin_structure]].\n", encoding="utf-8")
        violations = scan_file(f, tmp_path)
        assert [v for v in violations if v.kind == "player_link"] == []

    def test_concept_token_slugs_not_player_filenames(self):
        # Token-level check independent of directory exemption.
        for slug in ("free_throws", "bullpen_swing", "late_comeback",
                     "red_card_swing", "ht_collapse", "territorial_control",
                     "broke_late", "bp_conversion_edge", "tiebreak_swing",
                     "shooting_margin_structure"):
            assert _is_player_filename(slug) is False, slug

    def test_under_concept_dir(self):
        assert _under_concept_dir("NBA/Drivers/free_throws.md") is True
        assert _under_concept_dir("MLB/Mechanisms/big_inning.md") is True
        assert _under_concept_dir("NBA/Archetypes/role_player.md") is True
        assert _under_concept_dir("Tennis/Reference/foo.md") is True
        assert _under_concept_dir("_Index/_Brain.md") is True
        # NOT a concept dir -> not exempt.
        assert _under_concept_dir("NBA/Players/lebron_james.md") is False


# ── synthetic REAL player still flags (must NOT be over-suppressed) ───────────

class TestRealPlayerStillFlags:
    def test_player_filename_outside_concept_dir_flags(self, tmp_path):
        # A real player file OUTSIDE a concept dir must still flag player_node.
        f = tmp_path / "Players" / "lebron_james.md"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("# LeBron James\n", encoding="utf-8")
        rep = scan_vault(tmp_path)
        assert rep["player_nodes"] >= 1, rep["violations"]
        assert rep["clean"] is False

    def test_player_id_filename_flags(self, tmp_path):
        f = tmp_path / "2544_lebron_james.md"
        f.write_text("# LeBron James\n", encoding="utf-8")
        rep = scan_vault(tmp_path)
        assert rep["player_nodes"] >= 1, rep["violations"]

    def test_player_id_filename_flags_even_in_concept_dir(self, tmp_path):
        # The id-prefix form is unambiguous; concept-dir exemption only covers
        # the two-lowercase-word slug heuristic, not id_first_last filenames.
        f = tmp_path / "Drivers" / "2544_lebron_james.md"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("# LeBron James\n", encoding="utf-8")
        rep = scan_vault(tmp_path)
        assert rep["player_nodes"] >= 1, rep["violations"]

    def test_player_wikilink_flags(self, tmp_path):
        f = tmp_path / "Schemes" / "drop_coverage.md"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("See [[LeBron James]] usage.\n", encoding="utf-8")
        violations = scan_file(f, tmp_path)
        assert any(v.kind == "player_link" for v in violations), violations
