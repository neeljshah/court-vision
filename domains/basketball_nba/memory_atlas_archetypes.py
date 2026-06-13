"""domains.basketball_nba.memory_atlas_archetypes — NBA playstyle archetype notes.

Reads real parquet files (player_adv_stats, player_positions), classifies every
player with >= 10 games into one of 10 archetypes via stat-signature thresholds,
then emits Obsidian markdown notes (NO individual player names) in:

    out_dir/Archetypes/<Archetype>.md
    out_dir/Archetypes/_Archetypes_Index.md

Public API: build_archetypes(out_dir, data_dir) -> list[pathlib.Path]
F5-clean: stdlib + pandas only.  No src.* / kernel.* / edge language.
"""
from __future__ import annotations

import pathlib
from typing import Optional

import pandas as pd

from scripts.platformkit.atlas.obsidian_emit import write_note

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = _REPO_ROOT / "data"
MIN_GAMES = 10

# ---------------------------------------------------------------------------
# Archetype catalogue  (label, description, thresholds dict, extra tags)
# ---------------------------------------------------------------------------

ARCHETYPES: list[dict] = [
    {"label": "High-Usage Creator",
     "desc": "Ball-dominant guards/wings who generate offense for themselves and teammates via high usage + high AST%.",
     "thresh": {"usage%": ">= 0.22", "ast%": ">= 0.20", "position": "Guard or Guard-Forward"},
     "tags": ["#archetype/high_usage_creator"]},
    {"label": "Scoring Guard",
     "desc": "High-volume guards who prioritise scoring over playmaking — attack the basket or pull up rather than set teammates up.",
     "thresh": {"usage%": ">= 0.22", "ast%": "< 0.20", "ts%": ">= 0.52", "position": "Guard"},
     "tags": ["#archetype/scoring_guard"]},
    {"label": "3-and-D Wing",
     "desc": "Perimeter forwards who thrive as off-ball shooters and individual defenders — low usage, high TS%, good def rating.",
     "thresh": {"usage%": "< 0.19", "ts%": ">= 0.55", "def_rtg": "<= 112", "position": "Forward / Forward-Guard"},
     "tags": ["#archetype/three_and_d"]},
    {"label": "Stretch Big",
     "desc": "Bigs who face up and shoot from the perimeter — high TS% and eFG% stretch defenses for guards.",
     "thresh": {"position": "Center / Forward-Center / Center-Forward", "ts%": ">= 0.57", "efg%": ">= 0.54"},
     "tags": ["#archetype/stretch_big"]},
    {"label": "Rim-Running Big",
     "desc": "Athletic bigs who score at the rim via cuts and rolls — very high TS%, low usage (they finish, not create).",
     "thresh": {"position": "Center / Forward-Center / Center-Forward", "ts%": ">= 0.60", "usage%": "< 0.18"},
     "tags": ["#archetype/rim_runner"]},
    {"label": "Defensive Anchor",
     "desc": "Bigs who protect the rim and clean the glass — elite defensive rating + high reb% defines their value.",
     "thresh": {"position": "Center / Forward-Center / Center-Forward", "def_rtg": "<= 110", "reb%": ">= 0.10"},
     "tags": ["#archetype/defensive_anchor"]},
    {"label": "Versatile Forward",
     "desc": "Two-way forwards with balanced signatures — score in the mid-range, switch defensively, contribute on the glass.",
     "thresh": {"position": "Forward", "usage%": ">= 0.17", "reb%": ">= 0.09"},
     "tags": ["#archetype/versatile_forward"]},
    {"label": "Playmaking Big",
     "desc": "Centers/power forwards who facilitate from the high post — elevated AST% for their size, run the offense as secondary PG.",
     "thresh": {"position": "Center / Forward-Center / Center-Forward", "ast%": ">= 0.15", "usage%": ">= 0.18"},
     "tags": ["#archetype/playmaking_big"]},
    {"label": "Bench Contributor",
     "desc": "Role players off the bench — low minutes and usage, but execute a limited role efficiently across all positions.",
     "thresh": {"minutes_avg": "< 16", "usage%": "< 0.18"},
     "tags": ["#archetype/bench_contributor"]},
    {"label": "Low-Usage Connector",
     "desc": "Rotation players who fill in without demanding the ball — set screens, move off the ball, cash in open looks.",
     "thresh": {"usage%": "< 0.17", "ast%": "< 0.12"},
     "tags": ["#archetype/low_usage_connector"]},
]

# ---------------------------------------------------------------------------
# Position helpers
# ---------------------------------------------------------------------------

_BIGS = {"Center", "Forward-Center", "Center-Forward"}
_WINGS = {"Forward", "Guard-Forward", "Forward-Guard"}
_GUARDS = {"Guard"}


