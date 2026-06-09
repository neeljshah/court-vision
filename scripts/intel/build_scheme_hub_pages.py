"""
build_scheme_hub_pages.py
-------------------------
Build per-scheme hub pages in vault/Intelligence/Schemes/<slug>.md.
Also writes Schemes_Index.md and injects a "Scheme page" backlink
into each team note's Scheme Tag section.

Idempotent — re-runs replace blocks via <!-- SCHEME-HUB START/END --> markers.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
TEAMS_DIR   = ROOT / "vault" / "Intelligence" / "Teams"
PLAYERS_DIR = ROOT / "vault" / "Intelligence" / "Players"
SCHEMES_DIR = ROOT / "vault" / "Intelligence" / "Schemes"
INDEX_PATH  = ROOT / "vault" / "Intelligence" / "Schemes_Index.md"
PARQUET     = ROOT / "data" / "cache" / "atlas_team_defensive_scheme.parquet"

HUB_START = "<!-- SCHEME-HUB START -->"
HUB_END   = "<!-- SCHEME-HUB END -->"
AS_OF     = str(date.today())

# ---------------------------------------------------------------------------
# Hard-coded scheme definitions (basketball prose, 2-3 sentences each)
# ---------------------------------------------------------------------------
SCHEME_DEFS: dict[str, str] = {
    "DROP COVERAGE": (
        "The big sags below the screen in pick-and-roll, trading three-point exposure "
        "for paint protection. It forces ball-handlers into pull-up mid-rangers or floaters "
        "rather than open corner threes. Effective against non-shooting bigs; exploitable by "
        "elite PnR handlers who can pull up from the elbows."
    ),
    "SWITCH HEAVY": (
        "Defenders switch every screen action regardless of size mismatch, eliminating "
        "separation and keeping every shot contested. It neutralises well-designed PnR "
        "choreography but invites post-up and isolation counters against smaller defenders. "
        "High-athleticism rosters lean into this to compensate for scheme complexity."
    ),
    "PAINT-FIRST DEFENSE": (
        "Defenders shade toward the paint, accepting contested mid-range looks to deny "
        "paint touches and rim attempts. Opposing offenses are funneled into the mid-range "
        "desert or forced into low-percentage post-ups. Works best when the defense can "
        "recover and contest perimeter shots on kick-outs."
    ),
    "PACE CONTROL": (
        "The defense actively dictates tempo — slowing transitions, forcing early shot-clock "
        "resets, and limiting transition opportunities. Half-court grind teams use this to "
        "neutralise athleticism and create even defensive matchups. Effective against "
        "up-tempo offenses; punishable by disciplined halfcourt execution."
    ),
    "ISO FORCE": (
        "The defense intentionally funnels opponents into isolation situations, trading "
        "against high volume off-ball movement for predictable 1-on-1 assignments. "
        "It condenses spacing and dares opponents to beat their man off the dribble. "
        "Works against teams with weak iso scorers; backfires vs. high-usage creators."
    ),
    "HELP DEFENSE": (
        "Defenders rotate aggressively from weakside to provide help on drives and rolls, "
        "relying on rotational communication to close out shooters afterward. This scheme "
        "suppresses paint efficiency but can leave shooters open on skip passes. "
        "Teams with elite weak-side defenders — long wings, rim protectors — run this best."
    ),
    "PERIMETER DENIAL": (
        "On-ball defenders deny entry passes and push initiators off their preferred spots, "
        "extending pressure 25+ feet from the rim. It disrupts the offensive initiation "
        "point and inflates ball-movement requirements. High-energy scheme prone to "
        "backdoor cuts and transition surrenders on turnovers."
    ),
    "ACTIVE CLOSEOUTS": (
        "Defenders sprint from help position to contest catch-and-shoot opportunities "
        "at high velocity, accepting foul risk to deter three-point attempts. "
        "Contest frequency is elevated league-wide; effective for teams with high-motor "
        "wings. Can leave drive lanes open if the closeout is over-aggressive."
    ),
    "BALANCED": (
        "No single defensive axis dominates — the team sits near league-average on "
        "drop/switch tendency, paint protection, perimeter denial, and closeout intensity. "
        "Allows the coaching staff to adjust scheme game-by-game without a structural tell. "
        "Upside: versatility. Downside: no elite dimension to lean on."
    ),
}

# Which axis z-score is most relevant for ranking each scheme (key in scheme_axes dict)
SCHEME_RANK_AXIS: dict[str, str] = {
    "DROP COVERAGE":      "drop_score",
    "SWITCH HEAVY":       "drop_score",        # switch = low drop_score
    "PAINT-FIRST DEFENSE":"paint_protection_score",
    "PACE CONTROL":       "pace_control_score",
    "ISO FORCE":          "iso_force_score",
    "HELP DEFENSE":       "paint_protection_score",
    "PERIMETER DENIAL":   "perimeter_denial_score",
    "ACTIVE CLOSEOUTS":   "closeout_score",
    "BALANCED":           "quality_z",         # ranked by quality z (lowest = most balanced)
}

# Human-readable axis label
SCHEME_AXIS_LABEL: dict[str, str] = {
    "DROP COVERAGE":      "Drop vs Switch z",
    "SWITCH HEAVY":       "Drop vs Switch z (inverted)",
    "PAINT-FIRST DEFENSE":"Paint Protection z",
    "PACE CONTROL":       "Pace Control z",
    "ISO FORCE":          "ISO Force z",
    "HELP DEFENSE":       "Paint Protection z",
    "PERIMETER DENIAL":   "Perimeter Denial z",
    "ACTIVE CLOSEOUTS":   "Closeout Intensity z",
    "BALANCED":           "Quality z",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _j(val: Any) -> dict | list | Any:
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, ValueError):
            return val
    return val


def _slug(tag: str) -> str:
    return tag.lower().replace(" ", "_").replace("-", "_")


def _upsert_block(text: str, start_marker: str, end_marker: str, new_block: str) -> str:
    """Replace content between markers; append if markers absent."""
    pattern = re.compile(
        re.escape(start_marker) + r".*?" + re.escape(end_marker),
        re.DOTALL,
    )
    replacement = f"{start_marker}\n{new_block}\n{end_marker}"
    if pattern.search(text):
        return pattern.sub(replacement, text)
    return text + "\n" + replacement + "\n"


# ---------------------------------------------------------------------------
# 1. Load parquet → build per-team scheme_axes dict
# ---------------------------------------------------------------------------

df = pd.read_parquet(PARQUET)

team_axes: dict[str, dict] = {}           # tri → axes dict
team_dominant: dict[str, str] = {}        # tri → dominant tag
team_all_tags: dict[str, list[str]] = {}  # tri → list of tags
team_imposed: dict[str, dict] = {}        # tri → imposed_deviations dict
team_rim: dict[str, dict] = {}            # tri → rim_protection dict
team_perim: dict[str, dict] = {}          # tri → perimeter_pressure dict

for _, row in df.iterrows():
    tri = row["team_tricode"]
    cs  = _j(row["coverage_scheme"])
    sa  = _j(row["scheme_axes"])
    imp = _j(row["imposed_deviations"])
    rim = _j(row["rim_protection"])
    per = _j(row["perimeter_pressure"])

    dom = cs.get("dominant_tag", "") if isinstance(cs, dict) else str(row.get("value", ""))
    tags = cs.get("all_tags", [dom]) if isinstance(cs, dict) else [dom]

    team_axes[tri]    = sa if isinstance(sa, dict) else {}
    team_dominant[tri]= dom
    team_all_tags[tri]= tags
    team_imposed[tri] = imp if isinstance(imp, dict) else {}
    team_rim[tri]     = rim if isinstance(rim, dict) else {}
    team_perim[tri]   = per if isinstance(per, dict) else {}


# ---------------------------------------------------------------------------
# 2. Collect all distinct dominant tags (from Scheme Matrix dominant tags)
# ---------------------------------------------------------------------------

all_dominant_tags: set[str] = set(team_dominant.values())


# ---------------------------------------------------------------------------
# 3. Parse player notes for best/worst scheme
# ---------------------------------------------------------------------------

player_best:  dict[str, list[tuple[str, str]]] = {t: [] for t in all_dominant_tags}
player_worst: dict[str, list[tuple[str, str]]] = {t: [] for t in all_dominant_tags}

BEST_RE  = re.compile(r"\*\*Vs scheme — Best scheme:\*\* (.+)")
WORST_RE = re.compile(r"\*\*Vs scheme — Worst scheme:\*\* (.+)")
TEAM_RE  = re.compile(r"\*\*Team:\*\* \[\[([A-Z]+)\]\]")
NAME_RE  = re.compile(r"^#\s+(.+)", re.MULTILINE)

for pf in PLAYERS_DIR.glob("*.md"):
    text = pf.read_text(encoding="utf-8", errors="replace")
    bm = BEST_RE.search(text)
    wm = WORST_RE.search(text)
    tm = TEAM_RE.search(text)
    nm = NAME_RE.search(text)

    team = tm.group(1) if tm else "?"
    name = nm.group(1) if nm else pf.stem

    if bm:
        tag = bm.group(1).strip()
        if tag in player_best:
            player_best[tag].append((name, team))
    if wm:
        tag = wm.group(1).strip()
        if tag in player_worst:
            player_worst[tag].append((name, team))


# ---------------------------------------------------------------------------
# 4. Compute average imposed deviations per scheme (across teams that run it)
# ---------------------------------------------------------------------------

def avg_imposed_for_scheme(scheme_tag: str) -> dict[str, float]:
    """Average imposed deviation z-scores for teams whose dominant tag == scheme_tag."""
    rows = [team_imposed[t] for t, d in team_dominant.items() if d == scheme_tag and t in team_imposed]
    if not rows:
        return {}
    keys = set()
    for r in rows:
        keys.update(r.keys())
    result: dict[str, float] = {}
    for k in keys:
        vals = [r[k] for r in rows if isinstance(r.get(k), (int, float))]
        if vals:
            result[k] = sum(vals) / len(vals)
    return result


# ---------------------------------------------------------------------------
# 5. Build comparable schemes (by axis correlation heuristic)
# ---------------------------------------------------------------------------

COMPARABLE: dict[str, list[str]] = {
    "DROP COVERAGE":      ["PACE CONTROL", "PAINT-FIRST DEFENSE"],
    "SWITCH HEAVY":       ["PERIMETER DENIAL", "ACTIVE CLOSEOUTS"],
    "PAINT-FIRST DEFENSE":["DROP COVERAGE", "HELP DEFENSE"],
    "PACE CONTROL":       ["DROP COVERAGE", "ISO FORCE"],
    "ISO FORCE":          ["PACE CONTROL", "DROP COVERAGE"],
    "HELP DEFENSE":       ["PAINT-FIRST DEFENSE", "SWITCH HEAVY"],
    "PERIMETER DENIAL":   ["SWITCH HEAVY", "ACTIVE CLOSEOUTS"],
    "ACTIVE CLOSEOUTS":   ["PERIMETER DENIAL", "SWITCH HEAVY"],
    "BALANCED":           ["HELP DEFENSE", "PAINT-FIRST DEFENSE"],
}


# ---------------------------------------------------------------------------
# 6. Write scheme hub pages
# ---------------------------------------------------------------------------

SCHEMES_DIR.mkdir(parents=True, exist_ok=True)
n_pages_written = 0

def _build_hub_content(tag: str) -> str:
    slug = _slug(tag)
    teams_for_tag   = [t for t, d in team_dominant.items() if d == tag]
    n_teams         = len(teams_for_tag)
    rank_axis_key   = SCHEME_RANK_AXIS.get(tag, "drop_score")
    axis_label      = SCHEME_AXIS_LABEL.get(tag, rank_axis_key)
    definition      = SCHEME_DEFS.get(tag, f"A defensive scheme emphasizing {tag.lower()} principles, characterized by the axis z-scores below.")
    comparables     = COMPARABLE.get(tag, [])
    avg_imp         = avg_imposed_for_scheme(tag)

    # Sort teams by relevant axis (descending for most, ascending for SWITCH HEAVY)
    def team_sort_key(tri: str) -> float:
        axes = team_axes.get(tri, {})
        v = axes.get(rank_axis_key, 0.0) or 0.0
        return -v if tag != "SWITCH HEAVY" else v  # switch wants lowest drop_score

    sorted_teams = sorted(teams_for_tag, key=team_sort_key)

    # --- YAML frontmatter ---
    lines = [
        "---",
        f"scheme: {tag}",
        f"slug: {slug}",
        f"axis: {axis_label}",
        f"n_teams_running: {n_teams}",
        f"as_of: {AS_OF}",
        "---",
        "",
        f"# {tag} — Scheme Hub",
        "",
        "## What it is",
        "",
        definition,
        "",
        "## Teams that run it",
        "",
        f"Ranked by {axis_label} (primary axis).",
        "",
        f"| Team | {axis_label} | DefRtg | Pace |",
        f"|------|{'-'*len(axis_label+' z')}|--------|------|",
    ]

    for tri in sorted_teams:
        axes    = team_axes.get(tri, {})
        ax_val  = axes.get(rank_axis_key)
        ax_str  = f"{ax_val:+.3f}" if isinstance(ax_val, (int, float)) and ax_val == ax_val else "—"
        # get DefRtg / Pace from perimeter or rim context
        perim   = team_perim.get(tri, {})
        rim_d   = team_rim.get(tri, {})
        # ratings pulled from axes extra keys
        axes_full = team_axes.get(tri, {})
        def_rtg = "—"
        pace    = "—"
        # try reading from parquet row directly
        row_match = df[df["team_tricode"] == tri]
        if not row_match.empty:
            rc = _j(row_match.iloc[0]["ratings_context"])
            if isinstance(rc, dict):
                dr = rc.get("def_rtg")
                pc = rc.get("pace")
                def_rtg = f"{dr:.1f}" if isinstance(dr, float) else str(dr) if dr else "—"
                pace    = f"{pc:.1f}" if isinstance(pc, float) else str(pc) if pc else "—"
        lines.append(f"| [[{tri}]] | {ax_str} | {def_rtg} | {pace} |")

    lines += [
        "",
        "## Statistical fingerprint",
        "",
        "Average imposed deviations on opponents (σ from league mean) across teams running this scheme:",
        "",
        "| Feature | Avg Δ (σ) |",
        "|---------|-----------|",
    ]
    # Top 8 by abs value
    top_imp = sorted(avg_imp.items(), key=lambda kv: abs(kv[1]), reverse=True)[:8]
    if top_imp:
        for feat, val in top_imp:
            sign = "+" if val >= 0 else ""
            lines.append(f"| {feat} | {sign}{val:.3f} |")
    else:
        lines.append("| — | — |")

    lines += [
        "",
        "## Players who thrive against it",
        "",
        f"Players whose **Best scheme** is {tag} (scan of 582 player dossiers).",
        "",
        "| Player | Team |",
        "|--------|------|",
    ]
    best_list = player_best.get(tag, [])[:10]
    if best_list:
        for name, team in best_list:
            lines.append(f"| {name} | [[{team}]] |")
    else:
        lines.append("| — | — |")

    lines += [
        "",
        "## Players who struggle against it",
        "",
        f"Players whose **Worst scheme** is {tag} (scan of 582 player dossiers).",
        "",
        "| Player | Team |",
        "|--------|------|",
    ]
    worst_list = player_worst.get(tag, [])[:10]
    if worst_list:
        for name, team in worst_list:
            lines.append(f"| {name} | [[{team}]] |")
    else:
        lines.append("| — | — |")

    lines += [
        "",
        "## Comparable schemes",
        "",
    ]
    if comparables:
        for c in comparables:
            cslug = _slug(c)
            lines.append(f"- [[Schemes/{cslug}|{c}]]")
    else:
        lines.append("- _none identified_")

    lines += [""]
    return "\n".join(lines)


for tag in sorted(all_dominant_tags):
    slug      = _slug(tag)
    out_path  = SCHEMES_DIR / f"{slug}.md"
    content   = _build_hub_content(tag)
    # Wrap in idempotent markers
    wrapped   = f"{HUB_START}\n{content}\n{HUB_END}\n"

    if out_path.exists():
        existing = out_path.read_text(encoding="utf-8")
        new_text = _upsert_block(existing, HUB_START, HUB_END, content)
    else:
        new_text = wrapped

    out_path.write_text(new_text, encoding="utf-8")
    n_pages_written += 1
    print(f"  wrote {out_path.name}")


# ---------------------------------------------------------------------------
# 7. Write Schemes_Index.md
# ---------------------------------------------------------------------------

SCHEME_SUMMARIES: dict[str, str] = {
    "DROP COVERAGE":      "Big sags under screen; concedes elbows, protects paint",
    "SWITCH HEAVY":       "Switch all screens regardless of mismatch; kills PnR separation",
    "PAINT-FIRST DEFENSE":"Shade toward paint; force mid-range, deny rim",
    "PACE CONTROL":       "Dictate half-court tempo; limit transition opportunities",
    "ISO FORCE":          "Funnel opponents into predictable 1-on-1 isolation assignments",
    "HELP DEFENSE":       "Aggressive weakside rotation; closes shooters after helping on drives",
    "PERIMETER DENIAL":   "Extend pressure 25+ ft; disrupt offensive initiation point",
    "ACTIVE CLOSEOUTS":   "Sprint closeouts at high velocity; contest catch-and-shoot at cost of drive lanes",
    "BALANCED":           "No dominant axis; versatile scheme-by-matchup approach",
}

idx_lines = [
    "# Defensive Scheme Index",
    "",
    f"*Auto-generated by build_scheme_hub_pages.py — {AS_OF}*",
    "",
    "Hub pages for each distinct defensive scheme tag across all 30 NBA teams.",
    "",
    "| Scheme | Teams | Summary |",
    "|--------|-------|---------|",
]
for tag in sorted(all_dominant_tags):
    slug    = _slug(tag)
    n       = len([t for t, d in team_dominant.items() if d == tag])
    summary = SCHEME_SUMMARIES.get(tag, f"{tag} scheme")
    idx_lines.append(f"| [[Schemes/{slug}\\|{tag}]] | {n} | {summary} |")

idx_lines += [
    "",
    "## All scheme pages",
    "",
]
for tag in sorted(all_dominant_tags):
    slug = _slug(tag)
    idx_lines.append(f"- [[Schemes/{slug}|{tag}]]")

idx_lines.append("")
INDEX_PATH.write_text("\n".join(idx_lines), encoding="utf-8")
print(f"  wrote {INDEX_PATH.name}")


# ---------------------------------------------------------------------------
# 8. Inject "Scheme page" backlink into each team note
# ---------------------------------------------------------------------------

SCHEME_TAG_RE = re.compile(
    r"(## Scheme Tag.*?)(<!-- SCHEME-AUTO START -->|## Offensive Tempo)",
    re.DOTALL,
)
BACKLINK_RE = re.compile(r"\*\*Scheme page:\*\*.*\n?")

n_teams_linked = 0

for tf in TEAMS_DIR.glob("*.md"):
    tri  = tf.stem
    tag  = team_dominant.get(tri, "")
    if not tag:
        continue
    slug = _slug(tag)
    text = tf.read_text(encoding="utf-8")

    backlink_line = f"**Scheme page:** [[Schemes/{slug}|{tag}]]\n"

    # Remove old backlink if present (idempotent)
    text_clean = BACKLINK_RE.sub("", text)

    # Insert after "- **Dominant tag:** ..." line
    dom_tag_re = re.compile(r"(- \*\*Dominant tag:\*\* .+\n)")
    if dom_tag_re.search(text_clean):
        new_text = dom_tag_re.sub(r"\1" + backlink_line, text_clean, count=1)
        if new_text != text:
            tf.write_text(new_text, encoding="utf-8")
            n_teams_linked += 1
    # If nothing changed (already identical), still count
    elif backlink_line in text:
        n_teams_linked += 1


# ---------------------------------------------------------------------------
# 9. Count players categorised
# ---------------------------------------------------------------------------

n_players_categorized = sum(len(v) for v in player_best.values()) + sum(len(v) for v in player_worst.values())

# ---------------------------------------------------------------------------
# 10. Summary
# ---------------------------------------------------------------------------

print()
print("=" * 50)
print(f"n_schemes          : {len(all_dominant_tags)}")
print(f"n_pages_written    : {n_pages_written}")
print(f"n_teams_linked     : {n_teams_linked}")
print(f"n_players_categorized: {n_players_categorized}")
print(f"index              : {INDEX_PATH}")
print("=" * 50)

# ---------------------------------------------------------------------------
# 11. Print 2 sample outputs for verification
# ---------------------------------------------------------------------------

sample_tags = ["DROP COVERAGE", "SWITCH HEAVY"]
for tag in sample_tags:
    slug = _slug(tag)
    p = SCHEMES_DIR / f"{slug}.md"
    if p.exists():
        print(f"\n{'='*60}")
        print(f"SAMPLE: {p}")
        print("="*60)
        print(p.read_text(encoding="utf-8")[:3000])
