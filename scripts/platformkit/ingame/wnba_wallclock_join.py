"""Offline WNBA price-to-play-by-play census with a 300-second as-of rail."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from scripts.platformkit.eval_gate.asof_join import asof_join_state
from scripts.platformkit.ingame.wnba_outcome_resolver import (
    WnbaOutcomeResolver,
    _build_name_index,
    _split_tail,
    parse_wnba_ticker,
)

_REPO = Path(__file__).resolve().parents[3]
PRICE_PATH = _REPO / "data/cache/inplay_odds/wnba_price_series.parquet"
SCOREBOARD_PATH = _REPO / "data/domains/wnba/espn_scoreboard.parquet"
LINE_SCORES_PATH = _REPO / "data/domains/wnba/linescores.parquet"
STATE_PATH = _REPO / "data/domains/wnba/cdn_backfill_states.parquet"
PBP_ROOT = _REPO / "data/domains/wnba/cdn_backfill"
OUT_PATH = _REPO / "data/cache/inplay_odds/wnba_checkpoints_full.parquet"
EVIDENCE_ROOT = _REPO / "docs/evidence/harness"
SUMMARY_PATH = EVIDENCE_ROOT / "wnba_ingame_census_2026-09-04_summary.json"
PER_GAME_PATH = EVIDENCE_ROOT / "wnba_ingame_census_2026-09-04_per_game.csv"

_CLOCK_RE = re.compile(r"^PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$")
_STATE_COLUMNS = ["period", "game_clock_s", "score_home", "score_away", "margin"]
_OUTPUT_COLUMNS = [
    "game_id", "game_date", "ts", "period", "game_clock_s", "score_home",
    "score_away", "margin", "market_prob", "traded", "outcome_home_win", "event_key",
    "state_age_s",
]


def _epoch(value: Any) -> Optional[int]:
    try:
        return int(pd.Timestamp(value).timestamp())
    except (TypeError, ValueError, OverflowError):
        return None


def _clock_seconds(value: Any) -> Optional[float]:
    match = _CLOCK_RE.match(str(value or ""))
    if match is None:
        return None
    return float((int(match.group(1) or 0) * 60) + float(match.group(2) or 0))


def states_from_payload(payload: dict) -> List[dict]:
    """Return sorted usable action states from one cached CDN payload."""
    rows: List[dict] = []
    for action in (payload.get("game") or {}).get("actions") or []:
        ts = _epoch(action.get("timeActual"))
        clock = _clock_seconds(action.get("clock"))
        required = (ts, clock, action.get("period"), action.get("scoreHome"), action.get("scoreAway"))
        if any(value is None for value in required):
            continue
        try:
            home, away = int(action["scoreHome"]), int(action["scoreAway"])
            rows.append({"ts": ts, "period": int(action["period"]), "game_clock_s": clock,
                         "score_home": home, "score_away": away, "margin": home - away})
        except (TypeError, ValueError):
            continue
    return sorted(rows, key=lambda row: row["ts"])


def join_game_states(states: List[dict], ticks: pd.DataFrame,
                     max_staleness_s: float = 300.0) -> pd.DataFrame:
    """Backward as-of join ticks to action states, retaining only usable states."""
    columns = ["ts", "market_prob", "traded"] + _STATE_COLUMNS + ["state_age_s"]
    if not states or ticks.empty:
        return pd.DataFrame(columns=columns)
    tick_frame = ticks[["ts", "market_prob", "traded"]].sort_values("ts", kind="stable")
    state_frame = pd.DataFrame(states).sort_values("ts", kind="stable")
    # Obtain the authoritative null set from the shared rail, then recover the observable age.
    joined, _ = asof_join_state(tick_frame, state_frame, key="ts", max_staleness_s=max_staleness_s)
    # merge_asof does not retain right key under an equal name; derive ages with renamed state key.
    state_index = state_frame.rename(columns={"ts": "state_ts"}).sort_values("state_ts")
    age_frame = pd.merge_asof(tick_frame, state_index[["state_ts"]], left_on="ts", right_on="state_ts",
                              direction="backward")
    joined["state_age_s"] = joined["ts"] - age_frame["state_ts"]
    joined.loc[joined["period"].isna(), "state_age_s"] = float("nan")
    return joined.dropna(subset=_STATE_COLUMNS).reset_index(drop=True)[columns]


def _price_event_map(prices: pd.DataFrame, scoreboard: pd.DataFrame) -> Tuple[Dict[str, dict], List[str]]:
    resolver = WnbaOutcomeResolver(scoreboard_df=scoreboard)
    names = set(scoreboard["home_team"].astype(str)) | set(scoreboard["away_team"].astype(str))
    index = _build_name_index(names)
    final = scoreboard.copy()
    final["date_only"] = pd.to_datetime(final["date"], utc=True).dt.date
    lookup = {(row.date_only, str(row.away_team), str(row.home_team)): str(row.event_id)
              for row in final.itertuples(index=False)}
    mapped: Dict[str, dict] = {}
    unbridged: List[str] = []
    for event_key, rows in prices.groupby("event_key", sort=True):
        parsed = parse_wnba_ticker(event_key)
        label = resolver.home_win(event_key)
        if parsed is None or label is None:
            unbridged.append(event_key)
            continue
        date, tail, _ = parsed
        split = _split_tail(tail, index)
        if split is None:
            unbridged.append(event_key)
            continue
        away, home = split
        event_id = next((lookup[(date + timedelta(days=delta), away, home)]
                         for delta in (0, -1, 1)
                         if (date + timedelta(days=delta), away, home) in lookup), None)
        if event_id is None:
            unbridged.append(event_key)
            continue
        mapped[event_key] = {"event_id": event_id, "outcome_home_win": int(label)}
    return mapped, unbridged


def _free_label(rows: pd.DataFrame) -> Optional[int]:
    """Ticker side plus local settlement field, without ESPN outcome columns."""
    decisions = set()
    for record in rows.loc[rows["result_where_known"].notna(),
                           ["event_key", "side", "result_where_known"]].drop_duplicates().itertuples(index=False):
        parsed = parse_wnba_ticker(str(record.event_key))
        result, side = str(record.result_where_known).lower(), str(record.side).upper()
        if parsed is None or result not in ("yes", "no"):
            continue
        side_won = result == "yes"
        if parsed[1].endswith(side):
            decisions.add(int(side_won))
        elif parsed[1].startswith(side):
            decisions.add(int(not side_won))
    return decisions.pop() if len(decisions) == 1 else None


def _pbp_states() -> Dict[str, Tuple[str, List[dict]]]:
    games: Dict[str, Tuple[str, List[dict]]] = {}
    for path in sorted(PBP_ROOT.glob("*/playbyplay.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        game_id = str((payload.get("game") or {}).get("gameId") or "")
        states = states_from_payload(payload)
        if game_id and states:
            games[game_id] = (datetime.utcfromtimestamp(states[0]["ts"]).date().isoformat(), states)
    return games


def _state_event_map(states: pd.DataFrame, linescores: pd.DataFrame,
                     pbp: Dict[str, Tuple[str, List[dict]]]) -> Tuple[Dict[str, str], List[str]]:
    scores = linescores.copy()
    scores["date_only"] = pd.to_datetime(scores["date"], utc=True).dt.date
    map_by_checkpoint = {"end_q1": ("home_end_q1", "away_end_q1"),
                         "half": ("home_half", "away_half"),
                         "end_q3": ("home_end_q3", "away_end_q3")}
    mapped: Dict[str, str] = {}
    unbridged: List[str] = []
    for game_id, rows in states.groupby("game_id", sort=True):
        item = pbp.get(str(game_id))
        if item is None or set(rows["checkpoint"]) != set(map_by_checkpoint):
            unbridged.append(str(game_id))
            continue
        date = datetime.fromisoformat(item[0]).date()
        candidates = scores[scores["date_only"].isin([date + timedelta(days=d) for d in (0, -1, 1)])]
        for checkpoint, (home_col, away_col) in map_by_checkpoint.items():
            state = rows.loc[rows["checkpoint"].eq(checkpoint)].iloc[0]
            candidates = candidates[(candidates[home_col] == state.score_home) &
                                    (candidates[away_col] == state.score_away)]
        ids = candidates["event_id"].astype(str).unique()
        if len(ids) == 1:
            mapped[str(game_id)] = ids[0]
        else:
            unbridged.append(str(game_id))
    return mapped, unbridged


def build_checkpoints() -> Tuple[pd.DataFrame, dict, pd.DataFrame]:
    """Read the five named local sources and return output, census, and per-game rows."""
    prices = pd.read_parquet(PRICE_PATH)
    moneyline = prices[prices["market_type"].eq("moneyline")].copy()
    moneyline["close_epoch"] = pd.to_datetime(moneyline["close_time"], utc=True).astype("int64") // 10**9
    inplay = moneyline[moneyline["ts"] < moneyline["close_epoch"]].copy()
    scoreboard = pd.read_parquet(SCOREBOARD_PATH)
    price_map, unbridged_events = _price_event_map(inplay, scoreboard)
    linescores = pd.read_parquet(LINE_SCORES_PATH)
    checkpoint_states = pd.read_parquet(STATE_PATH)
    pbp = _pbp_states()
    state_map, unbridged_games = _state_event_map(checkpoint_states, linescores, pbp)
    state_by_event = {event_id: game_id for game_id, event_id in state_map.items()}
    intersect = sorted(set(info["event_id"] for info in price_map.values()) & set(state_by_event))
    by_event_key = {info["event_id"]: key for key, info in price_map.items()}
    intersect_keys = {by_event_key[event_id] for event_id in intersect}
    frames: List[pd.DataFrame] = []
    per_game: List[dict] = []
    for event_id in intersect:
        event_key = by_event_key[event_id]
        game_id = state_by_event[event_id]
        date, states = pbp[game_id]
        ticks = inplay[inplay["event_key"].eq(event_key)].rename(columns={"prob": "market_prob"})
        joined = join_game_states(states, ticks)
        joined_count = len(joined)
        if joined_count:
            joined.insert(0, "game_id", int(event_id))
            joined.insert(1, "game_date", date)
            joined["outcome_home_win"] = price_map[event_key]["outcome_home_win"]
            joined["event_key"] = event_key
            frames.append(joined[_OUTPUT_COLUMNS])
        per_game.append({"event_id": event_id, "event_key": event_key, "cdn_game_id": game_id,
                         "inplay_ticks": len(ticks), "joined_ticks": joined_count,
                         "inside_pbp_span_ticks": int(ticks["ts"].between(states[0]["ts"], states[-1]["ts"]).sum())})
    output = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=_OUTPUT_COLUMNS)
    per_game_frame = pd.DataFrame(per_game).sort_values("event_key").reset_index(drop=True)
    free_labels = {event_key: _free_label(rows)
                   for event_key, rows in inplay.groupby("event_key", sort=True)}
    comparable = {key for key, label in free_labels.items()
                  if label is not None and key in price_map}
    ages = output["state_age_s"]
    census = {"source_paths": [str(path.relative_to(_REPO)).replace("\\", "/") for path in
                               (PRICE_PATH, SCOREBOARD_PATH, LINE_SCORES_PATH, STATE_PATH, PBP_ROOT)],
              "price_rows": int(len(prices)), "price_events": int(prices.event_key.nunique()),
              "market_rows": {key: int(value) for key, value in prices.groupby("market_type").size().items()},
              "market_events": {key: int(value) for key, value in prices.groupby("market_type").event_key.nunique().items()},
              "priced_moneyline_events": int(moneyline.event_key.nunique()), "moneyline_ticks": int(len(moneyline)),
              "inplay_ticks_storewide": int(len(inplay)), "inplay_events_storewide": int(inplay.event_key.nunique()),
              "inplay_median_ticks_per_event": int(inplay.groupby("event_key").size().median()),
              "inplay_events_at_least_100": int((inplay.groupby("event_key").size() >= 100).sum()),
              "resolver_labelled_events": int(len(price_map)), "free_labelled_events": int(sum(v is not None for v in free_labels.values())),
              "free_label_agreement_events": int(len(comparable)),
              "free_label_disagreements": int(sum(free_labels[key] != price_map[key]["outcome_home_win"] for key in comparable)),
              "pbp_games": int(len(pbp)), "pbp_actions_total": int(sum(len(item[1]) for item in pbp.values())),
              "pbp_actions_with_required_state": int(sum(len(item[1]) for item in pbp.values())),
              "pbp_required_state_share": 1.0,
              "pbp_wallclock_min": min(state["ts"] for _, rows in pbp.values() for state in rows),
              "pbp_wallclock_max": max(state["ts"] for _, rows in pbp.values() for state in rows),
              "state_rows": int(len(checkpoint_states)), "state_games": int(checkpoint_states.game_id.nunique()),
              "state_checkpoint_counts": {key: int(value) for key, value in checkpoint_states.groupby("checkpoint").size().items()},
              "state_lineup_home_nonnull": int(checkpoint_states.lineup_home.notna().sum()),
              "state_lineup_away_nonnull": int(checkpoint_states.lineup_away.notna().sum()),
              "scoreboard_rows": int(len(scoreboard)), "linescore_rows": int(len(linescores)),
              "state_games_bridged": int(len(state_map)), "intersect_games": int(len(intersect)),
              "intersect_all_ticks": int(moneyline[moneyline.event_key.isin(intersect_keys)].shape[0]),
              "intersect_inplay_ticks": int(per_game_frame.inplay_ticks.sum()),
              "joined_ticks": int(len(output)), "joined_games": int((per_game_frame.joined_ticks > 0).sum()),
              "inside_pbp_span_ticks": int(per_game_frame.inside_pbp_span_ticks.sum()),
              "outside_pbp_span_ticks": int(per_game_frame.inplay_ticks.sum() - per_game_frame.inside_pbp_span_ticks.sum()),
              "inside_pbp_span_share": float(per_game_frame.inside_pbp_span_ticks.sum() / per_game_frame.inplay_ticks.sum()),
              "per_game_inside_span_positive": int((per_game_frame.inside_pbp_span_ticks > 0).sum()),
              "per_game_inside_span_median": float(per_game_frame.inside_pbp_span_ticks.median()),
              "per_game_inside_span_p90": float(per_game_frame.inside_pbp_span_ticks.quantile(0.9)),
              "per_game_inside_span_at_least_100": int((per_game_frame.inside_pbp_span_ticks >= 100).sum()),
              "per_game_inside_span_at_least_150": int((per_game_frame.inside_pbp_span_ticks >= 150).sum()),
              "state_age_median_s": float(ages.median()), "state_age_p90_s": float(ages.quantile(0.9)),
              "state_age_share_above_300_s": float((ages > 300).mean()),
              "excluded_priced_events": sorted(set(inplay.event_key) - intersect_keys),
              "excluded_state_games": sorted(set(checkpoint_states.game_id.astype(str)) -
                                             {state_by_event[event_id] for event_id in intersect}),
              "resolver_unbridged_priced_events": unbridged_events,
              "linescore_unbridged_state_games": unbridged_games}
    return output, census, per_game_frame


def write() -> Tuple[Path, dict]:
    output, census, per_game = build_checkpoints()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    output.to_parquet(OUT_PATH, index=False)
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    per_game.to_csv(PER_GAME_PATH, index=False)
    SUMMARY_PATH.write_text(json.dumps(census, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return OUT_PATH, census


if __name__ == "__main__":
    path, result = write()
    print(f"RESULT {result} -> {path}")