def _classify(row: pd.Series) -> str:
    u = float(row.get("usage", 0) or 0)
    ts = float(row.get("ts", 0) or 0)
    efg = float(row.get("efg", 0) or 0)
    a = float(row.get("ast_pct", 0) or 0)
    dr = float(row.get("def_rtg", 999) or 999)
    rb = float(row.get("reb_pct", 0) or 0)
    mn = float(row.get("minutes_avg", 0) or 0)
    pos = str(row.get("position", "") or "")
    g, w, b = pos in _GUARDS, pos in _WINGS, pos in _BIGS
    if (g or w) and u >= 0.22 and a >= 0.20: return "High-Usage Creator"
    if g and u >= 0.22 and a < 0.20 and ts >= 0.52: return "Scoring Guard"
    if w and u < 0.19 and ts >= 0.55 and dr <= 112.0: return "3-and-D Wing"
    if b and ts >= 0.60 and u < 0.18: return "Rim-Running Big"
    if b and dr <= 110.0 and rb >= 0.10: return "Defensive Anchor"
    if b and ts >= 0.57 and efg >= 0.54: return "Stretch Big"
    if b and a >= 0.15 and u >= 0.18: return "Playmaking Big"
    if w and u >= 0.17 and rb >= 0.09: return "Versatile Forward"
    if mn < 16.0 and u < 0.18: return "Bench Contributor"
    return "Low-Usage Connector"

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _build_stats(data_dir: pathlib.Path) -> pd.DataFrame:
    adv = pd.read_parquet(data_dir / "player_adv_stats.parquet")
    pos = pd.read_parquet(data_dir / "player_positions.parquet")
    df = adv.groupby("player_id").agg(
        usage=("usagepercentage", "mean"), ts=("trueshootingpercentage", "mean"),
        efg=("effectivefieldgoalpercentage", "mean"), ast_pct=("assistpercentage", "mean"),
        def_rtg=("defensiverating", "mean"), reb_pct=("reboundpercentage", "mean"),
        minutes_avg=("minutes", "mean"), n_games=("game_id", "count"),
    ).reset_index()
    df = df[df["n_games"] >= MIN_GAMES].copy()
    df = df.merge(pos[["player_id", "position"]], on="player_id", how="left")
    df["position"] = df["position"].fillna("Guard")
    return df

# ---------------------------------------------------------------------------
# Note rendering
# ---------------------------------------------------------------------------

def _write(path: pathlib.Path, text: str) -> None:
    write_note(path, text)


def _archetype_note(arch: dict, population: int, typical_pos: str) -> str:
    label, desc = arch["label"], arch["desc"]
    thresh_lines = "\n".join(f"- **{k}**: {v}" for k, v in arch["thresh"].items())
    tag_str = " ".join(["#sport/nba", "#archetype"] + arch["tags"])
    return (
        "---\ntags:\n  - sport/nba\n  - archetype\n---\n\n"
        f"# {label}\n\n"
        "[[Archetypes/_Archetypes_Index|Archetypes Index]] | [[_Index]]\n\n"
        f"## STYLE\n\n{desc}\n\n"
        f"## SIGNATURE (Classification Thresholds)\n\n{thresh_lines}\n\n"
        f"## POPULATION\n\n"
        f"- **Players fitting this archetype:** {population}\n"
        f"- **Typical position(s):** {typical_pos}\n\n"
        f"{tag_str}\n"
    )


def _label_to_slug(label: str) -> str:
    """Convert display label to filesystem slug (spaces→_, hyphens→_)."""
    return label.replace(" ", "_").replace("-", "_")


def _index_note(counts: list[tuple[str, int]]) -> str:
    total = sum(c for _, c in counts)
    rows = "\n".join(
        f"| [[{_label_to_slug(lb)}|{lb}]] | {ct} | {100 * ct / total:.1f}% |"
        for lb, ct in sorted(counts, key=lambda x: -x[1])
    )
    return (
        "---\ntags:\n  - sport/nba\n  - archetype\n  - atlas/index\n---\n\n"
        "# NBA Archetypes Index\n\n"
        "[[_Index]] | Playstyle archetype population breakdown\n\n"
        f"**Total players classified:** {total}  (min {MIN_GAMES} games)\n\n"
        "## Archetypes by Population\n\n"
        "| Archetype | Players | Share |\n|-----------|---------|-------|\n"
        f"{rows}\n\n#sport/nba #archetype\n"
    )

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_archetypes(
    out_dir: pathlib.Path,
    data_dir: Optional[pathlib.Path] = None,
    *,
    _stats_df: Optional[pd.DataFrame] = None,
) -> list[pathlib.Path]:
    """Write Obsidian archetype notes (no player names) and return written paths.

    Parameters
    ----------
    out_dir : directory where Archetypes/ sub-folder is created.
    data_dir : root data directory (default: <repo>/data).
    _stats_df : pre-built stats DataFrame for testing (bypasses parquet reads).
    """
    out_dir = pathlib.Path(out_dir)
    if data_dir is None:
        data_dir = DEFAULT_DATA_DIR
    stats = _stats_df.copy() if _stats_df is not None else _build_stats(pathlib.Path(data_dir))
    stats["archetype"] = stats.apply(_classify, axis=1)

    arch_dir = out_dir / "Archetypes"
    written: list[pathlib.Path] = []
    counts: list[tuple[str, int]] = []

    for arch in ARCHETYPES:
        label = arch["label"]
        sub = stats[stats["archetype"] == label]
        pop = len(sub)
        counts.append((label, pop))
        top_pos = sub["position"].value_counts().index.tolist()[:3] if pop else []
        typical = " / ".join(top_pos) if top_pos else "—"
        slug = label.replace(" ", "_").replace("-", "_")
        path = arch_dir / f"{slug}.md"
        _write(path, _archetype_note(arch, pop, typical))
        written.append(path)

    idx_path = arch_dir / "_Archetypes_Index.md"
    _write(idx_path, _index_note(counts))
    written.append(idx_path)
    return written
