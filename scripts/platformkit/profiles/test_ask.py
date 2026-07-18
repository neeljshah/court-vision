"""Per-file tests for the profiles ASK layer + weight hook.
Run: python -m pytest scripts/platformkit/profiles/test_ask.py -q
"""
import json

import pandas as pd

from scripts.platformkit.profiles import ask, weight_hook


def _make_profiles(tmp_path):
    rows = [
        # nba players -- two share the surname "James" for disambiguation
        dict(entity_id=1, entity_name="Luka Doncic", window="2023-24", attribute="scoring_usage",
             raw_value=32.4, percentile=98, rating_2k=97, n=70,
             ingredients=json.dumps({"pts": 32.4, "usg_pct": 0.37}),
             status="DESCRIPTIVE", sources="nba_api/boxscore"),
        dict(entity_id=1, entity_name="Luka Doncic", window="2024-25", attribute="scoring_usage",
             raw_value=33.9, percentile=99, rating_2k=98, n=65,
             ingredients=json.dumps({"pts": 33.9, "usg_pct": 0.39}),
             status="DESCRIPTIVE", sources="nba_api/boxscore"),
        dict(entity_id=2, entity_name="LeBron James", window="2024-25", attribute="rebounding",
             raw_value=8.1, percentile=80, rating_2k=85, n=60,
             ingredients=json.dumps({"reb": 8.1}), status="VALIDATED_MECHANISM",
             sources="nba_api/boxscore"),
        dict(entity_id=3, entity_name="James Harden", window="2024-25", attribute="playmaking",
             raw_value=9.2, percentile=95, rating_2k=93, n=62,
             ingredients=json.dumps({"ast": 9.2}), status="DESCRIPTIVE",
             sources="nba_api/boxscore"),
    ]
    p = tmp_path / "nba_player_profiles.parquet"
    pd.DataFrame(rows).to_parquet(p)
    return tmp_path


def test_exact_and_window_latest(tmp_path, monkeypatch):
    monkeypatch.setattr(ask, "PROFILES_DIR", str(_make_profiles(tmp_path)))
    out = ask.answer("Luka Doncic scoring usage")
    assert "Luka Doncic" in out and "scoring_usage" in out
    assert "2024-25" in out and "usg_pct = 0.39" in out  # latest window chosen
    assert "DESCRIPTIVE -- computed fact" in out


def test_window_override(tmp_path, monkeypatch):
    monkeypatch.setattr(ask, "PROFILES_DIR", str(_make_profiles(tmp_path)))
    out = ask.answer("doncic scoring", window="2023-24")
    assert "2023-24" in out and "usg_pct = 0.37" in out


def test_substring_match(tmp_path, monkeypatch):
    monkeypatch.setattr(ask, "PROFILES_DIR", str(_make_profiles(tmp_path)))
    out = ask.answer("harden playmaking")
    assert "James Harden" in out and "ast = 9.2" in out


def test_typo_difflib(tmp_path, monkeypatch):
    monkeypatch.setattr(ask, "PROFILES_DIR", str(_make_profiles(tmp_path)))
    out = ask.answer("doncicc scoring")  # surname typo -> difflib
    assert "Luka Doncic" in out


def test_multi_match_disambiguation(tmp_path, monkeypatch):
    monkeypatch.setattr(ask, "PROFILES_DIR", str(_make_profiles(tmp_path)))
    out = ask.answer("James")  # matches LeBron James AND James Harden
    assert "Multiple entities match" in out
    assert "LeBron James" in out and "James Harden" in out


def test_unknown_attribute_lists_available(tmp_path, monkeypatch):
    monkeypatch.setattr(ask, "PROFILES_DIR", str(_make_profiles(tmp_path)))
    out = ask.answer("Luka Doncic teleportation")
    assert "Available nba attributes" in out and "scoring_usage" in out


def test_attribute_listing(tmp_path, monkeypatch):
    monkeypatch.setattr(ask, "PROFILES_DIR", str(_make_profiles(tmp_path)))
    out = ask.list_attributes("nba")
    assert "scoring_usage" in out and "rebounding" in out and "[nba]" in out


def test_missing_profiles_graceful(tmp_path, monkeypatch):
    monkeypatch.setattr(ask, "PROFILES_DIR", str(tmp_path))  # empty dir
    out = ask.answer("anyone anything")
    assert "No profiles built yet" in out


