import json

from scripts.platformkit import mlb_queue_refresh as mod


def test_refresh_dedupes_and_caps_pending(tmp_path, monkeypatch):
    path = tmp_path / "queue.json"
    path.write_text(json.dumps([{"game_id": "old", "status": "done"}] +
                               [{"game_id": f"p{i}"} for i in range(10)]))
    monkeypatch.setattr(mod, "fetch_page", lambda _: "html")
    monkeypatch.setattr(mod, "extract_mp4_urls", lambda _: [{"id": 1}])
    monkeypatch.setattr(mod, "build_queue", lambda _, limit: [{"game_id": "new"}])
    assert mod.refresh("url", path) == 0
    assert json.loads(path.read_text()) == [{"game_id": "old", "status": "done"}] + [{"game_id": f"p{i}"} for i in range(10)]

