"""domains.basketball_wnba.claims_player_form -- per-player WNBA form claims
(SHARED CLAIMS CONTRACT rows, JSONL) off data/domains/wnba/player_boxscores.parquet
(4,697 player-game rows / 317 players / 168 games, 2026-04-25..2026-07-03; built
by domains/basketball_wnba/player_box_pergame.py -- see that module for schema).

Metrics (all per-36, except eFG which is a rate stat):
  usage_proxy_per36  -- fga+0.44*fta+tov per 36 min. FALLBACK, declared: the
                        real USG% needs per-game TEAM on-court totals (a join
                        across every player on court), which the validator's
                        single-group aggregate grammar (safe_formula.
                        evaluate_group_formula, one group_by, no cross-row
                        team join) cannot express -- so this is the simple
                        per-36 usage-ingredient rate, not true USG%.
  pts_per36, reb_per36, ast_per36 -- straightforward per-36 rate stats.
  efg_pct            -- (fgm + 0.5*fg3m) / fga, season shooting efficiency.

Recent-form vs season is the WINDOW axis (full vs last_10) applied to every
metric above -- same precedent as player_intel_shooting_claims.py's
last_20-vs-season windows -- NOT a separate single-claim delta metric: the
claims contract recomputes one window-slice per claim, so a last10-minus-full
delta isn't expressible in one claim. A consumer diffs the two rankings.

n-floor (declared): full window >= MIN_GAMES_FULL games; last_10 window (which
itself caps at 10 games) >= MIN_GAMES_LAST10 games, a looser floor since the
window already bounds sample size.

Emits: data/cache/intel_claims/wnba_player_form_claims.jsonl

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_claims_player_form.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

BOXSCORE_PATH = "data/domains/wnba/player_boxscores.parquet"
CLAIMS_PATH = Path("data/cache/intel_claims/wnba_player_form_claims.jsonl")

ENTITY_KEY = "player_id"
TOP_N = 40
VALUE_PRECISION = 4
MIN_GAMES_FULL = 15
MIN_GAMES_LAST10 = 5
LAST_N_GAMES = 10
MIN_GAMES = {"full": MIN_GAMES_FULL, "last_10": MIN_GAMES_LAST10}
DIRECTION = "desc"  # every metric here: higher = more remarkable

# formula strings are the machine contract: safe_formula's whitelist
# aggregate grammar (sum/mean/count/count_distinct + arithmetic) must be able
# to recompute each one from raw rows with zero import of this module.
FORMULAS = {
    "usage_proxy_per36": "36*(sum(fga)+0.44*sum(fta)+sum(tov))/sum(minutes)",
    "pts_per36": "36*sum(pts)/sum(minutes)",
    "reb_per36": "36*sum(reb)/sum(minutes)",
    "ast_per36": "36*sum(ast)/sum(minutes)",
    "efg_pct": "(sum(fgm)+0.5*sum(fg3m))/sum(fga)",
}


def load_boxscores(path: str = BOXSCORE_PATH) -> pd.DataFrame:
    return pd.read_parquet(path)


def _window_spec(window: str) -> dict:
    if window == "full":
        return {"kind": "last_n_games", "n": 99999, "order_by": "game_date"}
    if window == "last_10":
        return {"kind": "last_n_games", "n": LAST_N_GAMES, "order_by": "game_date"}
    raise ValueError(f"unknown window: {window}")


def _window_slice(df: pd.DataFrame, window: str) -> pd.DataFrame:
    """Independently-written mirror of aggregate_recompute.apply_window_spec's
    last_n_games branch -- 'full' uses n=99999 (>= any player's game count, so
    tail() is a no-op identity slice; matches the declared window_spec)."""
    n = 99999 if window == "full" else LAST_N_GAMES
    return df.sort_values("game_date").groupby(ENTITY_KEY, group_keys=False).tail(n)


def _compute_table(sliced: pd.DataFrame, metric: str) -> pd.DataFrame:
    g = sliced.groupby(ENTITY_KEY)
    games = g["game_id"].nunique()
    if metric == "usage_proxy_per36":
        value = 36 * (g["fga"].sum() + 0.44 * g["fta"].sum() + g["tov"].sum()) / g["minutes"].sum()
    elif metric == "pts_per36":
        value = 36 * g["pts"].sum() / g["minutes"].sum()
    elif metric == "reb_per36":
        value = 36 * g["reb"].sum() / g["minutes"].sum()
    elif metric == "ast_per36":
        value = 36 * g["ast"].sum() / g["minutes"].sum()
    elif metric == "efg_pct":
        value = (g["fgm"].sum() + 0.5 * g["fg3m"].sum()) / g["fga"].sum()
    else:
        raise ValueError(f"unknown metric: {metric}")
    return pd.DataFrame({"games": games, "value": value}).reset_index()


def build_claims(df: pd.DataFrame, window: str, top_n: int = TOP_N) -> list[dict[str, Any]]:
    sliced = _window_slice(df, window)
    win_dates = [str(sliced["game_date"].min()), str(sliced["game_date"].max())] if not sliced.empty else [None, None]
    names = df.drop_duplicates(ENTITY_KEY, keep="last").set_index(ENTITY_KEY)["player_name"]
    floor = MIN_GAMES[window]
    computed_at = datetime.now(timezone.utc).isoformat()
    claims = []

    for metric, formula in FORMULAS.items():
        table = _compute_table(sliced, metric)
        n_considered = int(len(table))
        survivors = table[table["games"] >= floor].sort_values("value", ascending=(DIRECTION == "asc")).reset_index(drop=True)
        n_excluded = n_considered - int(len(survivors))
        league_mean = float(survivors["value"].mean()) if len(survivors) else None

        ranking = []
        for i, row in survivors.head(top_n).iterrows():
            pid = row[ENTITY_KEY]
            val = round(float(row["value"]), VALUE_PRECISION)
            ranking.append({
                "rank": int(i) + 1,
                "player_id": str(pid),
                "player_name": str(names.get(pid, pid)),
                "value": val,
                "n": int(row["games"]),
                "deviation": round(val - league_mean, VALUE_PRECISION) if league_mean is not None else None,
            })

        caveats = [
            f"window={window} spans game_date {win_dates[0]}..{win_dates[1]} "
            f"({n_considered} players considered, floor games>={floor})."
        ]
        if metric == "usage_proxy_per36":
            caveats.append(
                "USAGE FALLBACK: this is fga+0.44*fta+tov per-36, NOT true USG% -- "
                "true USG% needs a per-game team-on-court join the single-group "
                "validator grammar cannot express. Declared simple per-36 fallback."
            )
        if n_considered == 0 or len(survivors) == 0:
            caveats.append(f"EMPTY RESULT: 0 of {n_considered} players clear the games>={floor} floor.")

        claims.append({
            "claim_id": f"wnba_player_form_{metric}_{window}",
            "kind": "ranking",
            "question": f"Top {top_n} WNBA players by {metric}, window={window}",
            "criteria": {
                "metric": metric,
                "formula": formula,
                "window": window,
                "window_spec": _window_spec(window),
                "aggregate": {"group_by": ENTITY_KEY, "derived": {"games": "count_distinct(game_id)"}},
                "min_sample": {"games": floor},
                "direction": DIRECTION,
                "value_precision": VALUE_PRECISION,
                "entity_key": ENTITY_KEY,
            },
            "ranking": ranking,
            "source_files": [BOXSCORE_PATH],
            "computed_at": computed_at,
            "n_considered": n_considered,
            "n_excluded_below_floor": n_excluded,
            "league_mean": round(league_mean, VALUE_PRECISION) if league_mean is not None else None,
            "window_date_range": win_dates,
            "caveats": caveats,
        })
    return claims


def write_claims(all_claims: list[dict]) -> None:
    CLAIMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CLAIMS_PATH, "w", encoding="ascii") as f:
        for c in all_claims:
            f.write(json.dumps(c, ensure_ascii=True) + "\n")


def run(windows: tuple[str, ...] = ("full", "last_10"), top_n: int = TOP_N) -> list[dict]:
    df = load_boxscores()
    all_claims: list[dict] = []
    for w in windows:
        all_claims.extend(build_claims(df, w, top_n=top_n))
    write_claims(all_claims)
    return all_claims


if __name__ == "__main__":
    claims = run()
    print(f"wrote {len(claims)} claims to {CLAIMS_PATH}")
