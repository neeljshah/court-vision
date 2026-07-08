"""Directed assist network: assister -> scorer edge counts, plus "who creates
GOOD shots for whom" -- the scorer's eFG on shots assisted specifically by A
vs the scorer's eFG on shots assisted by every OTHER assister (leave-one-out,
not a naive average-including-itself, so one dominant assister can't inflate
his own comparison).

ASSIST ENCODING -- TWO description formats coexist in this corpus (996 games
in one, 196 in the other; verified by scanning all 1192 files, not just the
first fixture -- a first look at only 0022500001.json/0022500003.json would
have missed one of them entirely, they use the OTHER format):
  (a) full-name, e.g. "Chet Holmgren makes 1-foot layup (Luguentz Dort
      assists)" -- matched by _ASSIST_RE.
  (b) abbreviated, e.g. "J. Brunson 3PT  (3 PTS) (K. Towns 1 AST)" -- first-
      initial + last name (suffix kept, e.g. "M. Porter Jr.") -- matched by
      _ASSIST_ABBREV_RE.
Neither carries a numeric assistPersonId -- both resolve the parsed name
string to a person_id via that game's own box-score roster (both teams -- an
assist is always a teammate of the scorer, so scoping to the scorer's own
team_id disambiguates the rare same-surname case for free). Format (b) is
resolved against a SEPARATE per-game abbreviation index (first-initial +
normalized rest-of-name), built once, same collision-drop rule as (a).

NOTE ON THE "eFG" METRIC HERE: assists only ever attach to MADE shots (the
feed never marks a miss "assisted"), so every shot in this table is a make
-- FGA==FGM for the edge's own subset. eFG = (FGM + 0.5*FG3M) / FGA still
means something in that special case: it collapses to 1 + 0.5*(3pt rate),
i.e. it is really measuring the MIX of layups/pull-ups vs threes among the
shots A set up for the scorer (a value-per-created-look proxy), not a make
rate. Documented rather than silently mislabeled.

Floors: an edge needs >=10 assists to be reported at all; the leave-one-out
comparison additionally needs >=5 OTHER assisted makes for that scorer or its
delta is left null (both fail-closed, both counted).

OUTPUT: data/cache/team_system/interactions/assist_network_2025_26.parquet
  assister_id, scorer_id, team_id, assister_name, scorer_name, n_assists,
  efg_by_assister, scorer_efg_other_assisters, efg_delta.

NETWORK: zero. CLI: python -m domains.basketball_nba.interactions.assist_network
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from domains.basketball_nba.lineups.pbp_lineups import _BOX_SRC, _PBP_DIR

REPO_ROOT = Path(__file__).resolve().parents[3]
_OUT_PATH = REPO_ROOT / "data" / "cache" / "team_system" / "interactions" / "assist_network_2025_26.parquet"

MIN_ASSISTS_PER_EDGE = 10
MIN_OTHER_ASSISTED_FGA = 5
_ASSIST_RE = re.compile(r"\(([^)]+) assists\)")
_ASSIST_ABBREV_RE = re.compile(r"\(([A-Za-z][A-Za-z.\-' ]*)\s+\d+ AST\)")


def load_assisted_makes(game_json: dict[str, Any]) -> list[dict[str, Any]]:
    """Every made 2pt/3pt action with a resolved (scorer, assister) pair --
    unmatched/self-only-name lookups are skipped, never crash the batch."""
    game_id = game_json["game"]["gameId"]
    rows = []
    for a in game_json["game"]["actions"]:
        if a.get("actionType") not in ("2pt", "3pt") or a.get("shotResult") != "Made":
            continue
        if not a.get("teamId") or not a.get("personId"):
            continue
        desc = a.get("description", "")
        m = _ASSIST_RE.search(desc)
        abbrev = m is None
        if m is None:
            m = _ASSIST_ABBREV_RE.search(desc)
        if not m:
            continue
        rows.append({
            "game_id": game_id, "team_id": a["teamId"], "scorer_id": a["personId"],
            "assister_name": m.group(1).strip(), "abbrev": abbrev,
            "fgm": 1, "fg3m": 1 if a["actionType"] == "3pt" else 0, "fga": 1,
        })
    return rows


def _normalize_name(name: str) -> str:
    """Strips accents (NFKD-decompose then drop combining marks) -- the PBP
    feed's `description` field renders assister names plain-ASCII ("Luka
    Doncic", "Nikola Jokic") while player_boxscores.parquet keeps the real
    diacritics ("Luka Doncic" vs "Doncic" -- verified: without this, several
    superstars' assists were silently unmatched, ~0022500002/0022500006)."""
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").strip().lower()


def _abbrev_key(full_name: str) -> str:
    """"Michael Porter Jr." -> "m.porter jr." (first-initial + normalized
    rest-of-name, suffix kept) -- the key space format (b) descriptions
    ("M. Porter Jr.") are parsed into, via _parse_abbrev below."""
    parts = full_name.split(" ", 1)
    first = _normalize_name(parts[0])
    rest = _normalize_name(parts[1]) if len(parts) > 1 else ""
    return f"{first[:1]}.{rest}"


def _parse_abbrev(raw: str) -> str:
    """"K. Towns" / "M. Porter Jr." -> the same "x.rest" key space as
    _abbrev_key, so both sides of the match are built identically."""
    m = re.match(r"^([A-Za-z])\.\s*(.+)$", raw.strip())
    if not m:
        return _normalize_name(raw)
    return f"{m.group(1).lower()}.{_normalize_name(m.group(2))}"


def _name_to_id_by_game(box_df: pd.DataFrame) -> dict[str, dict[str, int]]:
    """{game_id: {normalized_player_name: player_id}} -- built once from the
    box score, not re-derived per-shot; ambiguous (duplicate-normalized-name
    -in-one-game) rows are dropped from the map rather than guessed."""
    out: dict[str, dict[str, int]] = {}
    for gid, grp in box_df.groupby("game_id"):
        norm = grp["player_name"].map(_normalize_name)
        counts = norm.value_counts()
        unique_names = set(counts[counts == 1].index)
        out[gid] = {
            n: int(pid) for n, pid in zip(norm, grp["player_id"]) if n in unique_names
        }
    return out


def _abbrev_map_by_game(box_df: pd.DataFrame) -> dict[str, dict[str, int]]:
    """{game_id: {"f.lastname": player_id}} for description format (b)
    -- same collision-drop rule as _name_to_id_by_game (two teammates
    sharing a first-initial + last name in one game are dropped, not
    guessed; this is rarer than full-name collisions but not impossible)."""
    out: dict[str, dict[str, int]] = {}
    for gid, grp in box_df.groupby("game_id"):
        keys = grp["player_name"].map(_abbrev_key)
        counts = keys.value_counts()
        unique_keys = set(counts[counts == 1].index)
        out[gid] = {
            k: int(pid) for k, pid in zip(keys, grp["player_id"]) if k in unique_keys
        }
    return out


def resolve_assister_ids(
    rows: list[dict[str, Any]], name_map: dict[str, dict[str, int]], abbrev_map: dict[str, dict[str, int]],
) -> tuple[list[dict[str, Any]], int]:
    resolved, n_unmatched = [], 0
    for r in rows:
        if r.get("abbrev"):
            key = _parse_abbrev(r["assister_name"])
            aid = abbrev_map.get(r["game_id"], {}).get(key)
        else:
            aid = name_map.get(r["game_id"], {}).get(_normalize_name(r["assister_name"]))
        if aid is None:
            n_unmatched += 1
            continue
        r2 = dict(r)
        r2["assister_id"] = aid
        resolved.append(r2)
    return resolved, n_unmatched


def build_edges(resolved_rows: list[dict[str, Any]]) -> pd.DataFrame:
    edge_acc: dict[tuple[int, int, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    scorer_totals: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in resolved_rows:
        key = (r["assister_id"], r["scorer_id"], r["team_id"])
        edge_acc[key]["fgm"] += r["fgm"]
        edge_acc[key]["fg3m"] += r["fg3m"]
        edge_acc[key]["fga"] += r["fga"]
        st = scorer_totals[r["scorer_id"]]
        st["fgm"] += r["fgm"]
        st["fg3m"] += r["fg3m"]
        st["fga"] += r["fga"]

    rows = []
    for (aid, sid, tid), v in edge_acc.items():
        if v["fga"] < MIN_ASSISTS_PER_EDGE:
            continue
        efg_by_assister = (v["fgm"] + 0.5 * v["fg3m"]) / v["fga"]
        total = scorer_totals[sid]
        other_fga = total["fga"] - v["fga"]
        other_efg = (
            ((total["fgm"] - v["fgm"]) + 0.5 * (total["fg3m"] - v["fg3m"])) / other_fga
            if other_fga >= MIN_OTHER_ASSISTED_FGA else None
        )
        rows.append({
            "assister_id": aid, "scorer_id": sid, "team_id": tid,
            "n_assists": int(v["fga"]), "efg_by_assister": round(efg_by_assister, 4),
            "scorer_efg_other_assisters": round(other_efg, 4) if other_efg is not None else None,
            "efg_delta": round(efg_by_assister - other_efg, 4) if other_efg is not None else None,
        })
    return pd.DataFrame(rows)


def _attach_names(df: pd.DataFrame, box_df: pd.DataFrame) -> pd.DataFrame:
    names = box_df.drop_duplicates(subset=["player_id"]).set_index("player_id")["player_name"]
    df = df.copy()
    df["assister_name"] = df["assister_id"].map(names)
    df["scorer_name"] = df["scorer_id"].map(names)
    return df


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build NBA directed assist network")
    parser.add_argument("--out", type=str, default=str(_OUT_PATH))
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    box_df = pd.read_parquet(_BOX_SRC)
    name_map = _name_to_id_by_game(box_df)
    abbrev_map = _abbrev_map_by_game(box_df)
    files = sorted(_PBP_DIR.glob("*.json"))
    if args.limit:
        files = files[: args.limit]

    all_rows: list[dict[str, Any]] = []
    for fp in files:
        game_json = json.loads(fp.read_text(encoding="utf-8"))
        all_rows.extend(load_assisted_makes(game_json))

    n_parsed = len(all_rows)
    resolved, n_unmatched = resolve_assister_ids(all_rows, name_map, abbrev_map)
    edges = build_edges(resolved)
    edges = _attach_names(edges, box_df)
    cols = [
        "assister_id", "scorer_id", "team_id", "assister_name", "scorer_name",
        "n_assists", "efg_by_assister", "scorer_efg_other_assisters", "efg_delta",
    ]
    edges = edges[cols].sort_values("n_assists", ascending=False).reset_index(drop=True)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    edges.to_parquet(out_path, index=False)
    print(
        f"assisted_makes_parsed={n_parsed} name_unmatched={n_unmatched} "
        f"edges_above_floor={len(edges)} -> {out_path}"
    )
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
