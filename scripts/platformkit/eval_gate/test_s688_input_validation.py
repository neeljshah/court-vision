"""Construct tests for S688 input validation."""

import pytest

from scripts.platformkit.eval_gate.paired_tests import _read_csv, build_report, game_means
from scripts.platformkit.eval_gate.reliability_corp import brier_decomposition


def test_duplicate_required_csv_header_rejected(tmp_path):
    source = tmp_path / "losses.csv"
    source.write_text(
        "game_id,loss_ref,loss_cand,loss_ref\nG1,0.1,0.2,0.6\n",
        encoding="ascii",
    )
    with pytest.raises(ValueError, match="loss_ref"):
        _read_csv(str(source), ("game_id", "loss_ref", "loss_cand"))


def test_duplicate_reliability_csv_header_rejected(tmp_path):
    source = tmp_path / "reliability.csv"
    source.write_text("p,y,p\n0.1,0,0.9\n", encoding="ascii")
    with pytest.raises(ValueError, match="p"):
        _read_csv(str(source), ("p", "y"))


@pytest.mark.parametrize("bad_id", [None, "", " \t "])
def test_missing_game_id_rejected(bad_id):
    with pytest.raises(ValueError, match="game_id"):
        game_means([0.1, 0.2], [0.2, 0.1], ["G1", bad_id])


def test_blank_game_id_rejected_from_report_path():
    with pytest.raises(ValueError, match="game_id"):
        build_report([("G1", "0.1", "0.2"), (" ", "0.2", "0.1")])


@pytest.mark.parametrize("bins", [0, -1, True, 1.5])
def test_invalid_brier_bin_count_rejected(bins):
    with pytest.raises(ValueError, match="bins"):
        brier_decomposition([0.9] * 30, [0] * 30, bins=bins)


def test_invalid_bins_rejected_before_insufficient_data():
    with pytest.raises(ValueError, match="bins"):
        brier_decomposition([], [], bins=0)


def test_duplicate_game_id_header_rejected(tmp_path):
    source = tmp_path / "losses.csv"
    source.write_text(
        "game_id,loss_ref,loss_cand,game_id\nG1,0.1,0.2,G2\n",
        encoding="ascii",
    )
    with pytest.raises(ValueError, match="game_id"):
        _read_csv(str(source), ("game_id", "loss_ref", "loss_cand"))


def test_null_game_id_rejected_from_report_path():
    with pytest.raises(ValueError, match="game_id"):
        build_report([(None, "0.1", "0.2"), ("G2", "0.2", "0.1")])


def test_negative_bins_rejected_before_insufficient_data():
    with pytest.raises(ValueError, match="bins"):
        brier_decomposition([], [], bins=-1)
