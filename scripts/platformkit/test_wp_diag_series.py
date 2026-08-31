"""Synthetic checks for raw-series max-loser WP auditing."""
import json

from scripts.platformkit.wp_diag_series import audit, load_records


def _record(game, model, market, outcome):
    return {"game_id": game, "sport": "mlb", "ts": "2026-07-01T12:00:00Z",
            "model_prob": model, "market_prob": market, "outcome": outcome}


def test_audit_splits_raw_probability_series_and_applies_density_control(tmp_path):
    fixture = tmp_path / "ticks.jsonl"
    rows = []
    for index in range(20):
        rows.append(_record("KXMLBGAME-LOSS", .40, .95, 0.0))
    for index in range(19):
        rows.append(_record("KXMLBGAME-THIN", .99, .99, 0.0))
    fixture.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    report = audit(load_records(tmp_path))
    assert report["raw_probability_fields"] == ["market_prob", "model_prob"]
    model = report["series"]["model_prob"]["by_sport"]["mlb"]
    market = report["series"]["market_prob"]["by_sport"]["mlb"]
    assert model["n_games"] == 2
    assert model["n_games_at_least_20_ticks"] == 1
    assert model["max_loser_wp"]["quantiles"]["75"] == .40
    assert market["max_loser_wp"]["quantiles"]["75"] == .95
