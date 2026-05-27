try:
    from .video_fetcher import download_clip, list_downloaded, calibrate_from_video
except ImportError:
    # cv2 / heavy CV deps not installed (web/cloud environment).
    # video_fetcher is only needed for local CV pipeline work.
    pass

from .nba_stats import fetch_team_info, fetch_shot_chart, fetch_game_ids
