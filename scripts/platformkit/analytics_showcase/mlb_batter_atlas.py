"""MLB batter atlas: one compact descriptive card per batter above a pitches-
faced floor -- pitch mix seen, velo seen, zone profile (rulebook zone vs
edge/chase), and contact quality (exit velo on batted balls). Same 2025
statcast pull as mlb_pitch_atlas.py, batter side (grouped by `batter` instead
of pitching team). DESCRIPTIVE_ONLY, no edge/ROI/$ claims -- see
docs/JOB_EVIDENCE_PACKET.md.

CONTACT_NOTE: launch_speed and estimated_woba_using_speedangle are populated
only on pitches the batter actually put in play (batted-ball rows), not on
every pitch -- contact-panel n is the batted-ball count, not pitches_faced.
No swing/miss or launch_angle column exists in this pull (same gap
mlb_pitch_atlas found), so whiff rate and a true barrel profile are not built
here; the zone (rulebook 1-9 vs edge/chase 11-14) and exit-velo panels are the
honest substitutes from fields that actually exist.

Batter names come from data/domains/mlb/player_gamelogs.parquet (player_id ->
player), the same id->name recipe domains/mlb/platoon_split_index.py already
uses -- confirmed 671/671 2025 statcast batter ids resolve. Real name
collisions exist in MLB (two different 2025 batters are both "Max Muncy",
LAD vs ATH) -- disambiguated with team, falling back to batter_id if a team
match still collides.

Input:  data/cache/statcast/statcast_fuller__2025.parquet (columns-only read)
        data/domains/mlb/player_gamelogs.parquet (columns-only read, names)
Output: docs/img/atlas/mlb_batters/<slug>.png (one per eligible batter)
        out/atlas_mlb_batters_manifest.json (via atlas_factory.write_manifest)

Usage:
    python -m scripts.platformkit.analytics_showcase.mlb_batter_atlas          # full build (ONE process, takes minutes)
    python -m scripts.platformkit.analytics_showcase.mlb_batter_atlas --check  # fast: manifest count == disk PNGs + spot-open 2
"""
import json
from collections import Counter
from pathlib import Path

import pandas as pd

try:
    from scripts.platformkit.analytics_showcase.atlas_factory import (
        card_figure, write_manifest, slugify, card_path, REPO_ROOT, OUT_DIR)
except ImportError:
    from atlas_factory import card_figure, write_manifest, slugify, card_path, REPO_ROOT, OUT_DIR

SPORT = "mlb_batters"
SOURCE_ARTIFACT = "data/cache/statcast/statcast_fuller__2025.parquet"
PARQUET = REPO_ROOT / "data" / "cache" / "statcast" / "statcast_fuller__2025.parquet"
GAMELOGS = REPO_ROOT / "data" / "domains" / "mlb" / "player_gamelogs.parquet"
CARD_DIR = REPO_ROOT / "docs" / "img" / "atlas" / "mlb_batters"
MIN_PITCHES_FLOOR = 300

COLS = ["batter", "pitch_type", "release_speed", "zone", "launch_speed",
        "estimated_woba_using_speedangle", "stand", "game_date"]

IN_ZONE_VALUES = set(range(1, 10))    # statcast zone 1-9: inside the rulebook strike zone
EDGE_ZONE_VALUES = {11, 12, 13, 14}   # statcast zone 11-14: the four outside/chase quadrants

CONTACT_NOTE = (
    "launch_speed/estimated_woba_using_speedangle populated only on batted-ball "
    "rows (contact-panel n is batted balls, not pitches_faced); no swing/miss or "
    "launch_angle column in this pull, so whiff rate and a launch-angle barrel "
    "profile are not built here (same gap noted in mlb_pitch_atlas)."
)


def _load_name_team_lookup() -> tuple[dict, dict]:
    """id->name / id->last-known-team from player_gamelogs.parquet -- same
    recipe as domains/mlb/platoon_split_index.py (proven: 671/671 overlap)."""
    gl = pd.read_parquet(GAMELOGS, columns=["player_id", "player", "team"])
    last = gl.drop_duplicates(subset=["player_id"], keep="last").set_index("player_id")
    return dict(last["player"]), dict(last["team"])


def _disambiguate(ids: list, names: dict, teams: dict) -> dict:
    """Real MLB name collisions exist (two different 2025 batters are both
    "Max Muncy") -- suffix with team, then batter_id if still colliding."""
    display = {bid: names.get(int(bid), "Unknown") for bid in ids}
    counts = Counter(display.values())
    for bid in ids:
        if counts[display[bid]] > 1:
            display[bid] = f"{display[bid]} ({teams.get(int(bid), bid)})"
    counts2 = Counter(display.values())
    for bid in ids:
        if counts2[display[bid]] > 1:
            display[bid] = f"{names.get(int(bid), 'Unknown')} ({bid})"
    return display


def _render_pitch_mix(ax, vc: pd.Series, top_n: int = 6) -> None:
    top = vc.head(top_n)
    y = list(range(len(top)))[::-1]
    ax.barh(y, top.values, color="#1f77b4")
    ax.set_yticks(y)
    ax.set_yticklabels(top.index, fontsize=5)


def _render_velo_hist(ax, speeds: pd.Series) -> None:
    ax.hist(speeds, bins=15, color="#2a6fbf")


def _render_zone(ax, n_in: int, n_edge: int) -> None:
    labels = ["in-zone\n1-9", "edge/chase\n11-14"]
    total = (n_in + n_edge) or 1
    pcts = [100 * n_in / total, 100 * n_edge / total]
    bars = ax.bar(labels, pcts, color=["#2a9d5c", "#c0392b"])
    ax.set_ylim(0, 100)
    ax.tick_params(axis="x", labelsize=4.5)
    for b, v in zip(bars, pcts):
        ax.text(b.get_x() + b.get_width() / 2, v + 3, f"{v:.0f}", ha="center", fontsize=5)


