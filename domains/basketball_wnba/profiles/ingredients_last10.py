"""domains.basketball_wnba.profiles.ingredients_last10 -- last-10-games
window ABSOLUTE values (not the recent_form delta) for the same 5 per-36/rate
metrics ingredients_player.py's _box_metric_builder already computes
full-season, reusing claims_player_form's _window_slice/_compute_table
verbatim with window="last_10" instead of "full". floor=5 games, same
last-10-window floor precedent as recent_form.
"""
from __future__ import annotations

from typing import Callable

import pandas as pd

from domains.basketball_wnba.claims_player_form import _compute_table, _window_slice


def _last10_metric_builder(metric: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def _builder(df: pd.DataFrame) -> pd.DataFrame:
        sliced = _window_slice(df, "last_10")
        table = _compute_table(sliced, metric)
        names = df.drop_duplicates("player_id", keep="last").set_index("player_id")["player_name"]
        table["entity_id"] = table["player_id"].astype(str)
        table["entity_name"] = table["player_id"].map(lambda pid: names.get(pid, str(pid)))
        table["raw_value"] = table["value"]
        table["n"] = table["games"]
        table["ingredients"] = table.apply(lambda r: {
            metric: round(float(r.value), 4), "games": int(r.games), "window": "last_10"}, axis=1)
        return table[["entity_id", "entity_name", "raw_value", "n", "ingredients"]]
    return _builder


BUILDERS: dict[str, Callable[[pd.DataFrame], pd.DataFrame]] = {
    "scoring_per36_last10": _last10_metric_builder("pts_per36"),
    "reb_per36_last10": _last10_metric_builder("reb_per36"),
    "ast_per36_last10": _last10_metric_builder("ast_per36"),
    "efg_last10": _last10_metric_builder("efg_pct"),
    "usage_proxy_per36_last10": _last10_metric_builder("usage_proxy_per36"),
}
