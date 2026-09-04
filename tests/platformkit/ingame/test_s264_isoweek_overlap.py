"""S264 CONSTRUCT test: overlap counting and additive game-first-date keys.

Run: python -m pytest tests/platformkit/ingame/test_s264_isoweek_overlap.py -q
"""
from scripts.platformkit.ingame.s264_isoweek_overlap import (
    GAME_BLOCK,
    ISO_ALIAS,
    add_partition_keys,
    shared_game_ids,
    write_partition_table,
)


def test_shared_id_counter_and_game_first_date_repartition_are_idempotent():
    """n = 4 (CONSTRUCT): every row in a two-week, three-game fixture is listed."""
    rows = [
        {"game_id": "crosses", "ts": "2026-07-05T23:59:00Z"},
        {"game_id": "crosses", "ts": "2026-07-06T00:01:00Z"},
        {"game_id": "week27", "ts": "2026-07-04T12:00:00Z"},
        {"game_id": "week28", "ts": "2026-07-06T12:00:00Z"},
    ]
    first_dates = {"crosses": "2026-07-05", "week27": "2026-07-04", "week28": "2026-07-06"}
    keyed = add_partition_keys(rows, first_dates)
    assert shared_game_ids(keyed, ISO_ALIAS) == ["crosses"]
    assert shared_game_ids(keyed, GAME_BLOCK) == []
    assert [row[ISO_ALIAS] for row in keyed] == ["2026-W27", "2026-W28", "2026-W27", "2026-W28"]
    assert [row[GAME_BLOCK] for row in keyed] == ["2026-07-05", "2026-07-05", "2026-07-04", "2026-07-06"]
    assert add_partition_keys(keyed, first_dates) == keyed
    assert all(ISO_ALIAS not in row and GAME_BLOCK not in row for row in rows)


def test_additive_writer_preserves_existing_string_values(tmp_path):
    """n = 1 (CONSTRUCT): a full-precision source string must survive unchanged."""
    row = {"game_id": "g", "ts": "2026-07-05T23:59:00Z", "recal_prob": "0.5605439999999999"}
    keyed = add_partition_keys([row], {"g": "2026-07-05"})
    output = tmp_path / "partition.csv"
    write_partition_table(keyed, output)
    assert output.read_text(encoding="utf-8") == (
        "game_id,ts,recal_prob,iso_week_alias,game_id_block\n"
        "g,2026-07-05T23:59:00Z,0.5605439999999999,2026-W27,2026-07-05\n")