def _render_contact(ax, exit_velo: pd.Series) -> None:
    ax.hist(exit_velo, bins=15, color="#d9a021")


def build_cards(df: pd.DataFrame, names: dict, teams: dict) -> tuple[list[dict], str]:
    total_batters = df["batter"].nunique()
    pitch_counts = df["batter"].value_counts()
    eligible_ids = sorted(pitch_counts[pitch_counts >= MIN_PITCHES_FLOOR].index.tolist())
    floor_label = (f"pitches_faced_2025>={MIN_PITCHES_FLOOR} "
                   f"(yields {len(eligible_ids)}/{total_batters} batters). {CONTACT_NOTE}")
    as_of = str(df["game_date"].max())
    display = _disambiguate(eligible_ids, names, teams)

    entries = []
    for bid in eligible_ids:
        sub = df[df["batter"] == bid]
        name = display[bid]
        n_pitches = len(sub)

        pitch_vc = sub["pitch_type"].fillna("UNK").value_counts()
        speeds = sub["release_speed"].dropna()

        zone_vals = sub["zone"].dropna()
        n_in = int(zone_vals.isin(IN_ZONE_VALUES).sum())
        n_edge = int(zone_vals.isin(EDGE_ZONE_VALUES).sum())
        pct_in_zone = round(100 * n_in / (n_in + n_edge), 1) if (n_in + n_edge) else None

        contact = sub["launch_speed"].dropna()
        woba_contact = sub["estimated_woba_using_speedangle"].dropna()

        stand_vc = sub["stand"].value_counts()
        bats = stand_vc.index[0] if len(stand_vc) else "UNK"

        def render_mix(ax, v=pitch_vc):
            _render_pitch_mix(ax, v)

        def render_velo(ax, s=speeds):
            _render_velo_hist(ax, s)

        def render_zone(ax, i=n_in, e=n_edge):
            _render_zone(ax, i, e)

        def render_contact(ax, c=contact):
            _render_contact(ax, c)

        result = card_figure(
            title=name,
            panels=[("pitch mix seen %", render_mix), ("velo seen (mph)", render_velo),
                    ("zone profile %", render_zone), ("contact: exit velo (mph)", render_contact)],
            source_artifact=SOURCE_ARTIFACT, floors=floor_label, as_of=as_of,
            out_path=card_path(SPORT, name),
        )

        entries.append({
            "entity": name,
            "card_path": result["path"],
            "key_numbers": {
                "batter_id": int(bid),
                "bats": bats,
                "switch_hitter": bool(len(stand_vc) > 1),
                "pitches_faced": int(n_pitches),
                "top_pitch_type_seen": pitch_vc.index[0] if len(pitch_vc) else None,
                "top_pitch_type_seen_pct": round(100 * int(pitch_vc.iloc[0]) / n_pitches, 1) if len(pitch_vc) else None,
                "velo_seen_p10": round(float(speeds.quantile(0.10)), 1) if len(speeds) else None,
                "velo_seen_p50": round(float(speeds.quantile(0.50)), 1) if len(speeds) else None,
                "velo_seen_p90": round(float(speeds.quantile(0.90)), 1) if len(speeds) else None,
                "pct_pitches_in_rulebook_zone": pct_in_zone,
                "n_batted_balls": int(len(contact)),
                "avg_exit_velo": round(float(contact.mean()), 1) if len(contact) else None,
                "exit_velo_p90": round(float(contact.quantile(0.90)), 1) if len(contact) else None,
                "avg_estimated_woba_on_contact": round(float(woba_contact.mean()), 3) if len(woba_contact) else None,
            },
            "floors": floor_label,
            "as_of": as_of,
        })

    return entries, floor_label


def main() -> dict:
    df = pd.read_parquet(PARQUET, columns=COLS)
    names, teams = _load_name_team_lookup()
    entries, floor_label = build_cards(df, names, teams)
    manifest_path = write_manifest(SPORT, entries)

    disk_pngs = list(CARD_DIR.glob("*.png"))
    total_bytes = sum(p.stat().st_size for p in disk_pngs)
    return {
        "manifest_entries": len(entries),
        "disk_pngs": len(disk_pngs),
        "floor": floor_label,
        "card_dir_bytes": total_bytes,
        "manifest_path": str(manifest_path),
        "example_entities": [e["entity"] for e in entries[:3]],
    }


def _check():
    manifest_path = OUT_DIR / f"atlas_{SPORT}_manifest.json"
    assert manifest_path.exists(), (
        f"{manifest_path} missing -- run "
        f"`python -m scripts.platformkit.analytics_showcase.mlb_batter_atlas` first"
    )
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    disk_pngs = list(CARD_DIR.glob("*.png"))
    assert manifest["n_entries"] == len(disk_pngs), (
        f"manifest says {manifest['n_entries']} entries but {len(disk_pngs)} PNGs on disk in {CARD_DIR}"
    )
    for entry in manifest["entries"][:2]:
        p = Path(entry["card_path"])
        assert p.exists() and p.stat().st_size > 0, f"card missing/empty: {p}"
    assert slugify("Max Muncy (ATH)") == "max_muncy_ath"  # atlas_factory helper still wired correctly
    print(f"check ok: {manifest['n_entries']} manifest entries == {len(disk_pngs)} PNGs on disk")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        print(json.dumps(main(), indent=2))
