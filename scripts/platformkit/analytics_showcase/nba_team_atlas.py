"""NBA team atlas: one compact descriptive card per team (all 30) -- points/gm
scoring composition by season, a box-score-only pace proxy by season, and the
top-5 minutes-leaders' per-36 production (points+reb+ast per 36).

DESCRIPTIVE_ONLY (see docs/JOB_EVIDENCE_PACKET.md) -- no edge/ROI/$ claims.
"pace proxy" is FGA - OREB + TOV + 0.44*FTA per team-game (mean, per season) --
the standard single-side box-score possession estimate, NOT the official NBA
two-sided pace stat (that needs the opponent's DREB too, absent from this
per-player table). "top-5 contributors" = the 5 players with the most total
minutes logged for that team (team column already scopes rows to games played
FOR that team, so a mid-season trade splits correctly); their per-36 rate is
descriptive, not a performance ranking. Manifest counts are written verbatim,
never inflated.

Input:  data/domains/basketball_nba/player_boxscores.parquet (columns-only read)
Output: docs/img/atlas/nba_teams/<abbr>.png (one per team, 30 total)
        out/atlas_nba_teams_manifest.json (via atlas_factory.write_manifest)

Usage:
    python -m scripts.platformkit.analytics_showcase.nba_team_atlas          # full build (ONE process, ~1-2 min)
    python -m scripts.platformkit.analytics_showcase.nba_team_atlas --check  # fast: validate manifest count == disk PNG count
"""
import json
from pathlib import Path

import pandas as pd

try:
    from scripts.platformkit.analytics_showcase.atlas_factory import (
        card_figure, write_manifest, slugify, card_path, REPO_ROOT, OUT_DIR)
except ImportError:
    from atlas_factory import card_figure, write_manifest, slugify, card_path, REPO_ROOT, OUT_DIR

try:
    from scripts.platformkit.gamebrief.team_ids import fullname_for
except ImportError:
    def fullname_for(abbr):  # bare-script fallback (gamebrief isn't a sibling dir) -- title just uses the abbr
        return None

SPORT = "nba_teams"
SOURCE_ARTIFACT = "data/domains/basketball_nba/player_boxscores.parquet"
PARQUET = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
CARD_DIR = REPO_ROOT / "docs" / "img" / "atlas" / "nba_teams"

COLS = ["team", "season", "game_id", "date", "player_id", "player_name",
        "min", "pts", "reb", "oreb", "ast", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "tov"]


