"""Deterministic fixtures for the public pregame calibration scorer."""
import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.score_vs_close import (
    COLUMNS, NOTE, main, score_csv, score_rows,
)


def fixture_rows(kind: str = "known", n: int = 2000) -> list[dict]:
    """Construct deterministic probabilities and outcomes, with unique games."""
    rng = np.random.default_rng(20261006)
    if kind == "noisy":
        pc = rng.uniform(0.2, 0.8, n)
        y = rng.binomial(1, pc)
        pm = pc + rng.normal(0, 0.002, n)
    else:
        y = rng.permutation(np.arange(n) % 2)
        correct = np.arange(n) % 10 != 0
        side = np.where(correct, y, 1 - y)
        pc, pm = np.where(side, 0.8, 0.2), np.where(side, 0.65, 0.35)
    return [dict(zip(COLUMNS, ["2026-01-01", f"game-{i:05d}", float(pm[i]),
                              float(pc[i]), "proportional", int(y[i])]))
            for i in range(n)]


def write_csv(path: Path, rows: list[dict]) -> Path:
    """Write only the public six-column fixture schema."""
    with path.open("w", newline="", encoding="ascii") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_noisy_copy_matches_close() -> None:
    result = score_rows(fixture_rows("noisy"))
    assert result["n"] == result["n_clusters"] == 2000
    assert abs(result["gap"]) < 0.001
    assert result["verdict"] == "MATCHES_CLOSE"


def test_known_brier_and_public_dm_parity() -> None:
    rows = fixture_rows()
    result = score_rows(rows)
    pm, pc, y = (np.array([r[k] for r in rows]) for k in ("p_model", "p_close_devig", "y"))
    dm = diebold_mariano((pm - y) ** 2 - (pc - y) ** 2, [r["match_id"] for r in rows])
    assert round(result["model_brier"], 4) == 0.1525
    assert round(result["close_brier"], 4) == 0.1000
    assert round(result["gap"], 4) == 0.0525
    assert result["dm_p"] == dm.p_value
    assert result["dm_stat"] == dm.dm_stat
    assert result["ci95"] == list(dm.ci95)
    assert result["mde"] == 1.429 * (dm.ci95[1] - dm.ci95[0]) / 2
    assert result["verdict"] == "TRAILS_CLOSE"
    for p, key in [(pm, "model_log_loss"), (pc, "close_log_loss")]:
        expected = -np.mean(np.log(np.where(y == 1, p, 1 - p)))
        assert result[key] == pytest.approx(expected)


def test_leak_mutant(tmp_path: Path) -> None:
    rows = fixture_rows()
    rows[17]["p_model"] = rows[17]["y"]
    result = score_csv(write_csv(tmp_path / "leak.csv", rows))
    assert result["reasons"].get("leak_signature") == 1
    assert result["status"] == "REFUSED"


def test_near_perfect_leak_refused() -> None:
    rows = fixture_rows()
    for i in (5, 6):
        rows[i]["p_model"] = 0.999 if rows[i]["y"] == 1 else 0.001
    rows[7]["p_model"] = 0.998 if rows[7]["y"] == 1 else 0.002  # outside 1e-3: not flagged
    result = score_rows(rows)
    assert result["status"] == "REFUSED"
    assert result["reasons"]["leak_signature"] == 2


def test_shuffle_mutant() -> None:
    rows = fixture_rows()
    before = score_rows(rows)
    shuffled = np.random.default_rng(2718).permutation([r["y"] for r in rows])
    after = score_rows([dict(r, y=int(y)) for r, y in zip(rows, shuffled)])
    assert abs(after["gap"] - before["gap"]) > 0.05
    assert after["verdict"] != before["verdict"]
    assert after["verdict"] == "BEATS_CLOSE"


def test_duplicate_mutant(tmp_path: Path) -> None:
    rows = fixture_rows()
    rows[3]["match_id"] = rows[2]["match_id"]
    result = score_csv(write_csv(tmp_path / "duplicate.csv", rows))
    assert result["status"] == "REFUSED"
    assert result["reasons"]["duplicated_match_id"] == 1


@pytest.mark.parametrize("n", [0, 499, 500])
def test_floor(n: int) -> None:
    result = score_rows(fixture_rows(n=n))
    if n < 500:
        assert result["verdict"] == "INSUFFICIENT"
        assert result["reasons"]["below_floor"] == n
    else:
        assert result["status"] == "OK"


@pytest.mark.parametrize("column", ["p_model", "p_close_devig"])
@pytest.mark.parametrize("value", [0, 1, -0.01, 1.01, float("nan"), float("inf"), "oops"])
def test_invalid_probability(column: str, value: object) -> None:
    rows = fixture_rows()
    rows[0][column] = value
    result = score_rows(rows)
    assert result["status"] == "REFUSED"
    assert result["reasons"]["p_outside_open_interval"] == 1


