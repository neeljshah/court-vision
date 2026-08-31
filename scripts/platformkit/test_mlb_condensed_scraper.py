"""Offline tests for the MLB condensed-game CDN scraper.

Run: python -m pytest scripts/platformkit/test_mlb_condensed_scraper.py -q
"""
from scripts.platformkit.mlb_condensed_scraper import build_queue, extract_mp4_urls


HTML = '''
<article title="Tigers at Guardians condensed game">
  <video src="https://mlb-cuts-diamond.mlb.com/FORGE/2026/2026-08/30/a1b2c3d4e5f6-asset_1280x720_59_16000K.mp4"></video>
  <video src="https://mlb-cuts-diamond.mlb.com/FORGE/2026/2026-08/30/a1b2c3d4e5f6-asset_1280x720_59_4000K.mp4"></video>
</article>
<article aria-label="Mets at Marlins condensed game">
  <video src="https://mlb-cuts-diamond.mlb.com/FORGE/2026/2026-08/29/fedcba987654-asset_1280x720_59_4000K.mp4"></video>
</article>
'''


def test_extract_dedupe_and_build_queue() -> None:
    """Three embedded URLs yield two direct jobs, favoring 4000K per game."""
    records = extract_mp4_urls(HTML)

    assert len(records) == 3
    assert records[0]["date"] == "2026-08-30"
    assert records[0]["variant"] == "16000K"
    assert records[0]["game_hint"] == "Tigers at Guardians condensed game"

    queue = build_queue(records)

    assert len(queue) == 2
    assert queue[0] == {
        "sport": "baseball",
        "game_id": "mlb_2026-08-30_a1b2c3d4",
        "url": "https://mlb-cuts-diamond.mlb.com/FORGE/2026/2026-08/30/a1b2c3d4e5f6-asset_1280x720_59_4000K.mp4",
        "format": "direct",
    }
    assert queue[1]["game_id"] == "mlb_2026-08-29_fedcba98"
