from datetime import datetime, timezone

from scripts.platformkit.ingame import mlb_book_capture as capture


class StubClient:
    def __init__(self):
        self.n_429 = 0
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        return {"orderbook_fp": {"yes_dollars": [["0.30", "2"], ["0.40", "3"]],
                                 "no_dollars": [["0.40", "4"], ["0.50", "5"]]}}


def test_capture_writes_complete_ladder_and_paper_cell(tmp_path):
    client = StubClient()

    def live_games(_client, _date, _state):
        return [{"game_pk": "123", "ticker": "KXMLBGAME-26SEP011200LADSF",
                 "game_state": {"ts": "2026-09-01T12:00:00.000000Z", "inning": 4}}]

    out = capture.capture_once(client=client, now=datetime(2026, 9, 1, tzinfo=timezone.utc),
                                live_games_fn=live_games, output=tmp_path / "books.jsonl")
    row = out["rows"][0]
    assert row["yes_ladder"] == [["0.30", "2"], ["0.40", "3"]]
    assert row["no_ladder"] == [["0.40", "4"], ["0.50", "5"]]
    assert row["top_of_book_depth"] == 8.0
    assert row["src_ts"] == "2026-09-01T12:00:00.000000Z"
    assert out["cell_table"] == [{"game_pk": "123", "inplay_snapshots": 1,
                                   "median_top_of_book_depth": 8.0,
                                   "pre_registered_unit": 1.0, "depth_threshold": 5.0,
                                   "cell": "NOT_YET"}]


def test_local_archive_is_scratch_and_429_doubles_cadence(tmp_path):
    client = StubClient()
    def rate_limited(_client, _date, _state):
        client.n_429 += 1
        return []

    out = capture.capture_once(client=client, now=datetime(2026, 9, 1, tzinfo=timezone.utc),
                                live_games_fn=rate_limited, output=tmp_path / "books.jsonl")
    assert out["n_429"] == 1
    assert out["cadence_sec"] == 10.0
    assert capture.archive_path(datetime(2026, 9, 1, tzinfo=timezone.utc), {}) == capture.SCRATCH_ARCHIVE / "2026-09-01.jsonl"
    assert capture.live_archive_enabled({"CV_CAPTURE_POD": "1", "CV_MLB_BOOK_ARCHIVE_LIVE": "1"})
