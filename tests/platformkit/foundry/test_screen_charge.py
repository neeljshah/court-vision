"""S234 construct checks for screen-width K charging without a real ledger."""
from __future__ import annotations

import importlib.util
from datetime import date, timedelta
from pathlib import Path

from scripts.platformkit.eval_gate import backtest_runner
from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.foundry.screen_charge import k_increment


ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / "scripts/platformkit/eval_gate/backtest_runner.py"


def _state(index: int) -> dict:
    stamp = date(2026, 1, 1) + timedelta(days=index)
    ts = stamp.isoformat() + "T12:00:00"
    return {
        "game_id": "construct-%02d" % index, "state_ts": ts,
        "home": "H%02d" % index, "away": "A%02d" % index,
        "features": {"x": index / 7.0},
        "feature_avail": {"x": stamp.isoformat() + "T00:00:00"},
        "devig_close_prob": 0.5, "truth_wp": 0.5, "outcome": index % 2,
    }


def _scratch_runner(tmp_path: Path):
    """Load only a tmp copy with the preregistered defaulted increment edit."""
    text = RUNNER.read_text(encoding="utf-8")
    old_signature = "trial_prereg_sha256: str | None = None) -> dict:"
    new_signature = "trial_prereg_sha256: str | None = None, k_increment: int = 1) -> dict:"
    assert old_signature in text and "cumulative_k(prior, 1)" in text
    edited = text.replace(old_signature, new_signature).replace(
        "cumulative_k(prior, 1)", "cumulative_k(prior, k_increment)")
    path = tmp_path / "backtest_runner_s234_scratch.py"
    path.write_text(edited, encoding="utf-8", newline="\n")
    spec = importlib.util.spec_from_file_location("s234_scratch_runner", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _charge(module, path: Path, increment: int | None = None) -> int:
    kwargs = {} if increment is None else {"k_increment": increment}
    row = module._charge_ledger(path, "s234:construct", "nba", "2026-01-01", "2026-01-08", **kwargs)
    return int(row["k_cumulative"])


def test_s234_three_construct_fixtures_use_shared_symmetric_cpcv(tmp_path: Path) -> None:
    """0, 1, and 200 screens retain the one-charge floor and repair the wide screen."""
    states = [_state(index) for index in range(8)]
    records = cpcv_evaluate(states, lambda train, test, inside: 0.5,
                            n_groups=4, n_test_groups=1, embargo_days=1)
    assert records and all(record["n_train"] >= 0 for record in records)

    scratch = _scratch_runner(tmp_path)
    expected = {0: 1, 1: 1, 200: 200}
    for screened_n, true_k in expected.items():
        current_k = _charge(backtest_runner, tmp_path / ("current_%d.jsonl" % screened_n))
        proposed_k = _charge(scratch, tmp_path / ("proposed_%d.jsonl" % screened_n),
                             k_increment(screened_n, 1))
        assert k_increment(screened_n, 1) == true_k
        assert current_k == 1
        assert proposed_k == true_k
