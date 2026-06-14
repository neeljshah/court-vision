"""test_brain_critic.py — Acceptance tests for scripts/platformkit/brain_critic.py.

Six spec cases: (1) clean passes; (2) duplicate fails; (3) dishonest leak flag fails;
(4) edge claim hard-fails; (5) uncited numerics fail; (6) verdict mismatch NON-BLOCKING.

Run: PYTHONPATH=<repo_root> python -m pytest tests/platform/test_brain_critic.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "platformkit"))

from brain_critic import (  # noqa: E402
    Critique, critique_batch, critique_finding,
    _DEFAULT_MIN_CITATION, _citation_coverage, _detect_edge_claims,
    _has_leak_markers, _is_leak_safe, _jaccard, _tokenize, _main,
)


def _clean() -> dict:
    """Well-formed finding: cited, leak-safe (no markers), no edge claims."""
    return {
        "claim": (
            "Walk-forward validation yields MAE 4.58 "
            "(scripts/prediction/player_props.py, as-of 2024-06-01, gate=SHIP)."
        ),
        "text": (
            "N=101770 player-games (data/pergame_dataset.parquet, as-of 2024-06-01, "
            "scripts/loop/gate.py:L42, gate=SHIP)."
        ),
        "construction": "expanding walk-forward on wf_* columns only",
        "leak_safe": True,
        "predicted_verdict": "SHIP",
        "actual_verdict": "SHIP",
        "citations": ["scripts/prediction/player_props.py", "data/pergame_dataset.parquet"],
    }


class TestClean:  # Case 1
    def test_passes(self):
        c = critique_finding(_clean())
        assert c.passes is True, c.reasons

    def test_all_flags_nominal(self):
        c = critique_finding(_clean())
        assert not c.is_duplicate
        assert c.leak_flag_honest
        assert not c.edge_claim_detected
        assert c.verdict_calibrated
        assert c.citation_coverage >= _DEFAULT_MIN_CITATION
        assert c.reasons == []


class TestDuplicate:  # Case 2
    _SAME_CLAIM = (
        "Walk-forward MAE 4.58 on held-out seasons "
        "(scripts/player_props.py as-of 2024-06-01 gate SHIP)."
    )

    def _existing(self):
        return [{"claim": self._SAME_CLAIM}]

    def _dup(self):
        return {"claim": self._SAME_CLAIM, "citations": ["scripts/player_props.py"]}

    def test_is_duplicate_true(self):
        c = critique_finding(self._dup(), existing=self._existing())
        assert c.is_duplicate is True

    def test_passes_false(self):
        c = critique_finding(self._dup(), existing=self._existing())
        assert c.passes is False

    def test_reason_mentions_sharpen(self):
        c = critique_finding(self._dup(), existing=self._existing())
        assert any("SHARPEN" in r or "DEDUP" in r for r in c.reasons)

    def test_distinct_claim_not_flagged(self):
        f = {"claim": "Soccer RMSE 1.2 (data/soccer.parquet as-of 2024-06-01)."}
        c = critique_finding(f, existing=self._existing())
        assert c.is_duplicate is False

    def test_batch_cross_dedup(self):
        findings = [{"claim": self._SAME_CLAIM}, {"claim": self._SAME_CLAIM}]
        results = critique_batch(findings)
        assert results[0].is_duplicate and results[1].is_duplicate


class TestLeakFlag:  # Case 3
    def _leaky(self):
        return {
            "claim": "MAE 1.34 (scripts/props.py as-of 2024-06-01).",
            "construction": "Fit on in-season split of 2023-24 schedule.",
            "leak_safe": True,
            "text": "N=50000 (data/pergame_dataset.parquet as-of 2024-06-01).",
            "citations": ["data/pergame_dataset.parquet"],
        }

    def test_leak_flag_honest_false(self):
        c = critique_finding(self._leaky())
        assert c.leak_flag_honest is False

    def test_passes_false(self):
        assert critique_finding(self._leaky()).passes is False

    def test_reason_mentions_leak(self):
        c = critique_finding(self._leaky())
        assert any("LEAK" in r.upper() for r in c.reasons)

    def test_lookahead_caught(self):
        f = dict(self._leaky())
        f["construction"] = "uses lookahead information from game outcomes"
        assert critique_finding(f).leak_flag_honest is False

    def test_honest_construction_passes(self):
        f = {
            "claim": "MAE 4.58 (scripts/props.py as-of 2024-06-01).",
            "construction": "expanding walk-forward wf_* columns only",
            "leak_safe": True,
            "text": "N=50000 (data/pergame.parquet as-of 2024-06-01).",
            "citations": ["scripts/props.py"],
        }
        assert critique_finding(f).leak_flag_honest is True


class TestEdgeClaim:  # Case 4
    def _edge(self):
        return {
            "claim": "+7% ROI beats the market (data/backtests.parquet as-of 2024-06-01).",
            "text": "Model is profitable with +7% ROI; beats the market consistently.",
            "construction": "walk-forward expanding window",
            "leak_safe": False,
        }

    def test_detected_true(self):
        assert critique_finding(self._edge()).edge_claim_detected is True

    def test_passes_false(self):
        assert critique_finding(self._edge()).passes is False

    def test_reason_mentions_edge(self):
        c = critique_finding(self._edge())
        assert any("EDGE" in r.upper() for r in c.reasons)

    @pytest.mark.parametrize("phrase,text", [
        ("roi",         "ROI analysis shows 5%"),
        ("profitable",  "strategy is profitable"),
        ("guaranteed",  "guaranteed returns"),
        ("proven edge", "proven edge on AST"),
    ])
    def test_specific_phrases(self, phrase, text):
        f = {"claim": text + " (scripts/f.py as-of 2024).", "text": text}
        assert critique_finding(f).edge_claim_detected is True

    def test_clean_text_no_edge(self):
        f = {"claim": "MAE 4.58 (scripts/props.py as-of 2024-06-01).", "text": "calibrated"}
        assert critique_finding(f).edge_claim_detected is False


class TestCitationCoverage:  # Case 5
    def _uncited(self):
        return {
            "claim": "MAE improved by 12.5% over baseline.",
            "text": "Model achieves MAE 4.58, RMSE 7.1, Brier 0.208 after 60 iterations.",
        }

    def test_coverage_below_threshold(self):
        c = critique_finding(self._uncited())
        assert c.citation_coverage < _DEFAULT_MIN_CITATION

    def test_passes_false(self):
        assert critique_finding(self._uncited()).passes is False

    def test_reason_mentions_citation(self):
        c = critique_finding(self._uncited())
        assert any("CITATION" in r.upper() for r in c.reasons)

    def test_no_numerics_vacuously_passes(self):
        f = {"claim": "Purely qualitative finding.", "text": "No numbers here."}
        assert critique_finding(f).citation_coverage == 1.0

    def test_well_cited_passes(self):
        cited = {
            "claim": "MAE 4.58 (scripts/props.py as-of 2024-06-01).",
            "text": "RMSE 7.1 (scripts/loop/gate.py as-of 2024-06-01).",
            "citations": ["scripts/props.py", "scripts/loop/gate.py"],
        }
        assert critique_finding(cited).citation_coverage >= _DEFAULT_MIN_CITATION


class TestVerdictCalibration:  # Case 6
    def _mismatched(self):
        return {
            "claim": "AST gate verdict SHIP (scripts/loop/gate.py as-of 2024-06-01).",
            "text": "MAE 1.34 N=101770 (data/pergame_dataset.parquet as-of 2024-06-01).",
            "construction": "expanding walk-forward wf_* columns",
            "leak_safe": True,
            "predicted_verdict": "REJECT",
            "actual_verdict": "SHIP",
            "citations": ["scripts/loop/gate.py", "data/pergame_dataset.parquet"],
        }

    def test_verdict_calibrated_false(self):
        assert critique_finding(self._mismatched()).verdict_calibrated is False

    def test_passes_not_blocked(self):
        """Verdict mismatch alone must NOT flip passes; all other checks pass."""
        c = critique_finding(self._mismatched())
        assert c.passes is True, f"verdict mismatch is non-blocking; reasons={c.reasons}"

    def test_reason_mentions_verdict(self):
        c = critique_finding(self._mismatched())
        assert any("VERDICT" in r.upper() for r in c.reasons)

    def test_matching_verdicts_calibrated(self):
        f = dict(self._mismatched())
        f["predicted_verdict"] = "SHIP"
        assert critique_finding(f).verdict_calibrated is True

    def test_verdict_plus_edge_still_fails(self):
        f = dict(self._mismatched())
        f["text"] += " Our model is profitable and has a proven edge."
        c = critique_finding(f)
        assert c.passes is False and c.edge_claim_detected is True


class TestHelpers:
    def test_tokenize(self): assert "hello" in _tokenize("Hello 42")
    def test_jaccard_identical(self): assert _jaccard(_tokenize("abc"), _tokenize("abc")) == 1.0
    def test_jaccard_disjoint(self): assert _jaccard(_tokenize("abc"), _tokenize("xyz")) == 0.0
    def test_leak_markers(self):
        assert _has_leak_markers("in-season split")
        assert _has_leak_markers("uses lookahead")
        assert not _has_leak_markers("expanding walk-forward")
    def test_is_leak_safe(self):
        assert _is_leak_safe({"leak_safe": True})
        assert _is_leak_safe({"leak_flag": "safe"})
        assert not _is_leak_safe({"leak_safe": False})
    def test_edge_detection(self):
        assert _detect_edge_claims("12% ROI on backtests")
        assert not _detect_edge_claims("calibration improves")
    def test_citation_no_nums(self): assert _citation_coverage({"claim": "qualitative"}) == 1.0


class TestCLI:
    def test_clean_exits_0(self, tmp_path):
        jl = tmp_path / "f.jsonl"
        jl.write_text(json.dumps(_clean()) + "\n", encoding="utf-8")
        assert _main([str(jl)]) == 0

    def test_edge_claim_exits_nonzero(self, tmp_path):
        f = {"claim": "profitable +7% ROI (data/f.parquet as-of 2024).", "text": "profitable"}
        jl = tmp_path / "f.jsonl"
        jl.write_text(json.dumps(f) + "\n", encoding="utf-8")
        assert _main([str(jl)]) != 0

    def test_json_flag_valid(self, tmp_path, capsys):
        jl = tmp_path / "f.jsonl"
        jl.write_text(json.dumps(_clean()) + "\n", encoding="utf-8")
        _main([str(jl), "--json"])
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list) and "passes" in data[0]

    def test_missing_file_exits_2(self):
        assert _main(["/nonexistent/brain_critic_test.jsonl"]) == 2

    def test_empty_jsonl_exits_0(self, tmp_path):
        jl = tmp_path / "empty.jsonl"
        jl.write_text("", encoding="utf-8")
        assert _main([str(jl)]) == 0
