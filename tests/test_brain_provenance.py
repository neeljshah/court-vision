"""tests/test_brain_provenance.py — Unit tests for src/sim/agent/provenance.py.

ROADMAP PHASE: Domain 1 — Entity-Agent Layer (D01_entity_agent.md §9 Step 1).
Tests:
  - content_hash is deterministic (same SimAgent twice -> same hash).
  - content_hash is sensitive (change one field -> different hash).
  - content_hash is order-independent for assist_feeders (dict insertion order).
  - stamp_agent returns AgentProvenance with schema_version==SCHEMA_VERSION
    and a 64+ char hex content_hash.
  - built_from_mtimes returns ISO-8601 strings for existing files; skips missing.
"""
from __future__ import annotations

import os
import re
import tempfile
from typing import Dict, Optional

import pytest

from sim.agent.schema import SCHEMA_VERSION, SimAgent
from sim.agent.provenance import (
    built_from_mtimes,
    content_hash,
    stamp,
    stamp_agent,
)


# ---------------------------------------------------------------------------
# Fixture: minimal valid SimAgent
# ---------------------------------------------------------------------------

def _make_agent(
    pid: int = 1001,
    pts_pg: float = 20.0,
    archetype: str = "WING_SCORER",
    assist_feeders: Optional[Dict[int, float]] = None,
) -> SimAgent:
    """Construct a SimAgent with sensible defaults for testing."""
    if assist_feeders is None:
        assist_feeders = {202: 3.0, 101: 1.5}
    return SimAgent(
        pid=pid,
        name="Test Player",
        team="NYK",
        use_per_min=0.35,
        shot_share=0.22,
        tov_share=0.12,
        ft_share=0.15,
        ft_pct=0.82,
        fg3_rate=0.38,
        fg3_pct=0.37,
        z_rim=0.30,
        z_paint=0.15,
        z_mid=0.10,
        z_3=0.45,
        fg_rim=0.61,
        fg_paint=0.46,
        fg_mid=0.41,
        ast_per_min=0.08,
        oreb_per_min=0.02,
        dreb_per_min=0.06,
        stl_per_min=0.03,
        blk_per_min=0.01,
        pf_per_min=0.05,
        pts_pg=pts_pg,
        ft_pts_share=0.18,
        mpg=32.0,
        archetype=archetype,
        creation=0.55,
        self_create=0.60,
        pm_prop=0.45,
        int_d=58.0,
        perim_d=62.0,
        height=78.0,
        age_fatigue_w=0.90,
        pts_pg_rec=21.5,
        reb_pg_rec=5.1,
        ast_pg_rec=3.8,
        mpg_rec=33.0,
        assist_feeders=dict(assist_feeders),
    )


# ---------------------------------------------------------------------------
# content_hash tests
# ---------------------------------------------------------------------------