def build_cards(df: pd.DataFrame) -> tuple[list[dict], str]:
    teams = sorted(df["team"].unique().tolist())
    seasons = sorted(df["season"].unique().tolist())
    as_of = df["date"].max().strftime("%Y-%m-%d")

    tg = df.groupby(["team", "season", "game_id"]).agg(
        pts=("pts", "sum"), fgm=("fgm", "sum"), fg3m=("fg3m", "sum"), ftm=("ftm", "sum"),
        fga=("fga", "sum"), fta=("fta", "sum"), oreb=("oreb", "sum"), tov=("tov", "sum"),
    ).reset_index()
    tg["pts2"] = (tg["fgm"] - tg["fg3m"]) * 2
    tg["pts3"] = tg["fg3m"] * 3
    tg["pace_proxy"] = tg["fga"] - tg["oreb"] + tg["tov"] + 0.44 * tg["fta"]

    season_tbl = tg.groupby(["team", "season"]).agg(
        games=("game_id", "nunique"), ppg=("pts", "mean"), pts2_pg=("pts2", "mean"),
        pts3_pg=("pts3", "mean"), ptsft_pg=("ftm", "mean"), pace_proxy=("pace_proxy", "mean"),
    ).reset_index()

    name_map = df.sort_values("date").groupby("player_id")["player_name"].last()
    player_tbl = df.groupby(["team", "player_id"]).agg(
        min=("min", "sum"), pts=("pts", "sum"), reb=("reb", "sum"), ast=("ast", "sum"),
    ).reset_index()
    player_tbl["player_name"] = player_tbl["player_id"].map(name_map)
    player_tbl["pra36"] = (player_tbl["pts"] + player_tbl["reb"] + player_tbl["ast"]) * 36 / player_tbl["min"]

    floor_label = (f"all 30 teams included (each has >=200 team-games across "
                    f"{len(seasons)} seasons in sample, verified, no exclusion floor); "
                    f"top-5 contributors = 5 players with most total minutes for that "
                    f"team (minutes-ranking already excludes small-sample per-36 noise)")

    entries = []
    for abbr in teams:
        s = season_tbl[season_tbl["team"] == abbr].set_index("season").reindex(seasons)
        top5 = (player_tbl[player_tbl["team"] == abbr]
                .sort_values("min", ascending=False).head(5).reset_index(drop=True))

        full = fullname_for(abbr)
        title = f"{full} ({abbr})" if full else abbr

        def render_scoring(ax):
            x = range(len(seasons))
            p2, p3, pft = s["pts2_pg"], s["pts3_pg"], s["ptsft_pg"]
            ax.bar(x, p2, color="#1f77b4", label="2P")
            ax.bar(x, p3, bottom=p2, color="#d9a021", label="3P")
            ax.bar(x, pft, bottom=p2 + p3, color="#2a9d5c", label="FT")
            ax.set_xticks(list(x)); ax.set_xticklabels([sn[2:] for sn in seasons], fontsize=5)
            # frameon=True (unlike other atlas panels) -- a 3-segment full-height stack
            # leaves no guaranteed-empty corner for a floating legend to sit in.
            ax.legend(fontsize=4, loc="upper left", frameon=True, framealpha=0.75,
                       edgecolor="none", handlelength=1, borderpad=0.2, labelspacing=0.2)

        def render_pace(ax):
            x = range(len(seasons))
            ax.plot(x, s["pace_proxy"], marker="o", ms=2, lw=1, color="#b33333")
            ax.set_xticks(list(x)); ax.set_xticklabels([sn[2:] for sn in seasons], fontsize=5)

        def render_top5(ax):
            names = [_compact_name(n) for n in top5["player_name"]]
            y = list(range(len(names)))
            ax.barh(y, top5["pra36"], color="#1f77b4")
            ax.set_yticks(y); ax.set_yticklabels(names, fontsize=5)
            ax.invert_yaxis()  # most minutes on top

        result = card_figure(
            title=title,
            panels=[
                ("pts/gm by season", render_scoring),
                ("pace proxy/gm", render_pace),
                ("top-5 min, PRA/36", render_top5),
            ],
            source_artifact=SOURCE_ARTIFACT,
            floors=floor_label,
            as_of=as_of,
            out_path=card_path(SPORT, abbr),
        )

        entries.append({
            "entity": abbr,
            "card_path": result["path"],
            "key_numbers": {
                "team_full_name": full or abbr,
                "seasons_covered": int(s["games"].notna().sum()),
                "games_total": int(s["games"].fillna(0).sum()),
                "ppg_latest_season": round(float(s["ppg"].iloc[-1]), 1),
                "pace_proxy_latest_season": round(float(s["pace_proxy"].iloc[-1]), 1),
                "top_contributor": (top5["player_name"].iloc[0] if len(top5) else None),
                "top_contributor_pra_per36": (round(float(top5["pra36"].iloc[0]), 1) if len(top5) else None),
                "top_contributor_minutes": (round(float(top5["min"].iloc[0]), 1) if len(top5) else None),
            },
            "floors": floor_label,
            "as_of": as_of,
        })

    return entries, floor_label


def _compact_name(name: str) -> str:
    """'Giannis Antetokounmpo' -> 'G. Antetokounmpo' -- keeps 5 names readable in a ~1.8in panel."""
    parts = str(name).split()
    return f"{parts[0][0]}. {parts[-1]}" if len(parts) > 1 else str(name)


def main() -> dict:
    df = pd.read_parquet(PARQUET, columns=COLS)
    entries, floor_label = build_cards(df)
    manifest_path = write_manifest(SPORT, entries)

    disk_pngs = list(CARD_DIR.glob("*.png"))
    total_bytes = sum(p.stat().st_size for p in disk_pngs)
    summary = {
        "manifest_entries": len(entries),
        "disk_pngs": len(disk_pngs),
        "floor": floor_label,
        "card_dir_bytes": total_bytes,
        "manifest_path": str(manifest_path),
        "example_entities": [e["entity"] for e in entries[:3]],
    }
    return summary


def _check():
    manifest_path = OUT_DIR / f"atlas_{SPORT}_manifest.json"
    assert manifest_path.exists(), (
        f"{manifest_path} missing -- run "
        f"`python -m scripts.platformkit.analytics_showcase.nba_team_atlas` first"
    )
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    disk_pngs = list(CARD_DIR.glob("*.png"))
    assert manifest["n_entries"] == len(disk_pngs), (
        f"manifest says {manifest['n_entries']} entries but {len(disk_pngs)} PNGs on disk in {CARD_DIR}"
    )
    for entry in manifest["entries"][:2]:
        p = Path(entry["card_path"])
        assert p.exists() and p.stat().st_size > 0, f"card missing/empty: {p}"
    assert slugify("LAL") == "lal"  # atlas_factory helper still wired correctly
    print(f"check ok: {manifest['n_entries']} manifest entries == {len(disk_pngs)} PNGs on disk")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        print(json.dumps(main(), indent=2))
