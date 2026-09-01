"""Fixture-only tests for the generic mechanism -> trigger wiring."""
import re
from pathlib import Path

import pandas as pd

from scripts.platformkit.analytics_showcase import mechanism_foundry as foundry
from scripts.platformkit.analytics_showcase import mechanism_wiring as wiring
from scripts.platformkit.analytics_showcase.mechanism_exposure import parse_mechanisms

REQUIRED = ("mechanism_id", "trigger", "source_artifact", "as_of", "n", "verdict")
LEDGER = Path(__file__).resolve().parents[3] / "domains" / "basketball_nba" / "knowledge" / "mechanisms.md"


def _fake_root(tmp_path: Path) -> Path:
    """A minimal repo root: games.parquet plus one as-of column parquet."""
    domain = tmp_path / "data" / "domains" / "basketball_nba"
    domain.mkdir(parents=True)
    pd.DataFrame({"game_id": ["g1", "g2", "g3"], "date": ["2025-10-21", "2025-10-22", "2025-10-23"],
                  "home_team": ["AAA", "BBB", "CCC"], "away_team": ["BBB", "CCC", "AAA"],
                  "home_b2b": [0, 1, 0], "away_b2b": [0, 0, 1]}).to_parquet(domain / "games.parquet")
    # Every declared trigger source must exist, or column_exposures would be
    # silently partial; build each one from its own expression's column names.
    columns: dict[str, set] = {}
    for slug in wiring.TESTABLE:
        row = wiring.WIRING[slug]
        columns.setdefault(row["source"], set()).update(
            re.findall(r"[A-Za-z_][A-Za-z0-9_]*", row["expr"]))
    for source, names in columns.items():
        if (tmp_path / source).exists():
            continue
        frame = pd.DataFrame({"game_id": ["g1", "g2", "g3"]})
        for name in names:
            frame[name] = [10.0, 0.5, None]
        frame.to_parquet(tmp_path / source)
    return tmp_path


def setup_function() -> None:
    wiring._CACHE.clear()


def teardown_function() -> None:
    wiring._CACHE.clear()


def test_every_confirmed_mechanism_has_a_declared_wiring_row() -> None:
    slugs = [row["slug"] for row in parse_mechanisms(LEDGER)]
    assert slugs, "mechanism ledger parsed empty"
    assert wiring.rollup(slugs)["not_wired"] == []


def test_each_wiring_row_is_a_trigger_or_a_stated_data_reason() -> None:
    for slug, row in wiring.WIRING.items():
        if row["expr"]:
            assert row["source"] and isinstance(row["threshold"], float), slug
        else:
            assert len(row["reason"]) > 30, slug


def test_value_table_reads_the_declared_column_and_drops_nulls(tmp_path: Path) -> None:
    root = _fake_root(tmp_path)
    table = wiring.value_table("q1_slow_start_tendency_persistence", root)
    assert table == {"g1": 10.0, "g2": 0.5}


def test_value_table_refuses_an_outcome_bearing_trigger_expression(tmp_path: Path) -> None:
    wiring.WIRING["_probe"] = {"source": "data/domains/basketball_nba/games.parquet",
                               "expr": "home_win - 1", "threshold": 0.0}
    try:
        wiring.value_table("_probe", _fake_root(tmp_path))
    except AssertionError as error:
        assert "outcome" in str(error)
    else:  # pragma: no cover - the guard must fire
        raise AssertionError("outcome-bearing trigger expression was accepted")
    finally:
        wiring.WIRING.pop("_probe")


def test_column_exposures_respect_the_declared_threshold(tmp_path: Path) -> None:
    root = _fake_root(tmp_path)
    hits = wiring.column_exposures(["g1", "g2", "g3"], root)
    slug = "q1_slow_start_tendency_persistence"
    assert [h["slug"] for h in hits["g1"]].count(slug) == 1  # 10.0 >= 3.0
    assert slug not in [h["slug"] for h in hits["g2"]]  # 0.5 < 3.0
    assert slug not in [h["slug"] for h in hits["g3"]]  # value absent


def test_not_testable_rows_carry_every_required_field_and_run_no_trial() -> None:
    rows = [{"mechanism_id": "m1", "trigger": None, "source_artifact": "(none)",
             "planned": "NOT_TESTABLE", "reason": "no such column on disk", "as_of": None}]
    built = foundry.build(rows, run_trials=False)
    row = built["rows"][0]
    assert all(field in row for field in REQUIRED)
    assert row["verdict"] == "NOT_TESTABLE" and row["reason"] == "no such column on disk"
    assert built["edge_claimed"] is False and built["label"] == "DESCRIPTIVE_ONLY"