class TestContentHash:
    def test_deterministic_same_agent(self) -> None:
        """Calling content_hash twice on the same agent returns the same string."""
        agent = _make_agent()
        h1 = content_hash(agent)
        h2 = content_hash(agent)
        assert h1 == h2

    def test_deterministic_equal_agents(self) -> None:
        """Two independently constructed agents with same params -> same hash."""
        agent_a = _make_agent()
        agent_b = _make_agent()
        assert content_hash(agent_a) == content_hash(agent_b)

    def test_sensitive_pts_pg(self) -> None:
        """Changing pts_pg produces a different hash."""
        agent_a = _make_agent(pts_pg=20.0)
        agent_b = _make_agent(pts_pg=20.1)
        assert content_hash(agent_a) != content_hash(agent_b)

    def test_sensitive_pid(self) -> None:
        """Changing pid produces a different hash."""
        agent_a = _make_agent(pid=1001)
        agent_b = _make_agent(pid=1002)
        assert content_hash(agent_a) != content_hash(agent_b)

    def test_sensitive_archetype(self) -> None:
        """Changing archetype (string field) produces a different hash."""
        agent_a = _make_agent(archetype="WING_SCORER")
        agent_b = _make_agent(archetype="PLAYMAKER")
        assert content_hash(agent_a) != content_hash(agent_b)

    def test_sensitive_assist_feeders_value(self) -> None:
        """Changing a value inside assist_feeders produces a different hash."""
        agent_a = _make_agent(assist_feeders={202: 3.0, 101: 1.5})
        agent_b = _make_agent(assist_feeders={202: 3.0, 101: 2.0})
        assert content_hash(agent_a) != content_hash(agent_b)

    def test_sensitive_assist_feeders_key(self) -> None:
        """Changing a key inside assist_feeders produces a different hash."""
        agent_a = _make_agent(assist_feeders={202: 3.0, 101: 1.5})
        agent_b = _make_agent(assist_feeders={202: 3.0, 999: 1.5})
        assert content_hash(agent_a) != content_hash(agent_b)

    def test_order_independent_assist_feeders(self) -> None:
        """assist_feeders with same content but different insertion order -> same hash."""
        # Dict A inserted in one order
        feeders_a: Dict[int, float] = {}
        feeders_a[101] = 1.5
        feeders_a[202] = 3.0

        # Dict B inserted in reverse order
        feeders_b: Dict[int, float] = {}
        feeders_b[202] = 3.0
        feeders_b[101] = 1.5

        # Verify they have different insertion orders but same content
        assert list(feeders_a.keys()) != list(feeders_b.keys())
        assert dict(feeders_a) == dict(feeders_b)

        agent_a = _make_agent(assist_feeders=feeders_a)
        agent_b = _make_agent(assist_feeders=feeders_b)
        assert content_hash(agent_a) == content_hash(agent_b)

    def test_hash_is_hex_string(self) -> None:
        """content_hash returns a lowercase hex string."""
        h = content_hash(_make_agent())
        assert isinstance(h, str)
        assert re.fullmatch(r"[0-9a-f]+", h), f"Non-hex chars in: {h!r}"

    def test_hash_length(self) -> None:
        """Blake2b with digest_size=32 -> 64 hex chars."""
        h = content_hash(_make_agent())
        assert len(h) == 64, f"Expected 64 chars, got {len(h)}: {h!r}"


# ---------------------------------------------------------------------------
# stamp_agent tests
# ---------------------------------------------------------------------------

class TestStampAgent:
    def test_schema_version_matches(self) -> None:
        """stamp_agent sets schema_version == SCHEMA_VERSION."""
        agent = _make_agent()
        prov = stamp_agent(agent, tier="FULL_PBP", built_from={})
        assert prov.schema_version == SCHEMA_VERSION

    def test_content_hash_64_chars(self) -> None:
        """stamp_agent fills a 64-char hex content_hash."""
        agent = _make_agent()
        prov = stamp_agent(agent, tier="FULL_PBP", built_from={})
        assert len(prov.content_hash) >= 64
        assert re.fullmatch(r"[0-9a-f]+", prov.content_hash)

    def test_content_hash_matches_standalone(self) -> None:
        """stamp_agent content_hash equals content_hash(agent)."""
        agent = _make_agent()
        prov = stamp_agent(agent, tier="VAULT_PROXY", built_from={})
        assert prov.content_hash == content_hash(agent)

    def test_tier_stored(self) -> None:
        """stamp_agent stores the tier correctly."""
        agent = _make_agent()
        prov_full = stamp_agent(agent, tier="FULL_PBP", built_from={})
        prov_vault = stamp_agent(agent, tier="VAULT_PROXY", built_from={})
        assert prov_full.tier == "FULL_PBP"
        assert prov_vault.tier == "VAULT_PROXY"

    def test_missing_fields_default_empty(self) -> None:
        """stamp_agent defaults missing_fields to empty list."""
        agent = _make_agent()
        prov = stamp_agent(agent, tier="FULL_PBP", built_from={})
        assert prov.missing_fields == []

    def test_missing_fields_stored(self) -> None:
        """stamp_agent stores provided missing_fields."""
        agent = _make_agent()
        prov = stamp_agent(agent, tier="VAULT_PROXY", built_from={}, missing_fields=["height"])
        assert prov.missing_fields == ["height"]

    def test_recency_asof_none_default(self) -> None:
        """stamp_agent defaults recency_asof to None."""
        agent = _make_agent()
        prov = stamp_agent(agent, tier="FULL_PBP", built_from={})
        assert prov.recency_asof is None

    def test_recency_asof_stored(self) -> None:
        """stamp_agent stores a provided recency_asof string."""
        agent = _make_agent()
        prov = stamp_agent(agent, tier="FULL_PBP", built_from={}, recency_asof="2026-06-07")
        assert prov.recency_asof == "2026-06-07"

    def test_different_agents_different_hashes(self) -> None:
        """Two agents with different fields produce different content_hashes in stamp_agent."""
        prov_a = stamp_agent(_make_agent(pts_pg=20.0), tier="FULL_PBP", built_from={})
        prov_b = stamp_agent(_make_agent(pts_pg=25.0), tier="FULL_PBP", built_from={})
        assert prov_a.content_hash != prov_b.content_hash

    def test_built_from_stored(self) -> None:
        """stamp_agent preserves built_from dict."""
        agent = _make_agent()
        bf = {"player_rates.parquet": "2026-06-08T00:00:00+00:00"}
        prov = stamp_agent(agent, tier="FULL_PBP", built_from=bf)
        assert prov.built_from == bf