@pytest.mark.parametrize("value", [-1, 0.5, 2, float("nan"), "oops"])
def test_invalid_y(value: object) -> None:
    rows = fixture_rows()
    rows[0]["y"] = value
    assert score_rows(rows)["reasons"]["y_not_binary"] == 1


@pytest.mark.parametrize("column", ["p_model", "p_close_devig"])
def test_zero_brier_leak(column: str) -> None:
    rows = fixture_rows()
    for row in rows:
        row[column] = row["y"]
    assert score_rows(rows)["reasons"]["leak_signature"] == len(rows)


def test_devig_is_an_assertion() -> None:
    rows = fixture_rows()
    rows[0]["devig_method"] = "shin"
    assert score_rows(rows)["reasons"]["mixed_devig_method"] == 2000
    for row in rows:
        row["devig_method"] = "shin"
    assert score_rows(rows)["devig_method"] == "shin"
    assert score_rows(rows, "shin")["status"] == "OK"
    assert score_rows(rows, "proportional")["reasons"]["devig_method_mismatch"] == 2000
    rows[0]["devig_method"] = "unknown"
    assert score_rows(rows)["reasons"]["invalid_devig_method"] == 1


def test_reliability_counts_and_ties() -> None:
    rows = fixture_rows(n=2003)
    bins = score_rows(rows)["reliability"]
    assert bins == score_rows(list(reversed(rows)))["reliability"]
    for name, column in [("model", "p_model"), ("close", "p_close_devig")]:
        table = bins[name]
        assert len(table) == 10
        assert sum(b["count"] for b in table) == len(rows)
        assert max(b["count"] for b in table) - min(b["count"] for b in table) == 1
        assert [b["mean_p"] for b in table] == sorted(b["mean_p"] for b in table)
        for key, source in [("mean_p", column), ("observed_rate", "y")]:
            mean = sum(b[key] * b["count"] for b in table) / len(rows)
            assert mean == pytest.approx(np.mean([r[source] for r in rows]))


def test_cli_json_schema(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    path = write_csv(tmp_path / "rows.csv", fixture_rows())
    output = tmp_path / "result.json"
    assert main(["--csv", str(path), "--json-out", str(output)]) == 0
    stdout = capsys.readouterr().out
    assert stdout == output.read_text(encoding="ascii")
    result = json.loads(stdout)
    assert set(result) == {"schema", "status", "n", "n_clusters", "devig_method",
                           "model_brier", "close_brier", "gap", "gap_sign", "ci95",
                           "dm_stat", "dm_p", "mde", "mde_power", "model_log_loss",
                           "close_log_loss", "reliability", "verdict", "reasons", "note"}
    assert result["gap_sign"] == ("positive = model trails the close; "
                                  "dm_stat has the same sign as gap")
    assert result["note"] == NOTE
    assert set(result["reliability"]) == {"model", "close"}
    assert set(result["reliability"]["model"][0]) == {"mean_p", "observed_rate", "count"}
    assert "NaN" not in stdout and "Infinity" not in stdout


def test_cli_refusal_exit_three(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "short.csv", fixture_rows(n=499))
    output = tmp_path / "refusal.json"
    proc = subprocess.run([sys.executable, "-m", "scripts.platformkit.eval_gate.score_vs_close",
                           "--csv", str(path), "--json-out", str(output)],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 3
    assert json.loads(proc.stdout) == json.loads(output.read_text())
    assert json.loads(proc.stdout)["note"] == NOTE


def test_bad_csv(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    assert score_csv(path)["reasons"] == {"unreadable_csv": 1}
    path.write_text("wrong,columns\n", encoding="ascii")
    assert score_csv(path)["reasons"] == {"invalid_columns": 1}
    path.write_text(",".join(COLUMNS) + "\n2026-01-01,x,0.2,0.3,proportional\n", encoding="ascii")
    assert score_csv(path)["reasons"] == {"malformed_row": 1}


def test_reference_clip_and_identical_forecasts() -> None:
    rows = fixture_rows()
    for row in rows:
        # 1e-9 only on y=1 rows: clipped, yet far from y, so not a leak signature
        row["p_model"] = row["p_close_devig"] = 1e-9 if row["y"] == 1 else 0.5
    result = score_rows(rows)
    y = np.array([r["y"] for r in rows])
    assert result["model_brier"] == float(np.mean((np.where(y == 1, 1e-6, 0.5) - y) ** 2))
    assert result["ci95"] == [0, 0]
    assert result["dm_p"] == 1
    assert result["verdict"] == "MATCHES_CLOSE"
