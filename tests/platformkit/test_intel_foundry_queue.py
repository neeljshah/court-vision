"""Construct checks for the additive S232 queue helper."""
from pathlib import Path

import pytest

from scripts.platformkit import intel_foundry_queue
from scripts.platformkit.foundry import catalogue, seed_queue
from scripts.platformkit.foundry.grammar import Hypothesis


def test_dry_run_counts_the_grammar_without_creating_scratch(monkeypatch, tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        '{"canonical_queue":"data/cache/eval_gate/hypotheses.sqlite","stores":['
        '{"id":"state","path":"data/cache/ingame/possession_states.parquet",'
        '"classification":"GLOB-REACHABLE"}]}', encoding="ascii")
    state = tmp_path / "data" / "cache" / "ingame" / "possession_states.parquet"
    state.parent.mkdir(parents=True)
    state.touch()
    expected = [
        Hypothesis("nba", "f1", "raw", (), frozenset(), "live_tick", "inplay"),
        Hypothesis("nba", "f2", "raw", (), frozenset(), "live_tick", "inplay"),
    ]

    def fake_hypotheses(*, entries=None, sport=None):
        assert entries == (catalogue.Entry(state, "nba"),)
        assert sport is None
        yield from expected

    monkeypatch.setattr(seed_queue, "hypotheses", fake_hypotheses)
    scratch = tmp_path / "scratch.sqlite"
    result = intel_foundry_queue.dry_run(manifest, scratch, tmp_path)

    assert result.hypotheses == len(expected)
    assert result.entries == (catalogue.Entry(state, "nba"),)
    assert not scratch.exists()


def test_dry_run_refuses_the_canonical_queue_and_fwer_append_parses(tmp_path):
    manifest = Path("docs/evidence/harness/S232_intel_foundry_queue_manifest_2026-09-04.json")
    with pytest.raises(ValueError, match="canonical"):
        intel_foundry_queue.dry_run(manifest, Path("data/cache/eval_gate/hypotheses.sqlite"))

    from scripts.platformkit.eval_gate.family_bars import _parse_families_spec

    frozen = Path("docs/evidence/harness/FWER_FAMILIES_SPEC_2026-09-03.md").read_text("ascii")
    appended = frozen + (
        "\n### fam: s232_parse_probe\n"
        "sport: nba\nhorizon: pregame\nmarket: ml\nfeatures: 1\nhypotheses: 9\n"
        "sources: test\nmembers: probe\n"
    )
    parsed = _parse_families_spec(appended, "memory:s232", "test-pin")
    assert parsed.get("s232_parse_probe").members == ("probe",)