def _make_soccer_dupe_profiles(tmp_path):
    rows = [
        # upstream data bug: a fallback row where entity_id == entity_name,
        # duplicating the real numeric-id row below (verified live, 2026-07
        # -17: 7 soccer teams carry exactly this pattern, e.g. Chelsea/
        # Everton/Arsenal each have BOTH a real numeric-string id AND a
        # placeholder id literally equal to the name).
        dict(entity_id="Chelsea", entity_name="Chelsea", window="2024-25", attribute="formation_primary_xg",
             raw_value=1.1, percentile=50, rating_2k=60, n=10,
             ingredients="{}", status="DESCRIPTIVE", sources="soccer/x"),
        dict(entity_id="33", entity_name="Chelsea", window="2024-25", attribute="clean_sheet_rate",
             raw_value=0.42, percentile=70, rating_2k=77, n=38,
             ingredients="{}", status="DESCRIPTIVE", sources="soccer/x"),
        # a genuinely DIFFERENT, non-colliding name (the real women's club) --
        # must never be affected by the dedup below.
        dict(entity_id="971", entity_name="Chelsea FCW", window="2024-25", attribute="clean_sheet_rate",
             raw_value=0.55, percentile=80, rating_2k=84, n=20,
             ingredients="{}", status="DESCRIPTIVE", sources="soccer/x"),
    ]
    p = tmp_path / "soccer_team_profiles.parquet"
    pd.DataFrame(rows).to_parquet(p)
    return tmp_path


def test_fallback_id_duplicate_does_not_create_false_ambiguity(tmp_path, monkeypatch):
    """2026-07-17 pod coverage-stress defect 4: 'What's Chelsea's clean sheet
    rate?' resolved AMBIGUOUS with two candidates that printed identically
    ('Chelsea (soccer)' twice) -- root cause was a duplicate profile row
    (entity_id == entity_name placeholder) shadowing the real numeric-id row,
    not a genuine two-team collision. Must now resolve to the real row."""
    monkeypatch.setattr(ask, "PROFILES_DIR", str(_make_soccer_dupe_profiles(tmp_path)))
    # possessive phrasing, matching the real defect report verbatim -- "chelsea's"
    # (with apostrophe) resolves "Chelsea" only via the full-name substring bonus,
    # never an exact "chelsea" token match, so it does NOT also tie "Chelsea FCW"
    # (a real different name that must stay untouched by the dedup).
    r = ask.answer_lookup("What's Chelsea's clean sheet rate this season?", "soccer")
    assert r["status"] == "ok"
    assert r["row"]["entity_id"] == "33"
    assert r["row"]["raw_value"] == 0.42


def test_genuinely_different_named_entities_still_ambiguous(tmp_path, monkeypatch):
    """The dedup must only drop a same-NAME fallback-id duplicate -- a real
    two-entity name collision (two different real, non-fallback ids sharing
    one name) still returns ambiguous with candidates."""
    rows = [
        dict(entity_id="10", entity_name="Park", window="2024-25", attribute="clean_sheet_rate",
             raw_value=0.3, percentile=40, rating_2k=55, n=10,
             ingredients="{}", status="DESCRIPTIVE", sources="soccer/x"),
        dict(entity_id="20", entity_name="Park", window="2024-25", attribute="clean_sheet_rate",
             raw_value=0.6, percentile=90, rating_2k=90, n=10,
             ingredients="{}", status="DESCRIPTIVE", sources="soccer/x"),
    ]
    p = tmp_path / "soccer_team_profiles.parquet"
    pd.DataFrame(rows).to_parquet(p)
    monkeypatch.setattr(ask, "PROFILES_DIR", str(tmp_path))
    r = ask.answer_lookup("Park clean sheet rate", "soccer")
    assert r["status"] == "ambiguous"
    assert len(r["candidates"]) == 2


def test_weight_hook_unweighted(tmp_path, monkeypatch):
    # synthetic registry: two nba attributes declare families, one soccer
    fake = {
        "nba": {"scoring_usage": {"description": "usage", "weight_ledger_family": "nba_usage_fam"},
                "rebounding": {"description": "reb", "weight_ledger_family": "nba_reb_fam"},
                "no_fam": {"description": "x"}},
        "soccer": {"xg": {"description": "expected goals", "weight_ledger_family": "soccer_xg_fam"}},
    }
    monkeypatch.setattr(weight_hook, "load_registry", lambda sp: fake.get(sp, {}))
    monkeypatch.setattr(weight_hook, "SPORTS", ["nba", "soccer"])
    ledger = tmp_path / "claim_weights.jsonl"
    ledger.write_text(json.dumps({"family": "nba_usage_fam"}) + "\n", encoding="utf-8")
    weighted, unweighted = weight_hook.coverage(ledger_path=str(ledger))
    w_fams = {f for _, _, f in weighted}
    u_fams = {f for _, _, f in unweighted}
    assert w_fams == {"nba_usage_fam"}
    assert u_fams == {"nba_reb_fam", "soccer_xg_fam"}


def test_weight_hook_missing_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(weight_hook, "load_registry",
                        lambda sp: {"a": {"weight_ledger_family": "fam1"}} if sp == "nba" else {})
    monkeypatch.setattr(weight_hook, "SPORTS", ["nba"])
    weighted, unweighted = weight_hook.coverage(ledger_path=str(tmp_path / "nope.jsonl"))
    assert not weighted and {f for _, _, f in unweighted} == {"fam1"}
