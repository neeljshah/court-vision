"""NBA player atlas: one compact descriptive card per player above a minutes
floor -- per-36 P/R/A by season, career shooting splits, a box-score-only
usage proxy trend, and games/minutes workload by season.

DESCRIPTIVE_ONLY (see docs/JOB_EVIDENCE_PACKET.md) -- no edge/ROI/$ claims.
"usage proxy" here is (FGA + 0.44*FTA + TOV) per-36 from box-score columns
only -- NOT team-normalized USG% (needs team FGA/FTA/TOV/pace, absent from
this table) and NOT the src/prediction/usage_rate_model.py model output.
Manifest counts are written verbatim, never inflated.

Input:  data/domains/basketball_nba/player_boxscores.parquet (columns-only read)
Output: docs/img/atlas/nba/<slug>.png (one per eligible player)
        out/atlas_nba_manifest.json (via atlas_factory.write_manifest)

Usage:
    python -m scripts.platformkit.analytics_showcase.nba_player_atlas          # full build (ONE process, takes minutes)
    python -m scripts.platformkit.analytics_showcase.nba_player_atlas --check  # fast: validate manifest count == disk PNG count
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from scripts.platformkit.analytics_showcase.atlas_factory import (
        card_figure, write_manifest, slugify, card_path, REPO_ROOT, OUT_DIR)
except ImportError:
    from atlas_factory import card_figure, write_manifest, slugify, card_path, REPO_ROOT, OUT_DIR

SPORT = "nba"
SOURCE_ARTIFACT = "data/domains/basketball_nba/player_boxscores.parquet"
PARQUET = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
CARD_DIR = REPO_ROOT / "docs" / "img" / "atlas" / "nba"
MIN_MINUTES_FLOOR = 800.0

COLS = ["player_id", "player_name", "season", "date", "min", "pts", "reb", "ast",
        "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "tov"]
SUM_COLS = ["min", "pts", "reb", "ast", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "tov"]


def season_table(sub: pd.DataFrame) -> pd.DataFrame:
    """Per (player_id, season) totals + per-36 rate columns. games = rows with min>0."""
    g = sub.groupby(["player_id", "season"]).agg(
        **{c: (c, "sum") for c in SUM_COLS},
        games=("min", lambda s: int((s > 0).sum())),
    ).reset_index()
    with np.errstate(divide="ignore", invalid="ignore"):
        safe_min = g["min"].where(g["min"] > 0)  # NaN when 0 -> NaN rate, not a divide error
        g["pts36"] = g["pts"] * 36 / safe_min
        g["reb36"] = g["reb"] * 36 / safe_min
        g["ast36"] = g["ast"] * 36 / safe_min
        g["usage36"] = (g["fga"] + 0.44 * g["fta"] + g["tov"]) * 36 / safe_min
    return g


def build_cards(df: pd.DataFrame) -> tuple[list[dict], str]:
    total_players = df["player_id"].nunique()
    career_min = df.groupby("player_id")["min"].sum()
    eligible = career_min[career_min >= MIN_MINUTES_FLOOR]
    floor_label = (f"career_min_minutes>={int(MIN_MINUTES_FLOOR)} "
                   f"(yields {len(eligible)}/{total_players} players)")

    sub = df[df["player_id"].isin(eligible.index)]
    seasons = sorted(df["season"].unique().tolist())
    as_of = df["date"].max().strftime("%Y-%m-%d")

    name_map = sub.sort_values("date").groupby("player_id")["player_name"].last()
    assert not name_map.duplicated().any(), "slug collision risk: duplicate canonical names"

    season_tbl = season_table(sub)
    career = season_tbl.groupby("player_id").agg(
        **{c: (c, "sum") for c in SUM_COLS}, games=("games", "sum"),
    )

    entries = []
    for pid in sorted(eligible.index):
        name = name_map.loc[pid]
        s = season_tbl[season_tbl["player_id"] == pid].set_index("season").reindex(seasons)
        c = career.loc[pid]

        fg_pct = c["fgm"] / c["fga"] * 100 if c["fga"] > 0 else 0.0
        fg3_pct = c["fg3m"] / c["fg3a"] * 100 if c["fg3a"] > 0 else 0.0
        ft_pct = c["ftm"] / c["fta"] * 100 if c["fta"] > 0 else 0.0
        career_min_v = c["min"]
        pts36 = c["pts"] * 36 / career_min_v if career_min_v > 0 else 0.0
        reb36 = c["reb"] * 36 / career_min_v if career_min_v > 0 else 0.0
        ast36 = c["ast"] * 36 / career_min_v if career_min_v > 0 else 0.0

        def render_per36(ax):
            x = range(len(seasons))
            ax.plot(x, s["pts36"], marker="o", ms=2, lw=1, label="P", color="#1f77b4")
            ax.plot(x, s["reb36"], marker="o", ms=2, lw=1, label="R", color="#2a9d5c")
            ax.plot(x, s["ast36"], marker="o", ms=2, lw=1, label="A", color="#d9a021")
            ax.set_xticks(list(x)); ax.set_xticklabels([sn[2:] for sn in seasons], fontsize=5)
            ax.legend(fontsize=4, loc="upper left", frameon=False, handlelength=1)

        def render_shooting(ax):
            vals = [fg_pct, fg3_pct, ft_pct]
            bars = ax.bar(["FG", "3P", "FT"], vals, color=["#1f77b4", "#d9a021", "#2a9d5c"])
            ax.set_ylim(0, 100)
            for b, v in zip(bars, vals):
                ax.text(b.get_x() + b.get_width() / 2, v + 3, f"{v:.0f}", ha="center", fontsize=5)

        def render_usage(ax):
            x = range(len(seasons))
            ax.plot(x, s["usage36"], marker="o", ms=2, lw=1, color="#b33333")
            ax.set_xticks(list(x)); ax.set_xticklabels([sn[2:] for sn in seasons], fontsize=5)

        def render_workload(ax):
            x = range(len(seasons))
            mins = s["min"].fillna(0)
            bars = ax.bar(list(x), mins, color="#7f7f7f")
            ax.set_xticks(list(x)); ax.set_xticklabels([sn[2:] for sn in seasons], fontsize=5)
            for b, gm in zip(bars, s["games"].fillna(0)):
                ax.text(b.get_x() + b.get_width() / 2, b.get_height(), f"{int(gm)}g",
                         ha="center", va="bottom", fontsize=4.5)

        result = card_figure(
            title=name,
            panels=[
                ("per-36 P/R/A", render_per36),
                ("shooting %", render_shooting),
                ("usage proxy/36", render_usage),
                ("games/min", render_workload),
            ],
            source_artifact=SOURCE_ARTIFACT,
            floors=floor_label,
            as_of=as_of,
            out_path=card_path(SPORT, name),
        )

        entries.append({
            "entity": name,
            "card_path": result["path"],
            "key_numbers": {
                "player_id": int(pid),
                "seasons_played": int(s["min"].notna().sum()),
                "career_games": int(c["games"]),
                "career_minutes": round(float(career_min_v), 1),
                "career_pts_per36": round(float(pts36), 1),
                "career_reb_per36": round(float(reb36), 1),
                "career_ast_per36": round(float(ast36), 1),
                "career_fg_pct": round(float(fg_pct), 1),
                "career_fg3_pct": round(float(fg3_pct), 1),
                "career_ft_pct": round(float(ft_pct), 1),
            },
            "floors": floor_label,
            "as_of": as_of,
        })

    return entries, floor_label


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
        f"`python -m scripts.platformkit.analytics_showcase.nba_player_atlas` first"
    )
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    disk_pngs = list(CARD_DIR.glob("*.png"))
    assert manifest["n_entries"] == len(disk_pngs), (
        f"manifest says {manifest['n_entries']} entries but {len(disk_pngs)} PNGs on disk in {CARD_DIR}"
    )
    for entry in manifest["entries"][:2]:
        p = Path(entry["card_path"])
        assert p.exists() and p.stat().st_size > 0, f"card missing/empty: {p}"
    assert slugify("Nikola Jokic") == "nikola_jokic"  # atlas_factory helper still wired correctly
    print(f"check ok: {manifest['n_entries']} manifest entries == {len(disk_pngs)} PNGs on disk")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        print(json.dumps(main(), indent=2))
