"""Build leak-free player style embeddings from tracking box scores."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from scripts.platformkit.tracking_features import _game_key, load_game_dates


RATE_COLUMNS = (
    "touches",
    "passes",
    "distance",
    "reboundChancesTotal",
    "secondaryAssists",
)
EMBEDDING_COLUMNS = tuple("style_embedding_%d" % index for index in range(1, 5))
TRAIN_CUTOFF = pd.Timestamp("2025-01-15")


def _feature_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    """Return per-36 tracking rates plus the supplied average speed."""
    minutes = pd.to_numeric(frame["minutes"], errors="coerce").replace(0, pd.NA)
    features = frame.loc[:, RATE_COLUMNS].apply(pd.to_numeric, errors="coerce")
    features = features.div(minutes, axis=0).mul(36.0)
    features["speed"] = pd.to_numeric(frame["speed"], errors="coerce")
    return features.fillna(0.0)


def build_player_embeddings(
    tracking: pd.DataFrame, game_dates: Mapping[str, str]
) -> pd.DataFrame:
    """Return PCA embeddings averaged over each player's strictly prior games."""
    required = {"gameId", "personId", "minutes", "speed", *RATE_COLUMNS}
    missing = sorted(required.difference(tracking.columns))
    if missing:
        raise ValueError("Missing tracking columns: %s" % ", ".join(missing))

    result = tracking.copy()
    result["gameDate"] = result["gameId"].map(
        lambda game_id: game_dates.get(_game_key(game_id))
    )
    missing_dates = int(result["gameDate"].isna().sum())
    if missing_dates:
        raise ValueError("No schedule date for %d tracking rows" % missing_dates)
    result["gameDate"] = pd.to_datetime(result["gameDate"], errors="raise")
    result = result.sort_values(["personId", "gameDate", "gameId"], kind="mergesort")
    result = result.reset_index(drop=True)

    features = _feature_matrix(result)
    fit_rows = result["gameDate"] < TRAIN_CUTOFF
    if int(fit_rows.sum()) < len(EMBEDDING_COLUMNS):
        raise ValueError("Need four pre-cutoff player-game rows to fit PCA")
    scaler = StandardScaler().fit(features.loc[fit_rows])
    pca = PCA(n_components=len(EMBEDDING_COLUMNS)).fit(
        scaler.transform(features.loc[fit_rows])
    )
    realized = pd.DataFrame(
        pca.transform(scaler.transform(features)),
        columns=EMBEDDING_COLUMNS,
        index=result.index,
    )
    for column in EMBEDDING_COLUMNS:
        result[column] = realized[column].groupby(result["personId"], sort=False).transform(
            lambda values: values.expanding().mean().shift(1)
        )
    return result


def main() -> None:
    """Write player style embeddings under ``NBA_DATA_ROOT`` or ``./data``."""
    root = Path(os.environ.get("NBA_DATA_ROOT", "./data"))
    nba_dir = root / "nba"
    output = nba_dir / "player_embeddings_asof.parquet"
    embeddings = build_player_embeddings(
        pd.read_parquet(nba_dir / "player_tracking_games.parquet"),
        load_game_dates(nba_dir / "schedule"),
    )
    embeddings.to_parquet(output, index=False)
    print("Wrote %d rows to %s" % (len(embeddings), output))


if __name__ == "__main__":
    main()