def test_low_coverage_trigger_falls_back_to_not_testable_with_a_measured_reason() -> None:
    rows = [{"mechanism_id": "m2", "trigger": "some_col", "source_artifact": "a.parquet",
             "planned": "NOT_TESTABLE", "as_of": "2026-04-12", "n_covered": 74, "n_corpus": 1156}]
    row = foundry.build(rows, run_trials=False)["rows"][0]
    assert row["verdict"] == "NOT_TESTABLE" and row["n"] == 74
    assert "74 of 1156" in row["reason"]


def test_build_is_idempotent_for_the_same_declared_rows() -> None:
    rows = [{"mechanism_id": "m1", "trigger": None, "source_artifact": "(none)",
             "planned": "NOT_TESTABLE", "reason": "absent ingredient, stated in data terms",
             "as_of": None}]
    first, second = foundry.build(rows, run_trials=False), foundry.build(rows, run_trials=False)
    assert first["rows"] == second["rows"] and first["counts"] == second["counts"]


def test_no_edge_or_roi_language_in_the_declared_reasons() -> None:
    banned = ("roi", "profit", "edge over", "bankroll", "+ev")
    text = " ".join(row.get("reason", "") for row in wiring.WIRING.values()).lower()
    assert not [word for word in banned if word in text]


# --- per-sport wiring (MLB and any future sport declared in WIRING_BY_SPORT) ---

MLB_LEDGER = LEDGER.parent.parent.parent / "mlb" / "knowledge" / "mechanisms.md"
FWER_LEDGER = Path(__file__).resolve().parents[3] / "data" / "cache" / "eval_gate" / "backtest_fwer.jsonl"


def test_every_confirmed_mlb_mechanism_has_a_declared_wiring_row() -> None:
    slugs = [row["slug"] for row in parse_mechanisms(MLB_LEDGER)]
    assert slugs, "MLB mechanism ledger parsed empty"
    assert wiring.rollup(slugs, "mlb")["not_wired"] == []


def test_no_duplicate_slugs_within_or_across_declared_sports() -> None:
    seen: dict[str, str] = {}
    for sport, rows in wiring.WIRING_BY_SPORT.items():
        for slug in rows:
            assert slug not in seen, "slug %s declared for both %s and %s" % (slug, seen.get(slug), sport)
            seen[slug] = sport


def test_every_declared_source_path_exists_or_the_row_is_not_testable() -> None:
    for sport, rows in wiring.WIRING_BY_SPORT.items():
        for slug, row in rows.items():
            if row["expr"]:
                assert (wiring.REPO_ROOT / row["source"]).exists(), "%s: %s" % (sport, row["source"])
            else:
                assert len(row["reason"]) > 30, "%s: %s" % (sport, slug)


def test_dry_run_appends_nothing_to_the_shared_fwer_ledger() -> None:
    before = (FWER_LEDGER.stat().st_mtime_ns, len(FWER_LEDGER.read_text(encoding="ascii").splitlines()))
    result = foundry.build(foundry.prereg_rows("mlb"), run_trials=False, sport="mlb")
    after = (FWER_LEDGER.stat().st_mtime_ns, len(FWER_LEDGER.read_text(encoding="ascii").splitlines()))
    assert before == after, "dry run touched the shared cumulative-K ledger"
    assert result["counts"]["queued_for_charged_run"] == sum(
        1 for row in result["rows"] if row["verdict"] == "PENDING")


def test_mlb_rows_are_all_declared_and_carry_a_verdict() -> None:
    result = foundry.build(foundry.prereg_rows("mlb"), run_trials=False, sport="mlb")
    assert result["counts"]["mechanisms"] == len(wiring.WIRING_BY_SPORT["mlb"])
    assert result["corpus"]["sport"] == "mlb"
    for row in result["rows"]:
        assert all(field in row for field in REQUIRED), row["mechanism_id"]
        assert row["verdict"] in ("NOT_TESTABLE", "PENDING")


def test_sport_scoped_out_paths_never_clobber_the_nba_artifacts() -> None:
    assert foundry.out_paths("basketball_nba") == (foundry.PREREG_JSON, foundry.OUT_JSON)
    prereg, out = foundry.out_paths("mlb")
    assert prereg != foundry.PREREG_JSON and out != foundry.OUT_JSON
    assert out.name == "mechanism_wiring_mlb.json"
