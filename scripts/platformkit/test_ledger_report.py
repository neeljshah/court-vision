import json

from scripts.platformkit.ledger_report import report


def test_report_combines_ledger_and_json(tmp_path, capsys):
    (tmp_path / "ledger.jsonl").write_text(json.dumps({
        "sport": "mlb", "passed": True, "report": {
            "ball_valid_pct": 80, "coverage_pct": 90}}) + "\n")
    folder = tmp_path / "nba"
    folder.mkdir()
    (folder / "one.json").write_text(json.dumps({
        "sport": "nba", "passed": False, "ball_valid_pct": 70,
        "coverage_pct": 80}))
    result = report(tmp_path)
    assert result["mlb"]["n"] == 1 and result["mlb"]["pass_rate"] == 1
    assert result["nba"]["median_coverage_pct"] == 80
    assert json.loads((tmp_path / "scoreboard.json").read_text()) == result
    assert "SPORT" in capsys.readouterr().out
