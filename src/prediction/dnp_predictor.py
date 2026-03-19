"""
dnp_predictor.py — Predict probability player is inactive (DNP) for a game.

Features: recent_min_avg (last 5 games), min_trend (slope), games_in_last_7,
          season_games_pct, age_flag

Training: reads all gamelog_full_{player_id}_{season}.json files.
          MIN=0 (or "0:00") rows are labeled DNP=1.
          Uses logistic regression.

File naming: data/nba/gamelog_full_{player_id}_{season}.json
             Each file = one player's game log for one season (list of row dicts).

CLI:
  python src/prediction/dnp_predictor.py --train
  python src/prediction/dnp_predictor.py --predict "Kawhi Leonard"
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import pickle
import re
import sys
from collections import defaultdict

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)
_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
_MODEL_PATH = os.path.join(_MODEL_DIR, "dnp_model.pkl")
_META_PATH  = os.path.join(_MODEL_DIR, "dnp_model_meta.json")

FEAT_COLS = [
    "recent_min_avg",   # avg minutes last 5 played games
    "min_trend",        # slope of minutes over last 10 games
    "games_in_last_7",  # workload proxy
    "season_gp_pct",    # games played / total possible
    "age_flag",         # placeholder (0.0 — age not in gamelogs)
]


def _parse_min(val) -> float | None:
    """Parse minutes value: '32:15' -> 32.25, 0 -> 0.0, None -> None."""
    if val is None or val == "":
        return None
    s = str(val).strip()
    if s in ("0", "0:00", "None", "null"):
        return 0.0
    if ":" in s:
        parts = s.split(":")
        try:
            return float(parts[0]) + float(parts[1]) / 60
        except Exception:
            return None
    try:
        v = float(s)
        return v
    except Exception:
        return None


def _load_all_gamelogs() -> dict:
    """
    Returns {player_id_str: [(game_date_str, minutes_float_or_None)]} sorted by date.

    Reads gamelog_full_{player_id}_{season}.json files.
    Player ID is extracted from filename since rows don't have player_id field.
    """
    # Pattern: gamelog_full_{player_id}_{season}.json
    pattern = re.compile(r"gamelog_full_(\d+)_[\d-]+\.json$")
    files = glob.glob(os.path.join(_NBA_CACHE, "gamelog_full_*.json"))

    player_games: dict = defaultdict(list)
    for fpath in files:
        fname = os.path.basename(fpath)
        m = pattern.match(fname)
        if not m:
            continue
        pid = m.group(1)
        try:
            data = json.load(open(fpath, encoding="utf-8"))
            rows = data if isinstance(data, list) else list(data.values())
        except Exception:
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            # Keys are lowercase in gamelog_full files
            date = row.get("game_date", row.get("GAME_DATE", ""))
            minutes = _parse_min(row.get("min", row.get("MIN")))
            if date:
                player_games[pid].append((str(date), minutes))

    # Sort each player's games by date (they may be in descending order already)
    for pid in player_games:
        player_games[pid].sort(key=lambda x: x[0])
    return dict(player_games)


def _build_training_rows(player_games: dict) -> tuple:
    """Build (X, y) training arrays from gamelog data."""
    rows_X = []
    rows_y = []
    for pid, games in player_games.items():
        n = len(games)
        if n < 10:  # need history
            continue
        total_games = n
        played = sum(1 for _, m in games if m is not None and m > 0)
        season_gp_pct = played / total_games if total_games > 0 else 0.5

        for i, (date, minutes) in enumerate(games):
            if i < 5:
                continue

            # Label: DNP if minutes == 0.0
            dnp = 1 if (minutes is not None and minutes == 0.0) else 0

            # recent_min_avg: last 5 played games before this game
            recent = [m for _, m in games[max(0, i - 10):i] if m is not None and m > 0][-5:]
            recent_min_avg = float(np.mean(recent)) if recent else 20.0

            # min_trend: slope over last 10 games (DNPs counted as 0)
            window = [m if (m is not None and m > 0) else 0.0 for _, m in games[max(0, i - 10):i]]
            if len(window) >= 3:
                x_idx = np.arange(len(window), dtype=float)
                min_trend = float(np.polyfit(x_idx, window, 1)[0])
            else:
                min_trend = 0.0

            # games_in_last_7: count games in last 7 calendar days
            try:
                from datetime import date as dt, timedelta
                # Parse date — gamelog dates are like "Apr 13, 2025" or "YYYY-MM-DD"
                ref_str = str(date)[:10]
                try:
                    ref = dt.fromisoformat(ref_str)
                except ValueError:
                    from datetime import datetime
                    ref = datetime.strptime(str(date).strip(), "%b %d, %Y").date()
                cutoff = ref - timedelta(days=7)
                count = 0
                for d_str, _ in games[:i]:
                    try:
                        gd = dt.fromisoformat(str(d_str)[:10])
                    except ValueError:
                        from datetime import datetime
                        try:
                            gd = datetime.strptime(str(d_str).strip(), "%b %d, %Y").date()
                        except Exception:
                            continue
                    if gd >= cutoff:
                        count += 1
                games_in_last_7 = count
            except Exception:
                games_in_last_7 = 3

            feat = [recent_min_avg, min_trend, float(games_in_last_7), season_gp_pct, 0.0]
            rows_X.append(feat)
            rows_y.append(dnp)

    return np.array(rows_X, dtype=float), np.array(rows_y, dtype=int)


def train() -> None:
    """Train logistic regression DNP predictor and save model + metadata."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import classification_report, roc_auc_score
    from sklearn.model_selection import train_test_split

    print("[dnp] Loading gamelogs...")
    player_games = _load_all_gamelogs()
    print(f"[dnp] {len(player_games)} players")

    X, y = _build_training_rows(player_games)
    print(f"[dnp] Training rows: {len(y)}, DNP rate: {y.mean():.3f}")

    if len(y) < 100:
        print("[dnp] Insufficient data — skip training")
        return

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s  = scaler.transform(X_test)

    model = LogisticRegression(class_weight="balanced", max_iter=500, random_state=42)
    model.fit(X_train_s, y_train)

    preds = model.predict(X_test_s)
    probs = model.predict_proba(X_test_s)[:, 1]
    print("[dnp] Classification report:")
    print(classification_report(y_test, preds))
    try:
        auc = roc_auc_score(y_test, probs)
        print(f"[dnp] ROC-AUC: {auc:.4f}")
    except Exception:
        auc = 0.0

    os.makedirs(_MODEL_DIR, exist_ok=True)
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump({"model": model, "scaler": scaler}, f)
    json.dump(
        {"feat_cols": FEAT_COLS, "auc": round(float(auc), 4), "dnp_rate": round(float(y.mean()), 4)},
        open(_META_PATH, "w"), indent=2
    )
    print(f"[dnp] Saved -> {_MODEL_PATH}")


