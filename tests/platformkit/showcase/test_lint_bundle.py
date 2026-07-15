import json
from pathlib import Path

from scripts.platformkit.showcase.lint_bundle import lint_bundle


def _write(p: Path, name: str, obj) -> Path:
    f = p / name
    f.write_text(json.dumps(obj), encoding="utf-8")
    return f


def test_clean_bundle_passes(tmp_path: Path):
    _write(tmp_path, "manifest.json", {
        "counts": {"n": 3},
        "receipt": {"claim": "x matches close", "value": 0.5, "label": "MEASURED",
                    "artifact": "docs/JOB_EVIDENCE_PACKET.md"},
    })
    assert lint_bundle(tmp_path) == []


def test_banned_token_caught(tmp_path: Path):
    for tok in ("roi", "bankroll", "pnl", "profit", "edge_pct"):
        d = tmp_path / tok
        d.mkdir()
        _write(d, "bad.json", {"note": f"our {tok} today"})
        violations = lint_bundle(d)
        assert any(tok in v for v in violations), f"{tok} not caught: {violations}"


def test_retracted_number_caught(tmp_path: Path):
    d = tmp_path / "nums"
    d.mkdir()
    _write(d, "bad.json", {"value": "18.38"})
    violations = lint_bundle(d)
    assert any("18.38" in v for v in violations)

    d2 = tmp_path / "plus54"
    d2.mkdir()
    _write(d2, "bad.json", {"note": "in-play was +54% ceiling"})
    violations2 = lint_bundle(d2)
    assert any("+54%" in v for v in violations2)

    # not a false positive on a longer number containing the substring
    d3 = tmp_path / "safe"
    d3.mkdir()
    _write(d3, "ok.json", {"value": "10.1190"})
    assert lint_bundle(d3) == []


def test_receipt_missing_label_caught(tmp_path: Path):
    _write(tmp_path, "bad.json", {
        "receipt": {"claim": "x", "value": 1, "artifact": "some/path.py"}
    })
    violations = lint_bundle(tmp_path)
    assert any("label" in v for v in violations)


def test_malformed_json_caught(tmp_path: Path):
    f = tmp_path / "bad.json"
    f.write_text("{not valid json", encoding="utf-8")
    violations = lint_bundle(tmp_path)
    assert any("malformed JSON" in v for v in violations)


def test_secret_key_caught(tmp_path: Path):
    _write(tmp_path, "bad.json", {"api_key": "sk-1234567890abcdef1234567890abcdef"})
    violations = lint_bundle(tmp_path)
    assert any("secret-looking key" in v for v in violations)


def test_empty_secret_value_ok(tmp_path: Path):
    _write(tmp_path, "ok.json", {"api_key": ""})
    assert lint_bundle(tmp_path) == []
