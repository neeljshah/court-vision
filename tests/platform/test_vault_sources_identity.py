"""tests/platform/test_vault_sources_identity.py — hermetic unit tests for the
densified build_identity / roster_aggregate / parse_* in vault_sources.py.
Synthetic data only — no live vault reads, no network.
Run: python -m pytest tests/platform/test_vault_sources_identity.py -q
"""
from __future__ import annotations
import re
import pytest
from scripts.platformkit.vault_sources import (
    _arch_stem, _style_one_liner, _vuln, build_identity,
    roster_aggregate, parse_position, parse_usage, parse_scheme_tags,
    parse_density, parse_composite, _ARCH_TENDENCY, _ARCH_VULNERABILITY_MAP,
)

# --- synthetic fixtures (no real player names) ----------------------------

_RECS = [
    {"archetype": "Role Player",      "text": "- **Position:** Guard\n- **Usage rate:** 12.5%",   "stem": "r1"},
    {"archetype": "Playmaking Guard", "text": "- **Position:** Guard\n- **Usage rate:** 22.0%",   "stem": "r2"},
    {"archetype": "Role Player",      "text": "- **Position:** Forward\n- **Usage rate:** 10.1%", "stem": "r3"},
    {"archetype": "Rebounding Big",   "text": "- **Position:** Center\n- **Usage rate:** 18.3%",  "stem": "r4"},
    {"archetype": "Stretch Big",      "text": "- **Position:** Forward\n- **Usage rate:** 14.7%", "stem": "r5"},
]
_SRC = (
    "**Dominant tag:** HELP DEFENSE\n**All tags:** HELP DEFENSE | SWITCH | RIM PROTECTION\n"
    "Composite Intensity | -0.25\ndata_density_tier: high\n"
)
_WL_RE = re.compile(r"\[\[[^\]]+\]\]")
# Betting tokens that must NOT appear in _Identity output (tactical words like "pick-and-roll" are ok)
_EDGE_RE = re.compile(r"\b(wager|kelly|roi|clv|sharp|odds|spread|profit)\b", re.I)


def _build(recs=None, src=None, team="TST") -> str:
    return build_identity(team, src if src is not None else _SRC,
                          recs if recs is not None else _RECS, "NBA")


def _links(out: str): return _WL_RE.findall(out)


# --- 1. Required sections -------------------------------------------------

def test_yaml_frontmatter():    out = _build(); assert "tags:" in out and "person-free" in out
def test_title():               out = _build(); assert "# TST" in out and "Style Identity" in out
def test_style_signature():     assert "**Style signature:**" in _build()
def test_style_one_liner():     assert "**Style one-liner:**" in _build()
def test_scheme_tags_line():    assert "**Scheme / driver tags:**" in _build()
def test_profile_composite():   out = _build(); assert "defensive composite z" in out
def test_profile_density():     out = _build(); assert "data density" in out
def test_tendencies_section():  assert "## Stylistic Tendencies" in _build()
def test_vulnerabilities_section(): assert "## Stylistic Vulnerabilities" in _build()
def test_archetype_dist_section(): assert "## Archetype Distribution" in _build()
def test_dist_table_tendency_col(): assert "| Archetype | Count | Share | Tendency |" in _build()
def test_all_archetypes_in_output():
    out = _build()
    for a in ("Role Player", "Playmaking Guard", "Rebounding Big", "Stretch Big"):
        assert a in out, f"Missing archetype {a}"


# --- 2. Wikilinks ---------------------------------------------------------

def test_sport_index_link():    assert "[[../../_Index|Sport Index]]" in _build()
def test_brain_moc_link():      assert "[[../../../_Index/_Brain|Brain MOC]]" in _build()
def test_archetypes_index_link(): assert "[[../../Archetypes/_Archetypes_Index|Archetypes]]" in _build()
def test_scheme_matrix_link():  assert "[[../../Schemes/_Scheme_Effects_Matrix|Schemes]]" in _build()
def test_top1_arch_link():      assert "[[../../Archetypes/role_player|Role Player]]" in _build()
def test_top2_arch_link():      assert "[[../../Archetypes/playmaking_guard|Playmaking Guard]]" in _build()
def test_minimum_six_wikilinks(): assert len(_links(_build())) >= 6
def test_no_scheme_link_without_tags():
    out = build_identity("NT", "", _RECS); assert "Schemes" not in " ".join(_links(out))
def test_no_recs_still_has_core_links():
    out = build_identity("NR", _SRC, [])
    assert "Sport Index" in " ".join(_links(out)) and "Brain MOC" in " ".join(_links(out))