# Module-level cache to avoid repeated disk reads
_dnp_cache: dict = {}


def predict_dnp(player_name: str, season: str = "2024-25") -> float:
    """
    Return DNP probability 0.0-1.0.

    Args:
        player_name: Full player name (e.g. "Kawhi Leonard").
        season:      NBA season string (e.g. "2024-25").

    Returns:
        Probability in [0, 1]. Returns 0.0 if model not trained.
    """
    global _dnp_cache
    if not os.path.exists(_MODEL_PATH):
        return 0.0
    try:
        if "model" not in _dnp_cache:
            with open(_MODEL_PATH, "rb") as f:
                _dnp_cache = pickle.load(f)

        # Look up player_id from player_avgs cache
        avgs_path = os.path.join(_NBA_CACHE, f"player_avgs_{season}.json")
        pid = None
        if os.path.exists(avgs_path):
            player_avgs = json.load(open(avgs_path))
            import unicodedata
            def _norm(s: str) -> str:
                return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
            key = _norm(player_name)
            for k, v in player_avgs.items():
                if _norm(k) == key and isinstance(v, dict):
                    pid = str(v.get("player_id", ""))
                    break

        if not pid:
            return 0.05  # unknown player, low base rate

        all_games = _load_all_gamelogs()
        games = all_games.get(pid, [])
        if not games:
            return 0.05

        recent = [m for _, m in games[-10:] if m is not None and m > 0][-5:]
        recent_min_avg = float(np.mean(recent)) if recent else 20.0

        window = [m if (m is not None and m > 0) else 0.0 for _, m in games[-10:]]
        if len(window) >= 3:
            min_trend = float(np.polyfit(np.arange(len(window), dtype=float), window, 1)[0])
        else:
            min_trend = 0.0

        # Rough proxy: games in last 4 entries
        games_in_last_7 = min(len(games[-4:]), 4)
        season_gp_pct = sum(1 for _, m in games if m is not None and m > 0) / max(len(games), 1)

        feat = np.array([[recent_min_avg, min_trend, float(games_in_last_7), season_gp_pct, 0.0]])
        feat_s = _dnp_cache["scaler"].transform(feat)
        prob = float(_dnp_cache["model"].predict_proba(feat_s)[0][1])
        return round(prob, 4)
    except Exception:
        return 0.0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DNP probability predictor")
    parser.add_argument("--train", action="store_true", help="Train the DNP model")
    parser.add_argument("--predict", type=str, metavar="PLAYER", help="Predict DNP for player")
    parser.add_argument("--season", default="2024-25")
    args = parser.parse_args()

    if args.train:
        train()
    elif args.predict:
        prob = predict_dnp(args.predict, args.season)
        print(f"DNP probability for '{args.predict}': {prob:.4f} ({prob * 100:.1f}%)")
    else:
        train()
