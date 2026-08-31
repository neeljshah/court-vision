"""Focused mocked coverage for the rotating Foundry runner."""
from __future__ import annotations

import json

import pandas as pd

from scripts.platformkit import foundry_runner as runner


def test_runner_rotates_configs_appends_ledger_and_survives_failures(tmp_path, monkeypatch) -> None:
    summary_path = tmp_path / "foundry_runner.jsonl"
    ledger_path = tmp_path / "foundry_ledger.jsonl"
    specs = [runner.foundry.SignalSpec("one", "nba", "row", "none", "one"),
             runner.foundry.SignalSpec("two", "nba", "row", "none", "two")]
    matrix = pd.DataFrame({"gameDate": pd.date_range("2024-01-01", periods=12), "minutes": range(12)})
    seen_embargoes: list[int] = []

    monkeypatch.setattr(runner, "SUMMARY_PATH", summary_path)
    monkeypatch.setattr(runner, "build_minutes_matrix", lambda: (matrix, specs))
    monkeypatch.setattr(runner, "expanding_folds", lambda frame, folds: [(folds, folds)])

    def evaluate(frame, target, spec, folds):
        seen_embargoes.append(runner.foundry.EMBARGO_BLOCKS)
        with ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"signal": spec.name}) + "\n")
        if spec.name == "two":
            raise RuntimeError("bad signal")
        return {"grade": "WEAK"}

    monkeypatch.setattr(runner.foundry, "evaluate_signal", evaluate)
    monkeypatch.setattr(runner.foundry, "combine_pool", lambda *args: (_ for _ in ()).throw(RuntimeError("bad pool")))
    results = runner.run(max_passes=6, sleep_seconds=0)

    assert {(item["pass_config"]["n_folds"], item["pass_config"]["embargo_blocks"]) for item in results} == set(runner.PASS_CONFIGS)
    assert len(ledger_path.read_text(encoding="utf-8").splitlines()) == 12
    lines = [json.loads(line) for line in summary_path.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 6
    assert all(line["n_signals"] == 2 and line["pool_delta"] is None for line in lines)
    assert seen_embargoes == [config[1] for config in runner.PASS_CONFIGS for _ in specs]
