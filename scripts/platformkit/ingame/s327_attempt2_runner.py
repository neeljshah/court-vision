"""Ephemeral local S327 attempt-2 runner; delete after its detached measurement."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import psutil

from scripts.platformkit.ingame.prestart_m0_controls import collision_census, dedupe_by_event_key, permute_dates
from scripts.platformkit.ingame.prestart_m0_table import _write, build_table, iter_rows, state_events

REPO = Path.cwd()
OUT = REPO / "docs/evidence/harness/S327_prestart_m0_table_2026-09-08b"
STAGE_DIR = OUT / "staged_output_tables"
PROD_DIR = REPO / "data/cache/ingame"
MAP = json.loads((REPO / "domains/cross_sport_market/prestart_m0_name_map.json").read_text())
STATE = ["game_id", "event_id", "event_key", "match_id", "id", "start_ts", "start_time", "commence_time", "start_utc", "tip_ts", "home", "home_team", "team_home", "player1", "p1", "away", "away_team", "team_away", "player2", "p2", "date", "game_date", "event_date", "market_ticker"]
QUOTE = ["game_id", "event_id", "event_key", "match_id", "id", "quote_ts", "timestamp", "ts", "close_ts", "created_at", "time", "p_prestart", "probability", "implied_probability", "p_close", "close_prob", "price", "yes_price", "prob", "market_prob", "close_sec_after_tip", "sec_after_tip", "home", "home_team", "team_home", "player1", "p1", "away", "away_team", "team_away", "player2", "p2", "side", "venue", "source", "book", "date", "game_date", "event_date", "close_source", "ticker_or_slug", "market_ticker"]
NBA_QUOTES = ["data/cache/combo/gate_corpus_nba_close.parquet", "data/cache/inplay_odds/nba_price_series.parquet"]
WNBA_QUOTES = ["data/cache/inplay_odds/wnba_price_series.parquet"]
MLB_QUOTES = ["data/cache/combo/gate_corpus_mlb_close.parquet", "data/cache/inplay_odds/mlb_price_series.parquet"]
SOCCER_QUOTES = ["data/cache/inplay_odds/soccer_price_series.parquet", "data/cache/inplay_odds/soccer_intl_price_series.parquet"]
TENNIS_QUOTES = ["data/cache/inplay_odds/tennis_price_series.parquet"]
# Each sport: [(season_label, state_path), ...] -- 16 groups total, matching attempt-1's census.
GROUPS: dict[str, tuple[list[tuple[str, str]], list[str]]] = {
    "nba": ([("nba_full", "data/cache/inplay_odds/nba_checkpoints_full.parquet")], NBA_QUOTES),
    "wnba": ([("wnba_full", "data/cache/inplay_odds/wnba_checkpoints_full.parquet")], WNBA_QUOTES),
    "mlb": ([(str(year), f"data/cache/ingame/mlb_pitch_states__{year}.parquet") for year in range(2022, 2027)], MLB_QUOTES),
    "soccer": ([(name, f"data/cache/ingame/soccer_states__{name}.parquet")
                for name in ("combo_eng_ger", "combo_esp_ita", "eng1", "esp1", "ger1", "ita1", "wc_2026")], SOCCER_QUOTES),
    "tennis": ([(name, f"data/cache/ingame/tennis_states__{name}.parquet") for name in ("atp", "wta")], TENNIS_QUOTES),
}
_KINDS = (("PRE_START", "pre_start"), ("AT_TIP", "at_tip"), ("FIRST_INPLAY", "first_inplay"), ("NONE", "none"))


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stream(paths: list[str]):
    for relative in paths:
        path = REPO / relative
        if not path.exists():
            print("ABSENT-IN-WORKTREE", relative, flush=True)
            continue
        for row in iter_rows(path, QUOTE):
            row["_s327_source"] = relative
            yield row


def _events(sport: str, season_paths: list[tuple[str, str]]) -> tuple[list[dict], list[dict]]:
    """Tag season/source provenance BEFORE the sport-level dedupe; return (deduped, raw)."""
    raw: list[dict] = []
    for season, relative in season_paths:
        path = REPO / relative
        if not path.exists():
            print("ABSENT-IN-WORKTREE", relative, flush=True)
            continue
        for event in state_events(iter_rows(path, STATE), sport):
            event["season"], event["source_store"] = season, relative
            raw.append(event)
    deduped, _ = dedupe_by_event_key(raw)
    return deduped, raw


def _counts(rows: list[dict]) -> Counter:
    return Counter(row["kind"] for row in rows)


def _cell(value: int, width: int = 6) -> str:
    return f"{value:0{width}d}"


def _write_csv(name: str, fields: list[str], rows: list[dict], count_fields: set[str]) -> None:
    with (OUT / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _cell(row[field], 4) if field.endswith("_per_mille") else _cell(row[field]) if field in count_fields else row[field] for field in fields})


def _season_group(rows: list[dict], season: str) -> list[dict]:
    return [row for row in rows if row["season"] == season]


def main() -> int:
    started, proc, peak = time.monotonic(), psutil.Process(), 0
    STAGE_DIR.mkdir(parents=True, exist_ok=True)
    PROD_DIR.mkdir(parents=True, exist_ok=True)
    joins, controls, collisions, unmapped = [], [], [], {}
    for sport, (season_paths, quote_paths) in GROUPS.items():
        events, raw_events = _events(sport, season_paths)
        rows, misses = build_table(events, _stream(quote_paths), sport, MAP, source=sport, allow_proxy=True, require_team_agreement=True)
        control, _ = build_table(permute_dates(events), _stream(quote_paths), sport, MAP, source=sport, allow_proxy=True, require_team_agreement=True)
        unmapped[sport] = dict(misses)
        for season, _relative in season_paths:
            season_events, season_raw = _season_group(events, season), _season_group(raw_events, season)
            season_rows, season_control = _season_group(rows, season), _season_group(control, season)
            staged, production = STAGE_DIR / f"prestart_m0_attempt2__{sport}_{season}.parquet", PROD_DIR / f"prestart_m0_attempt2__{sport}_{season}.parquet"
            for out_path in (staged, production):
                if out_path.exists():
                    raise FileExistsError("refusing to overwrite " + str(out_path))
            _write(season_rows, staged)
            _write(season_rows, production)
            kinds, control_kinds = _counts(season_rows), _counts(season_control)
            total = len(season_rows)
            assert kinds == _counts(season_rows)
            join = {"sport": sport, "season": season, "archive_event_rows": len(season_raw), "unique_event_keys": len(season_events), "n_events": total}
            for kind, short in _KINDS:
                join[f"n_{short}"] = kinds[kind]
                join[f"{short}_per_mille"] = round(1000 * kinds[kind] / total) if total else 0
            joins.append(join)
            residual_keys = ";".join(sorted(row["event_key"] for row in season_control if row["kind"] != "NONE"))
            controls.append({"sport": sport, "season": season, "n_events": total,
                              **{f"real_{name}": kinds[kind] for kind, name in _KINDS},
                              **{f"control_{name}": control_kinds[kind] for kind, name in _KINDS},
                              "residual_event_keys": residual_keys})
            collisions.append({"sport": sport, "season": season, **collision_census(season_events)})
            print("OUTPUT_EQUALS_CENSUS", sport, season, dict(sorted(kinds.items())), "SHA256", _hash(staged), flush=True)
        peak = max(peak, proc.memory_info().rss)
        if peak > 700_000_000:
            print("RAM_LIMIT_EXCEEDED", round(peak / 1e6, 1), flush=True)
            return 2
        print("SPORT", sport, "archive_rows", len(raw_events), "unique", len(events), "rss_mb", round(peak / 1e6, 1), flush=True)
    count_fields = {"archive_event_rows", "unique_event_keys", "n_events", "n_pre_start", "n_at_tip", "n_first_inplay", "n_none"}
    join_fields = ["sport", "season", "archive_event_rows", "unique_event_keys", "n_events", "n_pre_start", "pre_start_per_mille", "n_at_tip", "at_tip_per_mille", "n_first_inplay", "first_inplay_per_mille", "n_none", "none_per_mille"]
    _write_csv("join_census.csv", join_fields, joins, count_fields)
    control_fields = ["sport", "season", "n_events", "real_pre_start", "real_at_tip", "real_first_inplay", "real_none", "control_pre_start", "control_at_tip", "control_first_inplay", "control_none", "residual_event_keys"]
    _write_csv("control_census.csv", control_fields, controls, set(control_fields) - {"sport", "season", "residual_event_keys"})
    collision_fields = ["sport", "season", "n_events", "doubleheader_keys", "doubleheader_events", "rematch_pairs", "rematch_events", "date_team_collision_keys", "date_team_collision_events", "multi_candidate_events", "resolved_kept_first_bypair", "resolved_kept_first_bydateteam", "resolved_kept_all"]
    _write_csv("collisions.csv", collision_fields, collisions, set(collision_fields) - {"sport", "season"})
    (OUT / "unmapped.json").write_text(json.dumps(unmapped, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("INTERPRETER", sys.executable, flush=True)
    print("WALL_S", round(time.monotonic() - started, 1), "PEAK_RSS_MB", round(peak / 1e6, 1), flush=True)
    return 0


if __name__ == "__main__":
    argparse.ArgumentParser(
        description="Ephemeral S327 attempt-2 measurement runner (no options; --help exits before loading data).",
    ).parse_args()
    raise SystemExit(main())
