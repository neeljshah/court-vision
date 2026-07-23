"""MLB pitch atlas: 3 card families from ONE column-selective pass over the
local 2025 statcast pull (693,037 pitches) -- (a) one card per pitch type
(19, incl. missing/rare codes), (b) one card per pitching staff (30 real MLB
franchises), (c) one card per ball-strike count state (12), league-wide pitch
mix. DESCRIPTIVE_ONLY, no edge/ROI/$ claims -- see docs/JOB_EVIDENCE_PACKET.md.

Whiff proxy: no per-pitch swing/miss field exists here -- no `description`
column, `type` merges called+swinging+foul into one "S" bucket, and `des`
only fires on PA-ending pitches (would undercount whiffs that don't end the
PA). All 3 families substitute the honest per-pitch outcome mix from `type`
instead of fabricating a whiff number -- see WHIFF_NOTE.

"Team" = the PITCHING team (home_team when inning_topbot=='Top' else
away_team). AL/NL (All-Star placeholders) excluded from the raw 32 team
codes to land on the 30 real franchises.

Output: docs/img/atlas/mlb_pitch/{by_type,by_team,by_count}/<slug>.png (19+30+12)
        out/atlas_mlb_pitch_manifest.json (61 entries, atlas_factory.write_manifest)

Usage:
    python -m scripts.platformkit.analytics_showcase.mlb_pitch_atlas          # full build (ONE process)
    python -m scripts.platformkit.analytics_showcase.mlb_pitch_atlas --check  # manifest count == disk PNGs + spot-open 2
"""
import json
from pathlib import Path

import pandas as pd

try:
    from scripts.platformkit.analytics_showcase.atlas_factory import (
        card_figure, write_manifest, slugify, REPO_ROOT, OUT_DIR)
except ImportError:
    from atlas_factory import card_figure, write_manifest, slugify, REPO_ROOT, OUT_DIR

SPORT = "mlb_pitch"
SOURCE_ARTIFACT = "data/cache/statcast/statcast_fuller__2025.parquet"
PARQUET = REPO_ROOT / "data" / "cache" / "statcast" / "statcast_fuller__2025.parquet"
CARD_DIR = REPO_ROOT / "docs" / "img" / "atlas" / "mlb_pitch"
TYPE_DIR, TEAM_DIR, COUNT_DIR = CARD_DIR / "by_type", CARD_DIR / "by_team", CARD_DIR / "by_count"

COLS = ["pitch_type", "release_speed", "balls", "strikes", "type", "home_team", "away_team", "inning_topbot", "game_date"]

ALLSTAR_CODES = {"AL", "NL"}  # exhibition-game placeholders, not real franchises
OUTCOME_LABEL = {"B": "ball", "S": "strike", "X": "in-play"}
OUTCOME_COLOR = {"ball": "#2a6fbf", "strike": "#c0392b", "in-play": "#2a9d5c"}

WHIFF_NOTE = (
    "no per-pitch swing/miss field in this pull (no `description` column; "
    "`type` merges called+swinging+foul into one S bucket, `des` only fires "
    "on PA-ending pitches) -- outcome mix (ball/strike/in-play) substitutes"
)


def _outcome_mix(sub: pd.DataFrame) -> dict:
    vc = sub["type"].value_counts()
    n = len(sub)
    return {OUTCOME_LABEL[k]: round(100 * int(v) / n, 1) for k, v in vc.items()}


def _render_outcome_panel(ax, mix: dict) -> None:
    labels = list(mix.keys())
    ax.bar(labels, [mix[l] for l in labels], color=[OUTCOME_COLOR[l] for l in labels])
    ax.set_ylabel("%", fontsize=6)
    ax.tick_params(axis="x", labelsize=5)


def _render_velo_hist(ax, speeds: pd.Series) -> None:
    ax.hist(speeds.dropna(), bins=15, color="#2a6fbf")


def _render_pitch_mix(ax, vc: pd.Series, top_n: int = 6) -> None:
    top = vc.head(top_n)
    y = list(range(len(top)))[::-1]
    ax.barh(y, top.values, color="#1f77b4")
    ax.set_yticks(y)
    ax.set_yticklabels(top.index, fontsize=5)


def _render_velo_percentiles(ax, velo_df: pd.DataFrame) -> None:
    y = list(range(len(velo_df)))[::-1]
    ax.hlines(y, velo_df["p10"], velo_df["p90"], color="#999")
    ax.scatter(velo_df["p50"], y, color="#c0392b", zorder=3, s=8)
    ax.set_yticks(y)
    ax.set_yticklabels(velo_df.index, fontsize=5)


