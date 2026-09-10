"""G375 rails: the sealed even stratified draw, the exclusion list, and the seal."""
import hashlib
from pathlib import Path

import pytest

from scripts.platformkit.tracking.g375_census import census, parse_unit, prefix_of
from scripts.platformkit.tracking.g375_rate import collect, kappa, parse_batch
from scripts.platformkit.tracking.g375_sample import draw, even_pick, quotas
from scripts.platformkit.tracking.g375_score import wilson

PREREG = (Path(__file__).resolve().parents[2] / "docs" / "evidence" / "tracking"
          / "g375_corpus_sport_purity_2026-09-10" / "g375_prereg_2026-09-10.md")


def test_seal_matches_the_bytes_above_it():
    """Q1: the sealed preregistration must still hash to the seal it carries."""
    raw = PREREG.read_bytes().replace(b"\r\n", b"\n")
    cut = raw.rfind(b"SEAL sha256")
    assert cut > 0, "preregistration carries no seal"
    assert raw[cut:].split()[2].decode() == hashlib.sha256(raw[:cut]).hexdigest()


def test_even_pick_is_never_a_head_slice():
    """A3/B7: the draw must span the whole stratum, not its first rows."""
    picked = even_pick(151, 45)
    assert len(picked) == len(set(picked)) == 45
    assert picked == sorted(picked)
    assert picked[0] > 0, "a draw starting at index zero is a head slice"
    assert picked[-1] >= 145, "the draw must reach the tail of the stratum"
    assert picked != list(range(45))
    assert even_pick(6, 6) == list(range(6))


def test_even_pick_rejects_an_impossible_quota():
    with pytest.raises(ValueError):
        even_pick(10, 11)


def test_quotas_hold_the_floor_and_the_total():
    sizes = {"fiba": 151, "bleague": 6, "nba": 126, "wnba": 65, "cba": 18}
    picked = quotas(sizes, total=200, floor=10)
    assert sum(picked.values()) == 200
    assert picked["bleague"] == 6, "a prefix smaller than the floor is taken whole"
    assert all(picked[key] <= sizes[key] for key in sizes)
    assert all(picked[key] >= min(10, sizes[key]) for key in sizes)


def test_draw_is_unique_and_covers_every_prefix():
    rows = [{"game_id": "%s-vid%07d_s90" % (tag, index), "prefix": tag,
             "video_id": "vid%07d" % index, "offset_s": "90", "source_duration": "130.000"}
            for tag, count in (("fiba", 60), ("nba", 40), ("wnba", 30)) for index in range(count)]
    picked = draw(rows, total=50)
    assert len({row["sheet_id"] for row in picked}) == 50
    assert len({row["game_id"] for row in picked}) == 50
    assert {row["prefix"] for row in picked} == {"fiba", "nba", "wnba"}
    assert picked[0]["target_tick_s"] == "155" and picked[0]["window_start_s"] == "153"


def test_census_lists_every_excluded_key_with_a_reason():
    """B3: an unfetchable key is named and excluded, never silently dropped."""
    rows = census([{"game_id": "0022400909_s1015", "sport": "nba", "source_duration": 130.0},
                   {"game_id": "wnba_06", "sport": "wnba", "source_duration": 130.0},
                   {"game_id": "fiba--x4DRmtYn4Q_s3530", "sport": "basketball",
                    "source_duration": 133.0},
                   {"game_id": "nbl-MrM2DBNLWc8_s90", "sport": "basketball",
                    "source_duration": 0}])
    verdicts = {row["game_id"]: (row["eligible"], row["ineligible_reason"]) for row in rows}
    assert verdicts["0022400909_s1015"] == ("0", "no_video_id_or_offset")
    assert verdicts["wnba_06"] == ("0", "no_video_id_or_offset")
    assert verdicts["nbl-MrM2DBNLWc8_s90"] == ("0", "no_source_duration")
    assert verdicts["fiba--x4DRmtYn4Q_s3530"] == ("1", "")
    assert parse_unit("fiba--x4DRmtYn4Q_s3530") == ("-x4DRmtYn4Q", "3530")


def test_prefix_rule_uses_the_tag_then_the_sport_field():
    assert prefix_of("fiba--x4DRmtYn4Q_s3530", "basketball") == "fiba"
    assert prefix_of("0022400909_s1015", "nba") == "nba"
    assert prefix_of("50pp-OqYVok_s2750", "nba") == "nba"
    assert prefix_of("ncaa_basketball_IB-_u4gW3ds_1080p", "ncaa_basketball") == "ncaa_basketball"


def test_rating_parser_keeps_five_labels_and_maps_the_rest_to_unknown():
    text = ("thinking about it\n"
            "sheet_0000.jpg,BASKETBALL_PLAY,,900\n"
            "sheet_0001.jpg,OTHER_SPORT,soccer,850\n"
            "sheet_0002.jpg,MAYBE_BASKETBALL,,500\n")
    parsed = parse_batch(text, "terra")
    assert parsed["sheet_0001"]["other_sport"] == "soccer"
    assert parsed["sheet_0002"]["label"] == "UNKNOWN"
    assert parsed["sheet_0002"]["raw_label"] == "MAYBE_BASKETBALL"
    assert parsed["sheet_0000"]["confidence_permille"] == "900"


def test_rating_collector_reads_committed_style_txt_batches(tmp_path):
    """B2: committed .txt archives reproduce parse_batch rows."""
    terra = "sheet_0001.jpg,BASKETBALL_PLAY,,900\n"
    sol = "sheet_0001.jpg,OTHER_SPORT,soccer,850\n"
    (tmp_path / "cx_g375_rater_terra_01.txt").write_text(terra, encoding="utf-8")
    (tmp_path / "cx_g375_rater_sol_01.txt").write_text(sol, encoding="utf-8")
    expected = sorted(
        [*parse_batch(terra, "terra").values(), *parse_batch(sol, "sol").values()],
        key=lambda row: (row["rater"], row["sheet_id"]),
    )
    assert collect(tmp_path) == expected


def test_kappa_and_wilson_are_the_textbook_values():
    assert kappa([("BASKETBALL_PLAY", "BASKETBALL_PLAY")] * 10) == pytest.approx(1.0)
    mixed = ([("BASKETBALL_PLAY", "BASKETBALL_PLAY")] * 8
             + [("OTHER_SPORT", "BASKETBALL_PLAY")] * 2)
    assert kappa(mixed) == pytest.approx(0.0, abs=1e-9)
    point, low, high = wilson(2, 100)
    assert point == pytest.approx(0.02)
    assert 0.0 < low < point < high < 0.1
    assert wilson(0, 0) == (0.0, 0.0, 0.0)
