"""Per-file checks for the S675 multiplicity haircut (construct cases + a small null smoke)."""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest

from scripts.platformkit.eval_gate import multiplicity_nullcheck as nc
from scripts.platformkit.eval_gate.ledger import load_fwer
from scripts.platformkit.eval_gate.multiplicity_haircut import (
    BETTER, NOT_EVALUABLE, NOT_SEPARATED, deflate, haircut, holm, load_paired_series,
    trial_count_table)

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "reference_runs" / "s675_paired_losses_fixture.csv"
SOURCE = HERE.parents[2] / "docs/evidence/S202_two_way_neff_2026-09-04/nba_paired_losses.csv"
LEDGER = HERE / "reference_runs" / "fwer_backtest_ledger.jsonl"


def _arms(k=3, n=40, seed=5, shift=0.0):
    x = np.random.default_rng(seed).standard_normal((k, n))
    x[0] += shift
    ids = ["g%02d" % i for i in range(n)]
    return [{"name": "a%d" % j, "diffs": x[j].tolist(), "game_ids": ids,
             "sealed_verdict": "REJECT"} for j in range(k)]


def test_holm_matches_hand_computation():
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert holm([0.5, 0.001]) == pytest.approx([0.5, 0.002])


def test_not_evaluable_consumes_no_k_and_gets_no_p():
    arms = _arms() + [{"name": "none", "diffs": None, "game_ids": None},
                      {"name": "noids", "diffs": [0.1, 0.2], "game_ids": None}]
    rep = haircut(arms, n_bootstrap=99, seed=1)
    assert rep["family"]["k_declared"] == 5 and rep["family"]["k_evaluable"] == 3
    for row in rep["arms"][3:]:
        assert row["label"] == NOT_EVALUABLE
        assert row["raw_p"] is None and row["holm_p"] is None and row["romano_wolf_p"] is None


def test_zero_and_one_evaluable_arms_are_defined():
    empty = haircut([{"name": "x", "diffs": None, "game_ids": None}])
    assert empty["family"]["k_evaluable"] == 0 and empty["arms"][0]["label"] == NOT_EVALUABLE
    one = haircut(_arms(k=1, shift=1.0), n_bootstrap=99, seed=2)
    assert one["family"]["k_evaluable"] == 1 and one["arms"][0]["label"] == BETTER


def test_sealed_verdict_passthrough_and_inputs_unmutated():
    arms = _arms(k=4, shift=1.0)
    arms[1]["sealed_verdict"] = "BEHIND"
    before = copy.deepcopy(arms)
    rep = haircut(arms, n_bootstrap=99, seed=3)
    assert arms == before
    assert [r["sealed_verdict"] for r in rep["arms"]] == [a["sealed_verdict"] for a in before]
    assert rep["arms"][0]["label"] == BETTER and rep["arms"][0]["sealed_verdict"] == "REJECT"


def test_zero_variance_arm_is_never_better_and_stays_in_k():
    arms = _arms(k=2, shift=1.0)
    arms.append({"name": "flat", "diffs": [0.2] * 40, "game_ids": arms[0]["game_ids"]})
    rep = haircut(arms, n_bootstrap=99, seed=4)
    assert rep["family"]["k_evaluable"] == 3
    assert rep["arms"][2]["raw_p"] == 1.0 and rep["arms"][2]["label"] == NOT_SEPARATED


def test_equal_decimal_game_means_never_better_and_stay_in_k():
    arm = {"name": "flat", "diffs": [0.1] * 3, "game_ids": ["g0", "g1", "g2"]}
    rep = haircut([arm], n_bootstrap=99, seed=4)
    assert rep["family"]["k_evaluable"] == 1
    assert rep["arms"][0]["raw_p"] == 1.0
    assert rep["arms"][0]["label"] == NOT_SEPARATED


def test_misaligned_games_mark_spa_not_evaluable_without_error():
    arms = _arms(k=2, shift=2.0)
    arms[1]["game_ids"] = ["h%02d" % i for i in range(40)]
    rep = haircut(arms, n_bootstrap=99, seed=6)
    assert rep["family"]["aligned"] is False and rep["family"]["spa_status"] == NOT_EVALUABLE
    assert all(r["label"] == NOT_SEPARATED for r in rep["arms"])
    assert all(r["holm_p"] is not None and r["romano_wolf_p"] is not None for r in rep["arms"])


def test_row_duplication_inside_games_changes_nothing():
    arms = _arms(k=3, shift=0.4)
    dup = [{**a, "diffs": [v for v in a["diffs"] for _ in range(3)],
            "game_ids": [g for g in a["game_ids"] for _ in range(3)]} for a in arms]
    a, b = haircut(arms, n_bootstrap=99, seed=7), haircut(dup, n_bootstrap=99, seed=7)
    for x, y in zip(a["arms"], b["arms"]):
        assert x["raw_p"] == pytest.approx(y["raw_p"], abs=1e-12)
        assert x["romano_wolf_p"] == pytest.approx(y["romano_wolf_p"], abs=1e-12)
        assert x["n_games"] == y["n_games"] == 40