def _count_leverage(sub: pd.DataFrame) -> dict:
    b, s = sub["balls"], sub["strikes"]
    n = len(sub)
    ahead = int((s > b).sum())
    behind = int((b > s).sum())
    even = n - ahead - behind
    return {"pitcher_ahead": round(100 * ahead / n, 1), "even": round(100 * even / n, 1),
            "pitcher_behind": round(100 * behind / n, 1)}


def build_type_cards(df: pd.DataFrame, as_of: str) -> tuple[list[dict], str]:
    type_sizes = df["pitch_type"].fillna("UNK").value_counts()
    floor = (f"all {len(type_sizes)} pitch_type codes in the 2025 pull included, no "
             f"exclusion (missing pitch_type kept as 'UNK'); smallest category n="
             f"{int(type_sizes.iloc[-1])} ({type_sizes.index[-1]}) -- small-n cards carry "
             f"high sampling noise, shown for completeness not comparison. {WHIFF_NOTE}")
    entries = []
    for pt, sub in df.groupby(df["pitch_type"].fillna("UNK")):
        n = len(sub)
        leverage = _count_leverage(sub)
        mix = _outcome_mix(sub)
        speeds = sub["release_speed"].dropna()
        counts_12 = {f"{int(bb)}-{int(ss)}": round(100 * int(c) / n, 2)
                     for (bb, ss), c in sub.groupby(["balls", "strikes"]).size().items()}

        def render_velo(ax, s=speeds):
            _render_velo_hist(ax, s)

        def render_leverage(ax, lv=leverage):
            ax.bar(list(lv.keys()), list(lv.values()), color="#6b6ba3")
            ax.tick_params(axis="x", labelsize=4, rotation=20)

        def render_outcome(ax, m=mix):
            _render_outcome_panel(ax, m)

        result = card_figure(
            title=f"pitch type: {pt}",
            panels=[("velo (mph)", render_velo), ("count leverage %", render_leverage),
                    ("outcome mix %", render_outcome)],
            source_artifact=SOURCE_ARTIFACT, floors=floor, as_of=as_of,
            out_path=TYPE_DIR / f"{slugify(pt)}.png",
        )
        entries.append({
            "entity": f"pitch_type:{pt}",
            "card_path": result["path"],
            "key_numbers": {
                "n_pitches": n,
                "pct_of_all_pitches": round(100 * n / len(df), 2),
                "velo_p10": round(float(speeds.quantile(0.10)), 1) if len(speeds) else None,
                "velo_p50": round(float(speeds.quantile(0.50)), 1) if len(speeds) else None,
                "velo_p90": round(float(speeds.quantile(0.90)), 1) if len(speeds) else None,
                "count_leverage_pct": leverage,
                "count_state_pct": counts_12,
                "outcome_mix_pct": mix,
            },
            "floors": floor,
            "as_of": as_of,
        })
    return entries, floor


def build_team_cards(df: pd.DataFrame, as_of: str) -> tuple[list[dict], str]:
    d = df[~df["pitching_team"].isin(ALLSTAR_CODES)]
    floor = (f"{d['pitching_team'].nunique()} real MLB franchises; AL/NL All-Star-Game "
             f"placeholder codes excluded from the 32 raw team codes in the pull. team = "
             f"PITCHING team, derived as home_team when inning_topbot=='Top' else "
             f"away_team (defense is whichever side is not currently batting). {WHIFF_NOTE}")
    entries = []
    for team, sub in d.groupby("pitching_team"):
        n = len(sub)
        vc = sub["pitch_type"].fillna("UNK").value_counts()
        mix = _outcome_mix(sub)
        vg = []
        velo_sub = sub.dropna(subset=["release_speed"])
        for pt, g in velo_sub.groupby(velo_sub["pitch_type"].fillna("UNK")):
            if len(g) < 20:
                continue
            q = g["release_speed"].quantile([0.10, 0.50, 0.90])
            vg.append({"pitch_type": pt, "n": len(g), "p10": q[0.10], "p50": q[0.50], "p90": q[0.90]})
        vg = sorted(vg, key=lambda r: -r["n"])[:6]
        velo_df = (pd.DataFrame(vg).set_index("pitch_type") if vg
                   else pd.DataFrame(columns=["n", "p10", "p50", "p90"]))

        def render_mix(ax, v=vc):
            _render_pitch_mix(ax, v)

        def render_velo(ax, vdf=velo_df):
            if len(vdf):
                _render_velo_percentiles(ax, vdf)

        def render_outcome(ax, m=mix):
            _render_outcome_panel(ax, m)

        result = card_figure(
            title=f"pitching staff: {team}",
            panels=[("pitch mix %", render_mix), ("velo p10-p90 by type", render_velo),
                    ("outcome mix %", render_outcome)],
            source_artifact=SOURCE_ARTIFACT, floors=floor, as_of=as_of,
            out_path=TEAM_DIR / f"{slugify(team)}.png",
        )
        entries.append({
            "entity": f"team:{team}",
            "card_path": result["path"],
            "key_numbers": {
                "n_pitches": n,
                "n_pitch_types_used": len(vc),
                "top_pitch_type": vc.index[0],
                "top_pitch_type_pct": round(100 * int(vc.iloc[0]) / n, 1),
                "outcome_mix_pct": mix,
                "velo_percentiles_by_type": {
                    r["pitch_type"]: {"n": r["n"], "p10": round(float(r["p10"]), 1),
                                       "p50": round(float(r["p50"]), 1), "p90": round(float(r["p90"]), 1)}
                    for r in vg
                },
            },
            "floors": floor,
            "as_of": as_of,
        })
    return entries, floor


