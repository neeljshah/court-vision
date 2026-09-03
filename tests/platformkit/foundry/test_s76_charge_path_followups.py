"""S76 construct: one real T2 DRY charge covers cache, seal, clustering, and archive evidence."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from scripts.platformkit.eval_gate import backtest_runner
from scripts.platformkit.foundry import tiers
from scripts.platformkit.foundry.grammar import Hypothesis
from scripts.platformkit.foundry.screen_predictor import RealScreenPredictor

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "docs/evidence/harness/FACTORY_TIERS_SPEC_2026-09-03.md"
TRIAL_SEAL = "7125552f4c772e15c05057a5beaf460b1dc152496007cd20ea14c521f893cc30"
EXPECTED_LEDGER = ROOT / "docs/evidence/harness/S76_charge_path_followups_2026-09-04_ledger.json"
EXPECTED_ARCHIVE = ROOT / "docs/evidence/harness/S76_charge_path_followups_2026-09-04_archive.json"


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):  # noqa: ANN001 - datetime's compatibility signature
        return cls(2026, 9, 4, tzinfo=tz)


def _states(unit: str, offset: int) -> list[dict]:
    base, rows = date(2025, 1, 6), []
    for index in range(48):
        day = base + timedelta(days=index * 7)
        label = int(index % 2 == 0)
        rows.append({
            "game_id": "%s-%03d" % (unit, index), "corpus_unit": unit,
            "state_ts": "%sT12:00:00" % day.isoformat(), "game_date": day.isoformat(),
            "home": "H%02d" % ((index + offset) % 6), "away": "A%02d" % ((index + offset + 2) % 6),
            "div": "D%d" % (index % 3), "outcome": label, "devig_close_prob": 0.5,
            "features": {"p_ref": 0.5, "signal_asof": float(label)},
            "feature_avail": {"p_ref": "%sT00:00:00" % day, "signal_asof": "%sT00:00:00" % day},
        })
    return rows


def _run_dry(tmp_path: Path, monkeypatch) -> tuple[dict, dict, tiers.TierResult]:
    monkeypatch.setattr(backtest_runner, "datetime", _FrozenDateTime)
    all_states = _states("unit_a", 0) + _states("unit_b", 3)
    rule = tiers.PromotionRule.from_spec(SPEC)
    partition = tiers.partition_corpus(all_states, seed=rule.partition_seed)
    verdict = [state for state in all_states if state["game_id"] in partition.verdict_ids]
    result = tiers.run_tier(
        Hypothesis("soccer", "signal_asof", "raw", (), frozenset(), "pregame", "total", "soccer_gate"),
        "T2", states=verdict, predict_fn=RealScreenPredictor("signal_asof"),
        ledger_path=tmp_path / "backtest_fwer.jsonl", partition=partition, rule=rule,
        family="soccer_gate", screened_n=1, trial_prereg_sha256=TRIAL_SEAL,
    )
    ledger = (tmp_path / "backtest_fwer.jsonl").read_bytes()
    archive = json.dumps(result.archive, allow_nan=False, indent=2, sort_keys=True).encode("ascii")
    (tmp_path / "dry_ledger.json").write_bytes(ledger)
    (tmp_path / "dry_archive.json").write_bytes(archive)
    return json.loads(ledger), result.archive, result


def test_s76_dry_charge_path_followups(tmp_path, monkeypatch) -> None:
    """All four S76 constructs run through `tiers.run_tier` with a temporary ledger only."""
    row, archive, result = _run_dry(tmp_path, monkeypatch)
    fits = archive["fits"]
    # (a) CPCV's 28 distinct path train sets each received a fresh real predictor fit.
    assert len(fits) == 28
    assert len({fit["train_sha256"] for fit in fits}) == len(fits)
    # (b) Preserve the tier pin and add the distinct per-trial seal on the temporary ledger row.
    assert row["prereg_sha256"] == tiers.PromotionRule.from_spec(SPEC).prereg_sha256
    assert row["trial_prereg_sha256"] == TRIAL_SEAL
    # (c) Keep division primary and expose the companion home-team effective-n / DM view.
    assert result.cluster_key == "div"
    assert set(archive["cluster_metrics"]) == {"div", "home"}
    assert archive["cluster_metrics"]["div"]["cluster_key"] == "div"
    assert archive["cluster_metrics"]["home"]["cluster_key"] == "home"
    assert archive["cluster_metrics"]["home"]["n_eff"] > 0.0
    # (d) Q9 archive contains one paired loss differential for every scored event.
    assert result.archive is not None and len(archive["differential"]) == result.n
    # S76 reproduction: deterministic fixture bytes equal the committed evidence copies.
    assert (tmp_path / "dry_ledger.json").read_bytes() == EXPECTED_LEDGER.read_bytes()
    assert (tmp_path / "dry_archive.json").read_bytes() == EXPECTED_ARCHIVE.read_bytes()


def test_s76_ledger_append_preserves_existing_terminator(tmp_path) -> None:
    """An additive charge retains either existing JSONL row terminator."""
    for name, terminator in (("lf", b"\n"), ("crlf", b"\r\n")):
        ledger = tmp_path / (name + ".jsonl")
        ledger.write_bytes(b'{"k_cumulative": 1}' + terminator)
        backtest_runner._charge_ledger(ledger, "s76:terminator", "soccer", "2025-01-01", "2025-01-02")
        rows = ledger.read_bytes().splitlines(keepends=True)
        assert len(rows) == 2 and all(row.endswith(terminator) for row in rows)
