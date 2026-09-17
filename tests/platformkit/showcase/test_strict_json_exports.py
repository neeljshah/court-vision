import json
import math

import pytest

from scripts.platformkit.analytics_showcase import mechanism_ledger_export as ledger
from scripts.platformkit.analytics_showcase import stage_webapp_assets as stager


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_export_mechanism_normalizes_non_finite_p(value):
    exported = ledger.export_mechanism({"p": value})

    assert exported["p"] is None
    assert json.dumps(exported, allow_nan=False)


@pytest.mark.parametrize("row, expected", [({}, None), ({"p": None}, None),
                                             ({"p": 0}, 0), ({"p": 0.0}, 0.0),
                                             ({"p": 0.25}, 0.25)])
def test_export_mechanism_preserves_valid_p_semantics(row, expected):
    assert ledger.export_mechanism(row)["p"] == expected


def test_stage_rejects_non_finite_json_without_overwriting(monkeypatch, tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    images = tmp_path / "images"
    source.mkdir()
    destination.mkdir()
    existing = destination / "artifact.json"
    existing.write_text('{"status": "good"}', encoding="utf-8")
    (source / "artifact.json").write_text('{"p": NaN}', encoding="utf-8")

    monkeypatch.setattr(stager, "_OUT", source)
    monkeypatch.setattr(stager, "_DATA_DST", destination)
    monkeypatch.setattr(stager, "_IMG_DST", images)

    with pytest.raises(ValueError, match="Out of range float values"):
        stager.stage()

    assert existing.read_text(encoding="utf-8") == '{"status": "good"}'


def test_check_rejects_non_finite_json(monkeypatch, tmp_path):
    (tmp_path / "artifact.json").write_text('{"p": NaN}', encoding="utf-8")
    monkeypatch.setattr(stager, "_OUT", tmp_path)

    with pytest.raises(ValueError, match="Out of range float values"):
        stager.check()


def test_producer_serializes_before_overwriting(monkeypatch, tmp_path):
    destination = tmp_path / "artifact.json"
    destination.write_text('{"status": "good"}', encoding="utf-8")
    monkeypatch.setattr(ledger, "OUT_JSON", str(destination))
    monkeypatch.setattr(ledger, "OUT_PNG", str(tmp_path / "artifact.png"))
    monkeypatch.setattr(ledger, "build", lambda: {"effect": math.nan})
    monkeypatch.setattr(ledger, "render_png",
                        lambda *_: pytest.fail("render must follow serialization"))
    monkeypatch.setattr("sys.argv", ["mechanism_ledger_export"])

    with pytest.raises(ValueError, match="Out of range float values"):
        ledger.main()

    assert destination.read_text(encoding="utf-8") == '{"status": "good"}'