def build_count_cards(df: pd.DataFrame, as_of: str) -> tuple[list[dict], str]:
    state_sizes = df.groupby(["balls", "strikes"]).size()
    floor = (f"all {len(state_sizes)} valid (balls 0-3) x (strikes 0-2) count states "
             f"present in the pull included, no exclusion floor; smallest state has "
             f"n={int(state_sizes.min()):,} pitches league-wide, largest n="
             f"{int(state_sizes.max()):,}. {WHIFF_NOTE}")
    entries = []
    for (b, s), sub in df.groupby(["balls", "strikes"]):
        n = len(sub)
        vc = sub["pitch_type"].fillna("UNK").value_counts()
        mix = _outcome_mix(sub)
        speeds = sub["release_speed"].dropna()
        label = f"{int(b)}-{int(s)}"

        def render_mix(ax, v=vc):
            _render_pitch_mix(ax, v)

        def render_velo(ax, sp=speeds):
            _render_velo_hist(ax, sp)

        def render_outcome(ax, m=mix):
            _render_outcome_panel(ax, m)

        result = card_figure(
            title=f"count {label}: league pitch mix",
            panels=[("pitch mix %", render_mix), ("velo (mph)", render_velo),
                    ("outcome mix %", render_outcome)],
            source_artifact=SOURCE_ARTIFACT, floors=floor, as_of=as_of,
            out_path=COUNT_DIR / f"{slugify(label)}.png",
        )
        entries.append({
            "entity": f"count:{label}",
            "card_path": result["path"],
            "key_numbers": {
                "balls": int(b), "strikes": int(s),
                "n_pitches": n,
                "pct_of_all_pitches": round(100 * n / len(df), 2),
                "top_pitch_type": vc.index[0],
                "top_pitch_type_pct": round(100 * int(vc.iloc[0]) / n, 1),
                "outcome_mix_pct": mix,
            },
            "floors": floor,
            "as_of": as_of,
        })
    return entries, floor


def main() -> dict:
    df = pd.read_parquet(PARQUET, columns=COLS)
    as_of = str(df["game_date"].max())
    df["pitching_team"] = df["home_team"].where(df["inning_topbot"] == "Top", df["away_team"])
    type_entries, type_floor = build_type_cards(df, as_of)
    team_entries, team_floor = build_team_cards(df, as_of)
    count_entries, count_floor = build_count_cards(df, as_of)
    entries = type_entries + team_entries + count_entries
    manifest_path = write_manifest(SPORT, entries)
    disk_pngs = list(CARD_DIR.rglob("*.png"))
    total_bytes = sum(p.stat().st_size for p in disk_pngs)
    return {
        "manifest_entries": len(entries),
        "n_by_type": len(type_entries), "n_by_team": len(team_entries), "n_by_count": len(count_entries),
        "disk_pngs": len(disk_pngs),
        "card_dir_bytes": total_bytes,
        "manifest_path": str(manifest_path),
        "example_entities": [type_entries[0]["entity"], team_entries[0]["entity"], count_entries[0]["entity"]],
        "floors": {"by_type": type_floor, "by_team": team_floor, "by_count": count_floor},
    }


def _check():
    manifest_path = OUT_DIR / f"atlas_{SPORT}_manifest.json"
    assert manifest_path.exists(), (
        f"{manifest_path} missing -- run "
        f"`python -m scripts.platformkit.analytics_showcase.mlb_pitch_atlas` first"
    )
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    disk_pngs = list(CARD_DIR.rglob("*.png"))
    assert manifest["n_entries"] == len(disk_pngs), (
        f"manifest says {manifest['n_entries']} entries but {len(disk_pngs)} PNGs on disk in {CARD_DIR}"
    )
    for entry in manifest["entries"][:2]:
        p = Path(entry["card_path"])
        assert p.exists() and p.stat().st_size > 0, f"card missing/empty: {p}"
    assert slugify("3-2") == "3_2"
    print(f"check ok: {manifest['n_entries']} manifest entries == {len(disk_pngs)} PNGs on disk")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        print(json.dumps(main(), indent=2))
