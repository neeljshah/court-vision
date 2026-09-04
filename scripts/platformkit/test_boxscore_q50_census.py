from scripts.platformkit.boxscore_q50_census import is_distribution_candidate


def test_filename_census_requires_stat_and_distribution_markers() -> None:
    stores = [
        "data/cache/pts_q50_oof_int95.parquet",
        "data/cache/reb_quantile_samples.parquet",
        "data/cache/ast_distribution.csv",
        "data/cache/q50_minutes.parquet",
        "data/cache/pts_predictions.parquet",
        "data/cache/roster_sample.csv",
    ]

    selected = [path for path in stores if is_distribution_candidate(path)]

    assert selected == stores[:3]
