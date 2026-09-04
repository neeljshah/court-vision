"""S275 construct: explicit basis consumers cannot follow a default flip."""
from pathlib import Path

from scripts.platformkit.eval_gate.calibration_report import build_report


_REPO = Path(__file__).resolve().parents[3]


def _records() -> list[dict]:
    return [
        {
            "event_id": "s275-%03d" % index,
            "corpus_unit": "A" if index < 120 else "B",
            "event_date": "2026-01-%02d" % ((index % 28) + 1),
            "p_base": 0.05 + (index % 10) * 0.09,
            "y": float(index % 3 == 0),
        }
        for index in range(240)
    ]


def test_explicit_basis_summaries_and_consumer_sites_are_flip_invariant() -> None:
    records = _records()
    positional = build_report(records, "synthetic", min_n=100)
    per_unit = build_report(
        records, "synthetic", min_n=100, order_by="event_date", unit_col="corpus_unit")

    assert positional["positional"] == per_unit["positional"]
    assert positional["per_unit"] == per_unit["per_unit"]
    assert positional["positional"]["ece_after"] == positional["ece_after"]
    assert per_unit["per_unit"]["ece_after"] == per_unit["ece_after"]

    resolver = (_REPO / "scripts/platformkit/answers/resolver_registry.py").read_text(encoding="utf-8")
    report_test = (_REPO / "scripts/platformkit/eval_gate/test_calibration_report.py").read_text(encoding="utf-8")
    scoreboard_test = (_REPO / "scripts/platformkit/answers/test_calibration_scoreboard_regex.py").read_text(encoding="utf-8")
    assert 'basis = v.get("per_unit", v)' in resolver
    assert 'report["per_unit"][key]' in report_test
    assert 'result["per_unit_ece"]' in scoreboard_test
