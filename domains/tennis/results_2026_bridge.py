"""domains.tennis.results_2026_bridge -- ESPN 2026 results -> Sackmann-id matches.

Bridges the gap the freshness-placement audit found: domains/tennis/matches.parquet
(Sackmann, the only dated-Elo input) ends 2025-12-17; no source has posted 2026
ATP/WTA results in Sackmann's own numeric-player-id format. This module joins the
already-ingested ESPN scoreboard rows (domains.tennis.ingest_espn, KNOWLEDGE-ONLY
realized results) onto Sackmann player_id via the existing name_aliases "sackmann"
key space (both ESPN "First Last" and Sackmann full_name share that format --
no new matching logic invented, reuses candidate_keys/normalize_sackmann as-is).

Surface is NOT in the ESPN payload; approximated only for the 4 majors (the one
place it's unambiguous from tournament_name), else "Unknown" -- ponytail: no
full tournament->surface table, the Elo surface-blend already degrades
gracefully on "Unknown" (same bucket every non-major match falls into).

Output: domains/tennis/matches_2026.parquet, same column contract as
ingest_sackmann.MATCHES_REQUIRED_COLS so it concatenates directly onto
matches.parquet for domains.tennis.elo_walkforward.walk_forward_elo.

Run: python -m domains.tennis.results_2026_bridge
Per-file test: python -m pytest domains/tennis/test_results_2026_bridge.py -q
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.tennis.name_aliases import candidate_keys, normalize_sackmann

_ROOT = Path(__file__).resolve().parents[2]
_ESPN = _ROOT / "data" / "domains" / "tennis" / "espn_matches.parquet"
_PLAYERS = _ROOT / "data" / "domains" / "tennis" / "players.parquet"
_OUT = _ROOT / "data" / "domains" / "tennis" / "matches_2026.parquet"
# players.parquet only ever populated from atp_players.csv (verified: 100% tour=="atp",
# 0 wta rows on disk) -- WTA identity is recovered instead from wta_matches.parquet's
# own p1_id/p1_name/p2_id/p2_name (same MATCHES_REQUIRED_COLS contract), which DOES
# carry real Sackmann WTA player ids. Used as a supplementary (fallback-only) source
# for BOTH tours so a player missing from players.parquet for any reason still resolves.
_BASE_MATCHES = {"atp": _ROOT / "data" / "domains" / "tennis" / "matches.parquet",
                  "wta": _ROOT / "data" / "domains" / "tennis" / "wta_matches.parquet"}

_MAJOR_SURFACE = {
    "australian open": "Hard", "us open": "Hard", "roland garros": "Clay",
    "french open": "Clay", "wimbledon": "Grass",
}


def _surface_from_name(tournament_name: str) -> str:
    n = str(tournament_name or "").strip().lower()
    for key, surf in _MAJOR_SURFACE.items():
        if key in n:
            return surf
    return "Unknown"


def build_sackmann_index(
    players_path: Path = _PLAYERS, base_matches: dict[str, Path] = _BASE_MATCHES,
) -> dict[str, dict[str, int]]:
    """tour -> {normalize_sackmann(full_name): player_id}. players.parquet wins on
    a collision; base_matches (each tour's own historical matches parquet, via its
    own p1/p2 id+name columns) only fills names players.parquet is missing -- the
    recovery path for a tour with 0 players.parquet coverage (WTA, verified on this
    disk). An unresolved ESPN name simply fails to join, never mislabels."""
    out: dict[str, dict[str, int]] = {"atp": {}, "wta": {}}
    if players_path.exists():
        players = pd.read_parquet(players_path, columns=["player_id", "full_name", "tour"])
        for r in players.itertuples(index=False):
            tour = str(r.tour)
            if tour not in out:
                continue
            key = normalize_sackmann(str(r.full_name))
            if key and key not in out[tour]:
                out[tour][key] = int(r.player_id)
    for tour, path in base_matches.items():
        if tour not in out or not path.exists():
            continue
        m = pd.read_parquet(path, columns=["p1_id", "p1_name", "p2_id", "p2_name"])
        for id_col, name_col in (("p1_id", "p1_name"), ("p2_id", "p2_name")):
            for pid, name in zip(m[id_col], m[name_col]):
                if pd.isna(pid):
                    continue
                key = normalize_sackmann(str(name))
                if key and key not in out[tour]:
                    out[tour][key] = int(pid)
    return out


def _resolve_player_id(name: str, index: dict[str, int]) -> int | None:
    for key in candidate_keys(name, "sackmann"):
        if key in index:
            return index[key]
    return None


def build_matches_2026(
    espn_path: Path = _ESPN, players_path: Path = _PLAYERS, out_path: Path = _OUT,
    start: str = "2026-01-01", end: str = "2026-12-31",
) -> tuple[pd.DataFrame, dict]:
    """Pivot ESPN player-rows -> match rows, join to Sackmann player_id, write parquet.

    Returns (matches_df, diagnostics) -- diagnostics reports join rate honestly.
    """
    espn = pd.read_parquet(espn_path)
    espn["_date"] = pd.to_datetime(espn["date"], errors="coerce", utc=True).dt.date
    espn = espn[(espn["_date"].astype(str) >= start) & (espn["_date"].astype(str) <= end)]
    espn = espn[espn["status"] == "STATUS_FINAL"]
    espn = espn[espn["discipline"].astype(str).str.contains("Singles", na=False)]

    sackmann_idx = build_sackmann_index(players_path)
    diag = {"espn_singles_final_rows": int(len(espn)), "comp_ids_seen": 0,
            "matches_both_resolved": 0, "matches_dropped_not_2_rows": 0,
            "matches_dropped_no_winner": 0, "matches_dropped_unresolved_name": 0}

    rows: list[dict] = []
    for comp_id, g in espn.groupby("comp_id", sort=False):
        diag["comp_ids_seen"] += 1
        if len(g) != 2:
            diag["matches_dropped_not_2_rows"] += 1
            continue
        g = g.reset_index(drop=True)
        winners = g["winner"] == True  # noqa: E712 -- explicit bool compare, avoid NaN truthiness
        if winners.sum() != 1:
            diag["matches_dropped_no_winner"] += 1
            continue
        league = str(g["league"].iloc[0])
        idx = sackmann_idx.get(league, {})
        ids = [_resolve_player_id(str(n), idx) for n in g["player_name"]]
        if any(i is None for i in ids) or ids[0] == ids[1]:
            diag["matches_dropped_unresolved_name"] += 1
            continue
        diag["matches_both_resolved"] += 1
        win_i = int(winners.to_numpy().argmax())
        lose_i = 1 - win_i
        winner_id, loser_id = ids[win_i], ids[lose_i]
        p1_is_winner = winner_id <= loser_id
        p1_id = winner_id if p1_is_winner else loser_id
        p2_id = loser_id if p1_is_winner else winner_id
        rows.append({
            "event_id": f"espn2026-{league}-{comp_id}",
            "date": g["_date"].iloc[0],
            "tour": league,
            "tourney_id": str(g["tournament_id"].iloc[0]),
            "tourney_name": str(g["tournament_name"].iloc[0]),
            "tourney_level": "",
            "surface": _surface_from_name(g["tournament_name"].iloc[0]),
            "best_of": int(g["best_of"].iloc[0]) if pd.notna(g["best_of"].iloc[0]) else 3,
            "round": str(g["round_name"].iloc[0]),
            "match_num": 0,
            "p1_id": p1_id, "p2_id": p2_id,
            "p1_name": str(g["player_name"].iloc[win_i if p1_is_winner else lose_i]),
            "p2_name": str(g["player_name"].iloc[lose_i if p1_is_winner else win_i]),
            "p1_rank": float("nan"), "p2_rank": float("nan"),
            "winner": 1 if p1_is_winner else 2,
            "score": "", "retirement": False, "minutes": float("nan"),
        })

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["date", "tourney_id", "match_num"], kind="mergesort").reset_index(drop=True)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pandas(out, preserve_index=False), out_path)
    diag["matches_written"] = int(len(out))
    diag["join_rate"] = round(diag["matches_both_resolved"] / diag["comp_ids_seen"], 4) if diag["comp_ids_seen"] else None
    return out, diag


def _main() -> None:
    out, diag = build_matches_2026()
    print(f"matches_2026: {diag}")
    print(f"wrote {_OUT} ({len(out)} rows)")


if __name__ == "__main__":
    _main()
