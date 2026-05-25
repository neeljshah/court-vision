"""tests/test_dnp_set.py — tier3-11 (loop 5) DNP-aware projection set.

Five tests:
1. Boxscore JSON with N DNP players → aggregation parquet emits N rows.
2. DNP reason classification preserves coach-decision vs injury vs other.
3. dnp_for_game returns the expected list of DNP records.
4. build_pergame_dataset with PROP_PERGAME_INCLUDE_DNP=1 emits MORE rows
   than the default (back-compat baseline preserved).
5. build_pergame_dataset with the flag OFF emits identical row count to
   the cycle-48 baseline (no flag set / not set in env).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)


# ── 1 + 2: aggregation ───────────────────────────────────────────────────────


@pytest.fixture()
def tmp_boxscore_dir(tmp_path):
    """Fabricates 1 boxscore + 1 season_games file with 3 DNPs of mixed reasons.

    DNP rows fabricated:
      - "T. Test1" coach decision
      - "I. Hurt"  injury (Ankle Sprain)
      - "N. Cap"   inactive (G League assignment)
    Plus one PLAYED row (P. Played, 28:00 minutes) which should NOT be
    emitted as a DNP.
    """
    nba_dir = tmp_path / "data" / "nba"
    nba_dir.mkdir(parents=True)
    # boxscore_adv
    box = {
        "game_id": "0099900001",
        "players": [
            {"personid": 1001, "namei": "P. Played",  "teamtricode": "ABC",
             "minutes": "28:00", "comment": ""},
            {"personid": 2001, "namei": "T. Test1",   "teamtricode": "ABC",
             "minutes": "",      "comment": "DNP - Coach's Decision"},
            {"personid": 2002, "namei": "I. Hurt",    "teamtricode": "ABC",
             "minutes": "",      "comment": "Inactive - Injury/Illness - Right Ankle; Sprain"},
            {"personid": 2003, "namei": "N. Cap",     "teamtricode": "XYZ",
             "minutes": "",      "comment": "Inactive - G League - On Assignment"},
        ],
        "teams": [],
    }
    (nba_dir / "boxscore_adv_0099900001.json").write_text(json.dumps(box))
    # season_games_* for the date lookup
    season_games = {
        "v": 1,
        "rows": [{"game_id": "0099900001", "season": "9999-00",
                  "game_date": "9999-01-15"}],
    }
    (nba_dir / "season_games_9999-00.json").write_text(json.dumps(season_games))
    return nba_dir


def test_aggregate_emits_three_dnp_rows(tmp_boxscore_dir, monkeypatch, tmp_path):
    """Single-game boxscore with 3 DNPs + 1 played → parquet has 3 DNP rows."""
    from scripts import aggregate_dnp_rows as agg

    # Point the aggregator at the fixture cache
    monkeypatch.setattr(agg, "_NBA_CACHE", str(tmp_boxscore_dir))
    out_parquet = tmp_path / "dnp_rows.parquet"
    counts = agg.aggregate(str(out_parquet))

    assert counts["n_dnp_rows"] == 3, \
        f"expected 3 DNP rows (1 coach, 1 injury, 1 inactive); got {counts['n_dnp_rows']}"
    assert counts["n_games"] == 1


def test_dnp_reason_classification(tmp_boxscore_dir, monkeypatch, tmp_path):
    """Classifier maps coach -> coach_decision, injury -> injury, G League -> inactive."""
    from scripts import aggregate_dnp_rows as agg

    monkeypatch.setattr(agg, "_NBA_CACHE", str(tmp_boxscore_dir))
    out_parquet = tmp_path / "dnp_rows.parquet"
    agg.aggregate(str(out_parquet))

    import pandas as pd
    df = pd.read_parquet(out_parquet)
    by_reason = dict(df["dnp_reason"].value_counts())
    assert by_reason.get("coach_decision", 0) == 1, by_reason
    assert by_reason.get("injury", 0) == 1, by_reason
    assert by_reason.get("inactive", 0) == 1, by_reason


# ── 3: dnp_for_game accessor ────────────────────────────────────────────────


def test_dnp_for_game_returns_expected_list(tmp_boxscore_dir, monkeypatch, tmp_path):
    """dnp_for_game('0099900001') returns the 3 DNP records (in any order)."""
    from scripts import aggregate_dnp_rows as agg
    from src.data import dnp_set

    monkeypatch.setattr(agg, "_NBA_CACHE", str(tmp_boxscore_dir))
    out_parquet = tmp_path / "dnp_rows.parquet"
    agg.aggregate(str(out_parquet))

    # Point the loader at the fixture parquet + reset its cache.
    monkeypatch.setattr(dnp_set, "_DEFAULT_PATH", str(out_parquet))
    monkeypatch.setattr(dnp_set, "_CSV_FALLBACK",
                        str(out_parquet).replace(".parquet", ".csv"))
    monkeypatch.setattr(dnp_set, "_JSONL_FALLBACK",
                        str(out_parquet).replace(".parquet", ".jsonl"))
    dnp_set.reset_cache()

    recs = dnp_set.dnp_for_game("0099900001")
    assert len(recs) == 3
    names = sorted(r["player"] for r in recs)
    assert names == ["I. Hurt", "N. Cap", "T. Test1"]
    # game_date carried through
    for r in recs:
        assert r["game_date"] == "9999-01-15"
        assert r["expected_to_play"] is True or r["expected_to_play"] == 1


# ── 4: build_pergame WITH flag adds DNP rows ────────────────────────────────
# ── 5: build_pergame WITHOUT flag preserves baseline row count ──────────────


def test_build_pergame_with_dnp_flag_adds_rows(monkeypatch):
    """Setting include_dnp=True should add ~17k rows to the real dataset.

    Uses the REAL data/dnp_rows.parquet built by the aggregator. The off
    baseline is captured first; turning the flag on must yield a strict
    increase (>= 1 DNP row). Counts are not asserted exactly because the
    baseline dataset evolves cycle-to-cycle.
    """
    from src.prediction import prop_pergame as pp
    from src.data import dnp_set

    real_parquet = os.path.join(PROJECT_DIR, "data", "dnp_rows.parquet")
    if not os.path.exists(real_parquet):
        pytest.skip("data/dnp_rows.parquet not present — run "
                    "scripts/aggregate_dnp_rows.py first")
    dnp_set.reset_cache()

    # Smoke-check on a tiny slice — full build is multi-minute. We don't
    # need an exact row count, just the strict-increase invariant.
    # Use a temp gamelog dir with no JSONs so the gamelog loop emits zero
    # rows; this isolates the DNP-injection delta.
    with tempfile.TemporaryDirectory() as td:
        # Empty gamelog_dir → 0 gamelog rows. DNP injection should add
        # all rows from the real parquet.
        rows_off, _ = pp.build_pergame_dataset(gamelog_dir=td, include_dnp=False)
        rows_on,  _ = pp.build_pergame_dataset(gamelog_dir=td, include_dnp=True)

    n_off = len(rows_off)
    n_on = len(rows_on)
    assert n_on > n_off, f"include_dnp=True should add rows; got {n_off} vs {n_on}"
    # All injected rows should be DNP-flagged and have all-zero targets
    dnp_rows = [r for r in rows_on if r.get("is_dnp_row")]
    assert len(dnp_rows) == n_on - n_off
    for r in dnp_rows[:50]:
        for stat in pp.STATS:
            assert r[f"target_{stat}"] == 0.0
        assert r["date"]  # date is set


def test_build_pergame_default_flag_off_preserves_back_compat(monkeypatch, tmp_path):
    """No flag, no env var → 0 DNP rows injected (back-compat)."""
    from src.prediction import prop_pergame as pp

    # Empty gamelog dir so the gamelog loop yields 0 rows; the only way
    # rows can appear is via DNP injection — which must NOT happen by
    # default.
    monkeypatch.delenv("PROP_PERGAME_INCLUDE_DNP", raising=False)
    rows, _ = pp.build_pergame_dataset(gamelog_dir=str(tmp_path))
    assert rows == []