@pytest.mark.parametrize("line_ending", [b"\n", b"\r\n"], ids=["LF", "CRLF"])
def test_fixture_is_every_30th_source_row_and_loader_sign_is_base_minus_model(line_ending):
    source_bytes = SOURCE.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", line_ending)
    src = source_bytes.decode("ascii").splitlines()
    fix = FIXTURE.read_text(encoding="ascii").splitlines()
    assert fix[0] == src[0] and len(fix) == 61
    assert fix[1:] == [src[1 + i] for i in range(0, 1800, 30)]
    # The recorded provenance digest is for LF bytes on every platform.
    assert hashlib.sha256(source_bytes.replace(b"\r\n", b"\n")).hexdigest() == (
        "db28645de44429ee67d303b62b14932e1b0932ab210b042339622742178effa1")
    series = load_paired_series(str(FIXTURE), "event_id", "loss_base", "loss_recalibrated")
    assert len(series["header"]) == 12
    with FIXTURE.open(encoding="ascii", newline="") as fh:
        rows = list(csv.reader(fh))[1:]
    by_hand = [float(r[6]) - float(r[7]) for r in rows]
    stored = [float(r[8]) for r in rows]
    assert max(abs(a - b) for a, b in zip(series["diffs"], by_hand)) <= 1e-12
    assert max(abs(a + b) for a, b in zip(series["diffs"], stored)) <= 1e-12
    assert abs(np.mean(series["diffs"]) - math.fsum(by_hand) / 60) <= 1e-12
    rep = haircut([{"name": "recal_s05", **series}], n_bootstrap=99, seed=8)
    assert rep["family"]["k_evaluable"] == 1 and rep["arms"][0]["n_games"] == 60


def test_duplicated_header_column_is_refused():
    with pytest.raises(ValueError):
        load_paired_series(str(FIXTURE), "away_team", "loss_base", "loss_recalibrated")


def test_deflate_only_sharpe_like_with_golden_value():
    assert deflate("brier")["status"] == "NOT_APPLICABLE"
    assert deflate("log_loss", 0.3, 100, 10, 0.1)["status"] == "NOT_APPLICABLE"
    assert deflate("sharpe_like", 0.2, 101, 10, None)["status"] == NOT_EVALUABLE
    r0 = 0.05 * 1.538752730835173
    z = (0.2 - r0) * 10.0 / math.sqrt(1.0 + 0.5 * 0.04)
    golden = 0.5 * math.erfc(z / math.sqrt(2.0))
    assert deflate("sharpe_like", 0.2, 101, 10, 0.05)["deflated_p"] == pytest.approx(golden, abs=1e-9)
    ps = [deflate("sharpe_like", 0.2, 101, k, 0.05)["deflated_p"] for k in (1, 10, 100)]
    assert ps[0] < ps[1] < ps[2]


def test_trial_count_table_counts_families_via_aliases_and_k_at_launch():
    committed = load_fwer(LEDGER)
    t = trial_count_table(committed, launch_at="2026-09-01T20:32:05+00:00")
    assert t["k_total_rows"] == 2 and t["max_k_cumulative"] == 2 and t["k_at_launch"] == 1
    assert [g["k"] for g in t["groups"]] == [1, 1]
    extra = [{"at": "2026-09-02T00:00:00+00:00", "family": "ingame_mlb_arms", "k_cumulative": 7},
             {"at": "2026-09-03T00:00:00+00:00", "family": "ingame_arms_mlb", "k_cumulative": 9},
             {"at": "2026-09-04T00:00:00+00:00", "family": "ingame_mlb_clamp", "k_cumulative": 11}]
    t = trial_count_table(committed + extra)
    fam = [g for g in t["groups"] if g["group"] == "family:ingame_arms_mlb"]
    assert fam and fam[0]["k"] == 3 and t["max_k_cumulative"] == 11
    with pytest.raises(ValueError):
        trial_count_table(committed, launch_at="2026-09-01T20:32:05")
    # 19:00-05:00 is 00:00Z next day, AFTER a 23:00Z launch; a text compare says before.
    mixed = [{"at": "2026-09-01T19:00:00-05:00", "sport": "s", "predictor": "p"}]
    assert trial_count_table(mixed, launch_at="2026-09-01T23:00:00+00:00")["k_at_launch"] == 0


def test_trial_count_table_accepts_utc_z_timestamp():
    row = {"at": "2026-09-01T20:32:05Z", "sport": "s", "predictor": "p"}
    z = trial_count_table([row], launch_at="2026-09-01T20:32:05Z")
    offset = trial_count_table([{**row, "at": "2026-09-01T20:32:05+00:00"}],
                               launch_at="2026-09-01T20:32:05+00:00")
    assert z["k_at_launch"] == offset["k_at_launch"] == 1
    assert z["groups"][0]["first_at"] == row["at"]


def test_null_smoke_haircut_bites_where_raw_does_not():
    rows = [nc.run_family(nc.NOISE_SEED0 + s, 60) for s in range(20)]
    assert max(r["better"] for r in rows) <= nc.BAR_NOISE60_MAX
    assert max(r["raw"] for r in rows) > 3


def test_cli_smoke_emits_json_and_marks_non_acceptance(capsys):
    assert nc.main(["2"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["verdict"]["acceptance_run"] is False and out["settings"]["n_bootstrap"] == 199
