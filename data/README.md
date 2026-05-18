# Data Directory

Large data files are not committed to the repository. Populate them locally:

```bash
# NBA API data (play-by-play, game logs, schedules, lineups)
python scripts/ingest_fetch.py --count 80

# Feature matrix (generated from NBA API + CV data)
python -m src.features.feature_engineering

# Model training (writes to data/models/)
python -m src.prediction.player_props --retrain
python -m src.prediction.win_probability --retrain
```

## Directory structure

| Directory | Contents | Source |
|-----------|----------|--------|
| `nba/` | Play-by-play, game logs, schedules, lineups | `nba_api` via ingest pipeline |
| `models/` | Trained model weights + metadata | Training scripts |
| `ball_yolo/` | Ball detection training images + labels | Manual annotation |
| `seeds/` | SQL seed data for PostgreSQL | Checked in |
| `videos/` | Game broadcast clips | yt-dlp via ingest pipeline |

Only `seeds/` and small model metadata files (registry, metrics, hyperparams) are version-controlled.
