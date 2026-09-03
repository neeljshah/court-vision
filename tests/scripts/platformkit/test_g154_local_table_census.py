"""Focused checks for the G154 exhaustive local census utility."""

from pathlib import Path

from scripts.platformkit.g154_local_table_census import census_root, write_census


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(content, encoding="utf-8")


def test_g154_preserves_first_blocker_order_and_denominators(tmp_path: Path) -> None:
    root = tmp_path / "tracking"
    _write(root / "0022500001" / "tracking_data.csv", "frame,track_id,cls,x,y\n0,1,player,1,2\n")
    _write(root / "mlb_sample" / "tracking_data.csv", "frame,track_id,cls,x,y,coordinate_space\n0,1,player,100,200,image_px\n")
    tennis_rows = "\n".join(f"{frame},1,player,{frame},2,court_feet" for frame in range(31))
    _write(root / "G83_tennis_valid" / "tracking_data.csv", "frame,track_id,cls,x,y,coordinate_space\n" + tennis_rows + "\n")
    _write(root / "failclosed_smoke" / "tracking_data.csv", "frame,track_id,cls,x,y\n")

    rows = census_root(root)
    blockers = {row.table: row.first_blocker for row in rows}
    assert blockers == {
        "0022500001": "missing_required_coordinate_or_schema",
        "G83_tennis_valid": "reaches_gate",
        "failclosed_smoke": "unknown_sport_routing",
        "mlb_sample": "coordinate_contract_rejection",
    }
    output = tmp_path / "output"
    write_census(rows, output)
    summary = (output / "bucket_summary.csv").read_text(encoding="utf-8")
    assert "reaches_gate,1,4,0.250000" in summary
    assert "other,2,4,0.500000" in summary
