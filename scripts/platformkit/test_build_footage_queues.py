import json

from scripts.platformkit.build_footage_queues import main


def test_build_footage_queues(tmp_path):
    main(tmp_path)
    for name in ("tennis", "wnba", "npb", "kbo"):
        entries = json.loads((tmp_path / f"footage_queue_{name}.json").read_text())
        assert len(entries) == 10
        assert all(set(entry) == {"sport", "game_id", "url", "format"} for entry in entries)
        assert all(entry["game_id"] == f"{name}_{i:02d}" for i, entry in enumerate(entries, 1))