# ---------------------------------------------------------------------------
# stamp (placeholder) tests
# ---------------------------------------------------------------------------

class TestStamp:
    def test_stamp_schema_version(self) -> None:
        """stamp returns AgentProvenance with schema_version == SCHEMA_VERSION."""
        prov = stamp(tier="FULL_PBP", built_from={})
        assert prov.schema_version == SCHEMA_VERSION

    def test_stamp_content_hash_empty(self) -> None:
        """stamp returns a placeholder content_hash of empty string."""
        prov = stamp(tier="FULL_PBP", built_from={})
        assert prov.content_hash == ""

    def test_stamp_tier(self) -> None:
        """stamp stores the tier."""
        prov = stamp(tier="VAULT_PROXY", built_from={})
        assert prov.tier == "VAULT_PROXY"


# ---------------------------------------------------------------------------
# built_from_mtimes tests
# ---------------------------------------------------------------------------

class TestBuiltFromMtimes:
    def test_returns_iso_for_existing_file(self) -> None:
        """built_from_mtimes returns an ISO-8601 string for an existing file."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".parquet") as f:
            tmp_path = f.name
        try:
            result = built_from_mtimes([tmp_path])
            assert tmp_path in result
            iso_str = result[tmp_path]
            # Must parse as ISO datetime
            from datetime import datetime
            dt = datetime.fromisoformat(iso_str)
            assert dt is not None
        finally:
            os.unlink(tmp_path)

    def test_skips_missing_path(self) -> None:
        """built_from_mtimes silently skips paths that do not exist."""
        missing = "/nonexistent/path/to/player_rates_abc123.parquet"
        result = built_from_mtimes([missing])
        assert missing not in result
        assert len(result) == 0

    def test_mixed_existing_and_missing(self) -> None:
        """built_from_mtimes includes existing and skips missing paths."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".parquet") as f:
            tmp_path = f.name
        missing = "/nonexistent/path_xyz.parquet"
        try:
            result = built_from_mtimes([tmp_path, missing])
            assert tmp_path in result
            assert missing not in result
        finally:
            os.unlink(tmp_path)

    def test_iso_has_timezone_info(self) -> None:
        """built_from_mtimes ISO strings include timezone offset (UTC)."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".parquet") as f:
            tmp_path = f.name
        try:
            result = built_from_mtimes([tmp_path])
            iso_str = result[tmp_path]
            # Must contain '+' or 'Z' timezone marker
            assert "+" in iso_str or "Z" in iso_str, (
                f"ISO string lacks timezone info: {iso_str!r}"
            )
        finally:
            os.unlink(tmp_path)

    def test_empty_list(self) -> None:
        """built_from_mtimes returns empty dict for empty input."""
        assert built_from_mtimes([]) == {}

    def test_multiple_existing_files(self) -> None:
        """built_from_mtimes handles multiple existing files correctly."""
        tmp_paths = []
        try:
            for _ in range(3):
                f = tempfile.NamedTemporaryFile(delete=False, suffix=".parquet")
                f.close()
                tmp_paths.append(f.name)
            result = built_from_mtimes(tmp_paths)
            assert len(result) == 3
            for p in tmp_paths:
                assert p in result
        finally:
            for p in tmp_paths:
                try:
                    os.unlink(p)
                except OSError:
                    pass