def test_arch_links_use_stems():
    out = _build(); assert "[[../../Archetypes/role_player|" in out


# --- 3. Person-free constraints -------------------------------------------

_PLAYER_ID_WL = re.compile(r"\[\[.*?\d{4,}_[a-z_]+", re.I)
_SAFE_CAPS = {"Style Identity", "Stylistic Tendencies", "Stylistic Vulnerabilities",
              "Archetype Distribution", "Sport Index", "Brain MOC", "Scheme Effects"}


def test_no_player_id_wikilinks():
    assert not _PLAYER_ID_WL.search(_build()), "Player-ID wikilink found"


def test_no_edge_tokens():
    m = _EDGE_RE.search(_build())
    assert m is None, f"Edge token '{m.group()}' in _Identity output"


def test_no_vs_matchup_lines():
    vs_pat = re.compile(r"\b[A-Z][a-z]+\s+vs\.?\s+[A-Z][a-z]+")
    tactical = {"stretch", "switch", "drop", "zone", "man", "help", "balanced",
                "perimeter", "paint", "transition", "iso"}
    for m in vs_pat.finditer(_build()):
        left = m.group().split(" vs")[0].strip().lower()
        assert left in tactical, f"Person vs person pattern: '{m.group()}'"


def test_disclaimer_present():
    out = _build(); assert "markets efficient" in out or "calibration is not edge" in out


# --- 4. Content density ---------------------------------------------------

def test_one_liner_non_empty():
    m = re.search(r"\*\*Style one-liner:\*\*\s*(.+)", _build())
    assert m and len(m.group(1).strip()) > 10


def test_vulnerability_non_empty():
    m = re.search(r"## Stylistic Vulnerabilities\n+(.+)", _build())
    assert m and len(m.group(1).strip()) > 10


def test_tendencies_has_bullets():
    tend = _build().split("## Stylistic Tendencies")[-1]
    assert tend.count("- ") >= 1


def test_share_percentages_in_table():
    assert re.search(r"\|\s+\d+%\s+\|", _build()), "No share % column in table"


def test_output_longer_than_stub():
    assert len(_build().splitlines()) >= 25, "Output too short vs expected density"


# --- 5. Archetype intel helpers -------------------------------------------

def test_arch_stem_spaces():    assert _arch_stem("Role Player") == "role_player"
def test_arch_stem_hyphen():    assert _arch_stem("High-Usage Shot Creator") == "high_usage_shot_creator"
def test_tendency_role_player(): assert "spacing" in _ARCH_TENDENCY.get("role player", "")
def test_tendency_playmaking_big():
    v = _ARCH_TENDENCY.get("playmaking big", "")
    assert "hub" in v or "passing" in v or "screen" in v


def test_vulnerability_stretch_big():
    assert "rim protection" in _ARCH_VULNERABILITY_MAP.get("stretch big", "").lower()


def test_one_liner_deduplicates():
    liner = _style_one_liner(["Role Player", "Role Player"])
    assert liner.count("spacing-heavy") == 1


def test_vuln_fallback_for_unknown():
    result = _vuln(["Totally Unknown Archetype XYZ"])
    assert "Totally Unknown Archetype XYZ" in result


def test_arch_intel_tables_loaded():
    assert len(_ARCH_TENDENCY) >= 30 and len(_ARCH_VULNERABILITY_MAP) >= 30


# --- 6. Edge cases --------------------------------------------------------

def test_empty_recs_no_crash():
    out = build_identity("EMP", "", []); assert "# EMP" in out


def test_none_src_no_crash():
    out = build_identity("NS", None, _RECS); assert "## Archetype Distribution" in out


def test_single_archetype():
    recs = [{"archetype": "Dominant Two-Way Big",
             "text": "- **Position:** Center\n- **Usage rate:** 25%", "stem": "x"}]
    out = build_identity("OTYP", None, recs)
    assert "Dominant Two-Way Big" in out and "## Archetype Distribution" in out


def test_roster_aggregate_counts():
    agg = roster_aggregate(_RECS)
    assert agg["n"] == 5
    assert agg["arch_hist"]["Role Player"] == 2
    assert "%" in agg["style_signature"]


def test_parse_position():    assert parse_position("- **Position:** Guard") == "Guard"
def test_parse_usage():       assert parse_usage("- **Usage rate:** 18.5%") == "18.5%"
def test_parse_scheme_tags():
    tags = parse_scheme_tags(_SRC)
    assert "HELP DEFENSE" in tags and "SWITCH" in tags

def test_parse_density():     assert parse_density(_SRC) == "high"
def test_parse_composite():   assert parse_composite(_SRC) == "-0.25"
