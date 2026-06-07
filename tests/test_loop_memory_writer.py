"""Unit tests for src/loop/memory_writer.py.

All tests use dry_run=True or a tmp_path to avoid touching real memory files.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure repo root is on path (required when run standalone).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.loop import memory_writer as mw


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def fake_memory_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect MEMORY_DIR + MEMORY_INDEX to a tmp directory."""
    mem = tmp_path / "memory"
    mem.mkdir()
    monkeypatch.setattr(mw, "MEMORY_DIR", mem)
    monkeypatch.setattr(mw, "MEMORY_INDEX", mem / "MEMORY.md")
    return mem


@pytest.fixture()
def fake_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a minimal fake vault tree and redirect VAULT."""
    vault = tmp_path / "vault"
    intel = vault / "Intelligence"
    intel.mkdir(parents=True)
    (vault / "MOC-Research.md").write_text(
        "---\ntags: [moc]\n---\n# Research\n", encoding="utf-8"
    )
    (intel / "_Vault_Index.md").write_text(
        "# Vault Index\n", encoding="utf-8"
    )
    monkeypatch.setattr(mw, "VAULT", vault)
    return vault


@pytest.fixture()
def fake_profiles(tmp_path: Path) -> Path:
    """Create a minimal profiles directory tree for index-builder tests."""
    players = tmp_path / "players"
    teams = tmp_path / "teams"
    players.mkdir()
    teams.mkdir()

    # Two players.
    (players / "1628983.json").write_text(json.dumps({
        "player_id": 1628983,
        "player_name": "Shai Gilgeous-Alexander",
        "schema_version": "1.0",
        "as_of_game_date": "2026-05-27",
        "sections": {
            "bio": {},
            "scoring_usage": {
                "scoring": {
                    "pts_pg": 32.292, "min_per_game": 34.0, "n_games": 65
                }
            },
            "clutch": {},
            "coverage_faced": {},
            "prop_calibration": {},
        },
        "_provenance": {},
    }), encoding="utf-8")
    (players / "203507.json").write_text(json.dumps({
        "player_id": 203507,
        "player_name": "Giannis Antetokounmpo",
        "schema_version": "1.0",
        "as_of_game_date": "2026-05-20",
        "sections": {
            "bio": {},
            "scoring_usage": {
                "scoring": {"pts_pg": 30.4, "min_per_game": 35.1, "n_games": 60}
            },
        },
        "_provenance": {},
    }), encoding="utf-8")

    # One team.
    (teams / "OKC.json").write_text(json.dumps({
        "team_tricode": "OKC",
        "as_of_game_date": "2026-05-27",
        "sections": {
            "ratings": {"off_rtg": 117.24, "def_rtg": 110.39, "pace": 101.25},
            "defense_scheme": {"primary_scheme": "DROP COVERAGE"},
            "rebounding": {},
        },
        "_provenance": {
            "defense_scheme": {"confidence": "high"}
        },
    }), encoding="utf-8")

    return tmp_path


# ---------------------------------------------------------------------------
# _find_existing_note
# ---------------------------------------------------------------------------

class TestFindExistingNote:
    def test_finds_by_exact_type_slug(self, fake_memory_dir: Path) -> None:
        (fake_memory_dir / "project_my_slug.md").write_text("existing", encoding="utf-8")
        found = mw._find_existing_note("my_slug", "project")
        assert found is not None
        assert found.name == "project_my_slug.md"

    def test_finds_by_different_type(self, fake_memory_dir: Path) -> None:
        # slug exists as feedback_ but we query with project_ → should still find
        (fake_memory_dir / "feedback_my_slug.md").write_text("existing", encoding="utf-8")
        found = mw._find_existing_note("my_slug", "project")
        assert found is not None

    def test_returns_none_when_absent(self, fake_memory_dir: Path) -> None:
        found = mw._find_existing_note("nonexistent_slug", "project")
        assert found is None


# ---------------------------------------------------------------------------
# write_finding (dry_run)
# ---------------------------------------------------------------------------

class TestWriteFinding:
    def test_dry_run_returns_path_without_writing(
        self, fake_memory_dir: Path
    ) -> None:
        path = mw.write_finding(
            slug="test_signal",
            title="Test Signal Finding",
            body="Ablation delta: -0.012 MAE on walk-forward folds.",
            index_line="[Test Signal Finding](project_test_signal.md) — ablation -0.012",
            dry_run=True,
        )
        assert path == fake_memory_dir / "project_test_signal.md"
        assert not path.exists()  # dry_run: nothing written

    def test_writes_file_with_frontmatter(self, fake_memory_dir: Path) -> None:
        (fake_memory_dir / "MEMORY.md").write_text(
            "# Claude Memory\n\n## Recent feedback\n", encoding="utf-8"
        )
        path = mw.write_finding(
            slug="shot_profile_atlas",
            title="Shot Profile Atlas",
            body="526 players, as-of 2026-05-30.",
            index_line="[Shot Profile Atlas](project_shot_profile_atlas.md) — 526 players",
            origin_session_id="abc-123",
            dry_run=False,
        )
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert "---" in text  # has YAML frontmatter
        assert "node_type: memory" in text
        assert "Shot Profile Atlas" in text
        assert "526 players" in text

    def test_sharpens_existing_note(self, fake_memory_dir: Path) -> None:
        """A second call for the same slug updates rather than overwrites."""
        (fake_memory_dir / "MEMORY.md").write_text(
            "# Memory\n\n## Recent feedback\n", encoding="utf-8"
        )
        existing = fake_memory_dir / "project_my_atlas.md"
        existing.write_text(
            "---\nname: project_my_atlas\ndescription: \"orig\"\n"
            "metadata:\n  node_type: memory\n  type: project\n  originSessionId: x\n---\n"
            "\n# My Atlas\n\nOriginal body with real numbers.\n",
            encoding="utf-8",
        )
        mw.write_finding(
            slug="my_atlas",
            title="My Atlas",
            body="Updated body with new numbers.",
            index_line="[My Atlas](project_my_atlas.md) — updated",
            dry_run=False,
        )
        updated = existing.read_text(encoding="utf-8")
        assert "Original body" in updated
        assert "Updated body" in updated

    def test_index_line_inserted_in_memory_md(self, fake_memory_dir: Path) -> None:
        mem_md = fake_memory_dir / "MEMORY.md"
        mem_md.write_text(
            "# Claude Memory\n\n## Recent feedback\n- [Old](old.md) — old\n",
            encoding="utf-8",
        )
        mw.write_finding(
            slug="new_signal",
            title="New Signal",
            body="body",
            index_line="[New Signal](project_new_signal.md) — ships",
            dry_run=False,
        )
        updated = mem_md.read_text(encoding="utf-8")
        assert "New Signal" in updated


# ---------------------------------------------------------------------------
# refresh_memory_index
# ---------------------------------------------------------------------------

class TestRefreshMemoryIndex:
    def test_inserts_under_header(self, fake_memory_dir: Path) -> None:
        mem_md = fake_memory_dir / "MEMORY.md"
        mem_md.write_text(
            "# Memory\n\n## Recent feedback\n- [Old](old.md)\n",
            encoding="utf-8",
        )
        mw.refresh_memory_index(
            "[New finding](project_new.md) — new",
            slug="new",
            dry_run=False,
        )
        text = mem_md.read_text(encoding="utf-8")
        assert "New finding" in text

    def test_deduplication_replaces_old_line(self, fake_memory_dir: Path) -> None:
        mem_md = fake_memory_dir / "MEMORY.md"
        mem_md.write_text(
            "# Memory\n\n## Recent feedback\n"
            "- [Old](project_slug.md) — version 1\n",
            encoding="utf-8",
        )
        mw.refresh_memory_index(
            "[New](project_slug.md) — version 2",
            slug="slug",
            dry_run=False,
        )
        text = mem_md.read_text(encoding="utf-8")
        assert "version 2" in text
        # Old version should have been replaced (removed).
        assert "version 1" not in text

    def test_dry_run_no_write(self, fake_memory_dir: Path) -> None:
        mem_md = fake_memory_dir / "MEMORY.md"
        mem_md.write_text("# Memory\n\n## Recent feedback\n", encoding="utf-8")
        original = mem_md.read_text(encoding="utf-8")
        mw.refresh_memory_index("[X](x.md)", dry_run=True)
        assert mem_md.read_text(encoding="utf-8") == original

    def test_noop_when_no_memory_md(self, fake_memory_dir: Path) -> None:
        # No MEMORY.md — should not raise.
        mw.refresh_memory_index("[X](x.md)", dry_run=False)


# ---------------------------------------------------------------------------
# write_vault_atlas_note
# ---------------------------------------------------------------------------

class TestWriteVaultAtlasNote:
    def test_returns_none_when_vault_absent(self, tmp_path: Path,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mw, "VAULT", tmp_path / "nonexistent_vault")
        result = mw.write_vault_atlas_note(name="SomeAtlas", body="body", dry_run=False)
        assert result is None

    def test_creates_atlas_note(self, fake_vault: Path) -> None:
        result = mw.write_vault_atlas_note(
            name="Shot_Profile", body="526 players, rim_freq top.", dry_run=False
        )
        assert result is not None
        assert result.exists()
        assert "Shot_Profile" in result.name
        text = result.read_text(encoding="utf-8")
        assert "526 players" in text

    def test_links_vault_index(self, fake_vault: Path) -> None:
        mw.write_vault_atlas_note(name="Form_Atlas", body="body", dry_run=False)
        vault_idx = fake_vault / "Intelligence" / "_Vault_Index.md"
        text = vault_idx.read_text(encoding="utf-8")
        assert "[[Form_Atlas_Atlas]]" in text

    def test_links_moc(self, fake_vault: Path) -> None:
        mw.write_vault_atlas_note(
            name="DefScheme_Atlas", body="body", moc="MOC-Research", dry_run=False
        )
        moc = fake_vault / "MOC-Research.md"
        text = moc.read_text(encoding="utf-8")
        assert "DefScheme_Atlas" in text

    def test_dry_run_no_write(self, fake_vault: Path) -> None:
        result = mw.write_vault_atlas_note(
            name="DryTest", body="body", dry_run=True
        )
        # Path returned but not written.
        assert result is not None
        assert not result.exists()

    def test_idempotent_vault_index_link(self, fake_vault: Path) -> None:
        mw.write_vault_atlas_note(name="IdemAtlas", body="body", dry_run=False)
        mw.write_vault_atlas_note(name="IdemAtlas", body="body update", dry_run=False)
        vault_idx = fake_vault / "Intelligence" / "_Vault_Index.md"
        text = vault_idx.read_text(encoding="utf-8")
        assert text.count("[[IdemAtlas_Atlas]]") == 1  # not duplicated


# ---------------------------------------------------------------------------
# refresh_profile_indices (dry_run)
# ---------------------------------------------------------------------------

class TestRefreshProfileIndices:
    def test_dry_run_returns_stub(self) -> None:
        result = mw.refresh_profile_indices(dry_run=True)
        assert result["rc"] == -1
        assert "player_index" in result
        assert "team_index" in result

    def test_missing_script_returns_stub(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mw, "ROOT", Path("/nonexistent"))
        result = mw.refresh_profile_indices(dry_run=False)
        assert result["rc"] == -1


# ---------------------------------------------------------------------------
# build_profile_indices script (unit-level)
# ---------------------------------------------------------------------------

class TestBuildProfileIndices:
    def test_player_index_structure(self, fake_profiles: Path,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
        import scripts.loop.build_profile_indices as bpi
        monkeypatch.setattr(bpi, "PLAYERS_DIR", fake_profiles / "players")
        monkeypatch.setattr(bpi, "TEAMS_DIR", fake_profiles / "teams")

        idx = bpi.build_player_index()
        assert idx["n_players"] == 2
        player = next(p for p in idx["players"] if p["player_id"] == 1628983)
        assert player["name"] == "Shai Gilgeous-Alexander"
        assert player["has_clutch"] is True
        assert player["has_prop_cal"] is True
        assert player["pts_pg"] == pytest.approx(32.292, rel=1e-3)
        assert player["n_games"] == 65
        assert "bio" in player["sections"]

    def test_team_index_structure(self, fake_profiles: Path,
                                   monkeypatch: pytest.MonkeyPatch) -> None:
        import scripts.loop.build_profile_indices as bpi
        monkeypatch.setattr(bpi, "PLAYERS_DIR", fake_profiles / "players")
        monkeypatch.setattr(bpi, "TEAMS_DIR", fake_profiles / "teams")

        idx = bpi.build_team_index()
        assert idx["n_teams"] == 1
        team = idx["teams"][0]
        assert team["team"] == "OKC"
        assert team["n_sections"] == 3
        assert team["scheme"] == "DROP COVERAGE"
        assert team["off_rtg"] == pytest.approx(117.24, rel=1e-3)

    def test_fully_loaded_count(self, fake_profiles: Path,
                                 monkeypatch: pytest.MonkeyPatch) -> None:
        import scripts.loop.build_profile_indices as bpi
        monkeypatch.setattr(bpi, "PLAYERS_DIR", fake_profiles / "players")
        monkeypatch.setattr(bpi, "TEAMS_DIR", fake_profiles / "teams")

        idx = bpi.build_player_index()
        # SGA has 5 sections; neither qualifies for 15+.
        assert idx["fully_loaded_15plus"] == 0
        assert idx["max_sections"] == 5

    def test_malformed_json_skipped(self, fake_profiles: Path,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
        import scripts.loop.build_profile_indices as bpi
        monkeypatch.setattr(bpi, "PLAYERS_DIR", fake_profiles / "players")
        monkeypatch.setattr(bpi, "TEAMS_DIR", fake_profiles / "teams")

        (fake_profiles / "players" / "bad.json").write_text(
            "{not valid json", encoding="utf-8"
        )
        # Should not raise; malformed file is skipped.
        idx = bpi.build_player_index()
        assert idx["n_players"] == 2  # only the two valid players
