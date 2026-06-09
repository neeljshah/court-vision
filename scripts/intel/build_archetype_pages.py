"""
Build per-archetype hub pages for the CourtVision Intelligence vault.

Reads all 582 player notes from vault/Intelligence/Players/*.md, groups them
by archetype, then writes:
  vault/Intelligence/Archetypes/<slug>.md   — one hub per archetype
  vault/Intelligence/Archetypes_Index.md    — MOC table ranked by player count

Also backfills a  **Archetype page:** [[Archetypes/<slug>]]  line into each
player note header (idempotent: skipped if line already present).

Deterministic, no LLM, stdlib + pathlib only. Re-runs are safe.
"""
from __future__ import annotations

import re
import sys
import statistics
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
PLAYERS_DIR = ROOT / "vault" / "Intelligence" / "Players"
ARCHETYPES_DIR = ROOT / "vault" / "Intelligence" / "Archetypes"
INDEX_PATH = ROOT / "vault" / "Intelligence" / "Archetypes_Index.md"

HUB_START = "<!-- ARCHETYPE-HUB START -->"
HUB_END   = "<!-- ARCHETYPE-HUB END -->"

AS_OF = str(date.today())

# ---------------------------------------------------------------------------
# Canonical archetype descriptions (stub for anything not listed here)
# ---------------------------------------------------------------------------
ARCH_DESC: dict[str, str] = {
    "primary initiator / lead guard": (
        "The offensive engine — ball-dominant guard or wing who creates for himself "
        "and teammates, runs the pick-and-roll as the handler, and closes games. "
        "Expected to generate high-volume, high-difficulty looks while managing pace "
        "and protecting the ball."
    ),
    "playmaking guard": (
        "A combo guard who keeps the offense moving without necessarily anchoring it. "
        "Strong passer with solid A/TO, comfortable both as initiator and as off-ball "
        "threat, often used to relieve pressure from the primary creator."
    ),
    "playmaking big": (
        "A center or power forward with above-average court vision who can initiate "
        "from the elbow or short-roll, hand the ball off, and finish around the rim. "
        "Combines frontcourt size with guard-like decision-making."
    ),
    "dominant two-way big": (
        "Elite frontcourt player who anchors both ends — rim protection, defensive "
        "rebounding, and post or mid-range scoring on offense. Impact on both sides "
        "of the ball makes him the fulcrum of the team's identity."
    ),
    "rebounding big": (
        "High-rate offensive and defensive rebounder whose primary value is controlling "
        "the glass, providing second-chance points, and vacating spacing for others. "
        "Typically a roll-man or lob target on offense."
    ),
    "movement shooter": (
        "Wing or forward who scores efficiently off movement, cuts, and hand-offs. "
        "Gets open via screens and is a threat both from three and at mid-range on "
        "pull-ups. Versatile enough to spot-up but most dangerous in motion."
    ),
    "floor-spacing specialist": (
        "Designated shooter whose value comes primarily from standing ready at the "
        "perimeter and making opponents pay for help rotations. High catch-and-shoot "
        "efficiency, low usage, and minimal self-creation demand."
    ),
    "3&d wing": (
        "The connective tissue of modern rosters — three-point shooting combined with "
        "switchable on-ball defense. Expected to guard multiple positions, hit corner "
        "threes, and stay out of the way of ball-handlers."
    ),
    "role player": (
        "Complementary player whose contribution is defined situationally — spot-up "
        "shooting, cutting, defensive switching, or energy minutes. Rarely drives "
        "possession outcomes but fulfills a specific niche within the system."
    ),
    "high-usage scorer": (
        "Bucket-getter who commands significant offensive responsibility but may not "
        "be the primary playmaker. Lives off isolation, pull-up jumpers, and "
        "aggressive drives; usage and scoring volume are the defining traits."
    ),
    "high-usage shot creator": (
        "Self-creation specialist with elite off-the-dribble scoring ability. Combines "
        "high usage with a wide shot-creation menu (iso, PnR, step-backs). "
        "Distinct from a pure scorer: can manufacture shots regardless of help-defense."
    ),
    "stretch big": (
        "A frontcourt player who spaces the floor with mid-range or three-point "
        "shooting, pulling rim-protectors away from the paint to create driving lanes "
        "and cutting opportunities for teammates."
    ),
    "big": (
        "Traditional frontcourt player — rim presence, rebounding, and paint scoring "
        "are the primary contributions. Role may vary by team context; archetype label "
        "signals size/position rather than a defined offensive role."
    ),
    "interior scoring big": (
        "Post-up and paint-attack specialist who generates offense predominantly inside "
        "the arc. High-efficiency finisher who draws fouls and anchors the halfcourt "
        "offense from the high-post or low-post."
    ),
}


def _stub_desc(arch: str) -> str:
    return (
        f"Auto-generated archetype stub for '{arch}'. "
        "Players in this category share a common role identity; "
        "a canonical description has not yet been authored."
    )


def slug(arch: str) -> str:
    """'3&D Wing' → '3d_wing'"""
    s = arch.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s


# ---------------------------------------------------------------------------
# Parser (reuses _grab logic from write_playstyle_narratives.py)
# ---------------------------------------------------------------------------
NUM_RE = r"[-+]?\d*\.?\d+%?"


def _grab(text: str, label_pattern: str, value_pattern: str = NUM_RE):
    patterns = [
        rf"[-*]\s+\*\*(?:[^*\n]*?\s)?{label_pattern}\s*:?\s*\*\*\s*({value_pattern})",
        rf"\*\*(?:[^*\n]*?\s)?{label_pattern}\s*:?\s*\*\*\s*({value_pattern})",
        rf"\|\s*{label_pattern}\s*\|\s*({value_pattern})\s*\|",
        rf"(?:^|\n){label_pattern}\s*:\s*({value_pattern})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            v = m.group(1).strip()
            cleaned = v.rstrip("%").replace(",", "")
            try:
                f = float(cleaned)
                if v.endswith("%"):
                    return f / 100.0
                return f
            except (TypeError, ValueError):
                return v
    return None


def _grab_str(text: str, label_pattern: str):
    patterns = [
        rf"[-*]\s+\*\*(?:[^*\n]*?\s)?{label_pattern}\s*:?\s*\*\*\s*([^\n|]+?)\s*(?:\||\n|$)",
        rf"\*\*(?:[^*\n]*?\s)?{label_pattern}\s*:?\s*\*\*\s*([^\n|]+?)\s*(?:\||\n|$)",
        rf"\|\s*{label_pattern}\s*\|\s*([^\n|]+?)\s*\|",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def parse_player_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    p: dict[str, Any] = {"path": path, "text": text}

    m = re.search(r"^#\s+(.+?)\s*$", text, re.M)
    p["name"] = m.group(1).strip() if m else path.stem

    m = re.search(r"\*\*Archetype:\*\*\s*([^·\n]+)", text)
    p["archetype"] = m.group(1).strip() if m else "Role Player"

    m = re.search(r"\*\(secondary:\s*([^\)]+)\)\*", text)
    p["secondary"] = m.group(1).strip() if m else None

    m = re.search(r"\*\*Team:\*\*\s*\[\[([A-Z]{2,4})\]\]", text)
    p["team"] = m.group(1).strip() if m else "UNK"

    m = re.search(r"Tags:\s*(.+)$", text, re.M)
    p["tags"] = re.findall(r"`([^`]+)`", m.group(1)) if m else []

    p["usage_rate"]   = _grab(text, r"Usage rate")
    p["minutes"]      = _grab(text, r"Minutes per game")
    p["ast_pct"]      = _grab(text, r"AST %")
    p["three_share"]  = _grab(text, r"Pts 3pt share")
    p["paint_share"]  = _grab(text, r"Pts paint share")
    p["dreb"]         = _grab(text, r"DREB rate(?! rank)")
    p["drives"]       = _grab(text, r"Drives per game")
    p["ato"]          = _grab(text, r"AST to TOV")
    p["fg_allow"]     = _grab(text, r"FG % allowed")
    p["impact_rank"]  = _grab(text, r"Impact % rank")
    p["pie"]          = _grab(text, r"Pie mean")
    p["usage_rank"]   = _grab(text, r"Usage % rank")

    # top-1 strength label from S&W table
    best_str = None
    best_pct = -1
    for m2 in re.finditer(
        r"\|\s*([^|]+?)\s*\|\s*(\d+)(?:th|st|nd|rd)?\s*\|\s*([^|]+?)\s*\|", text
    ):
        metric = m2.group(1).strip()
        if metric.lower() in ("metric", "---"):
            continue
        try:
            pct = int(m2.group(2))
        except ValueError:
            continue
        if pct > best_pct:
            best_pct = pct
            best_str = metric
    p["top_strength"] = best_str

    # wiki link slug for Obsidian
    p["file_slug"] = path.stem  # e.g. 1626164_devin_booker

    return p


# ---------------------------------------------------------------------------
# Aggregate stats across a list of player dicts
# ---------------------------------------------------------------------------
def _median(vals: list) -> float | None:
    nums = [v for v in vals if isinstance(v, (int, float)) and v == v]
    return statistics.median(nums) if nums else None


def _pct(v) -> str:
    if v is None:
        return "—"
    if 0 <= v <= 1.0:
        return f"{v*100:.1f}%"
    return f"{v:.1f}%"


def _fmt(v, nd: int = 1) -> str:
    if v is None:
        return "—"
    return f"{float(v):.{nd}f}"


def fingerprint(players: list[dict]) -> str:
    def med(field):
        return _median([p[field] for p in players])

    rows = [
        ("Usage rate",     _pct(med("usage_rate"))),
        ("Minutes/g",      _fmt(med("minutes"), 1)),
        ("AST %",          _pct(med("ast_pct"))),
        ("3PT share",      _pct(med("three_share"))),
        ("Paint share",    _pct(med("paint_share"))),
        ("DREB %",         _pct(med("dreb"))),
        ("Drives/g",       _fmt(med("drives"), 1)),
        ("A/TO",           _fmt(med("ato"), 2)),
        ("FG% allowed",    _pct(med("fg_allow"))),
    ]
    lines = ["| Metric | Median |", "|---|---|"]
    for label, val in rows:
        lines.append(f"| {label} | {val} |")
    return "\n".join(lines)


def top15_table(players: list[dict]) -> str:
    def sort_key(p):
        ir = p.get("impact_rank")
        pie = p.get("pie")
        if isinstance(ir, (int, float)) and ir == ir:
            return -ir
        if isinstance(pie, (int, float)) and pie == pie:
            return -pie
        return 0

    ranked = sorted(players, key=sort_key)[:15]
    lines = [
        "| Name | Team | Usage% | Min/g | Top Strength |",
        "|---|---|---|---|---|",
    ]
    for p in ranked:
        usage = _pct(p["usage_rate"]) if p["usage_rate"] is not None else "—"
        mins  = _fmt(p["minutes"], 1) if p["minutes"] is not None else "—"
        strength = p["top_strength"] or "—"
        link = f"[[Players/{p['file_slug']}|{p['name']}]]"
        lines.append(f"| {link} | {p['team']} | {usage} | {mins} | {strength} |")
    return "\n".join(lines)


def team_distribution(players: list[dict]) -> str:
    counts: Counter = Counter(p["team"] for p in players)
    lines = ["| Team | Players |", "|---|---|"]
    for team, cnt in sorted(counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {team} | {cnt} |")
    return "\n".join(lines)


def common_tags(players: list[dict], top_n: int = 5) -> str:
    c: Counter = Counter()
    for p in players:
        for t in p["tags"]:
            c[t] += 1
    if not c:
        return "_No tags found_"
    parts = [f"`{tag}` ({cnt})" for tag, cnt in c.most_common(top_n)]
    return ", ".join(parts)


def comparable_archetypes(
    arch: str,
    all_players: list[dict],
    top_n: int = 3,
) -> str:
    """Jaccard similarity on tag sets across archetypes."""
    from_tags: set[str] = set()
    target_arch_lower = arch.lower()
    arch_tag_sets: dict[str, set[str]] = defaultdict(set)

    for p in all_players:
        a_low = p["archetype"].lower()
        for t in p["tags"]:
            arch_tag_sets[a_low].add(t)
        if a_low == target_arch_lower:
            for t in p["tags"]:
                from_tags.add(t)

    scores: list[tuple[float, str]] = []
    for other_arch, other_tags in arch_tag_sets.items():
        if other_arch == target_arch_lower:
            continue
        if not from_tags or not other_tags:
            continue
        union = from_tags | other_tags
        inter = from_tags & other_tags
        j = len(inter) / len(union) if union else 0.0
        scores.append((j, other_arch))

    scores.sort(key=lambda x: -x[0])
    if not scores:
        return "_None computed_"
    top = scores[:top_n]
    canonical = {a.lower(): a for p in all_players for a in [p["archetype"]]}
    parts = []
    for _, other in top:
        display = canonical.get(other, other.title())
        sl = slug(display)
        parts.append(f"[[Archetypes/{sl}|{display}]]")
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Hub page writer
# ---------------------------------------------------------------------------
def arch_hub(
    arch: str,
    players: list[dict],
    all_players: list[dict],
) -> str:
    n_players = len(players)
    n_teams   = len({p["team"] for p in players})
    sl        = slug(arch)

    desc = ARCH_DESC.get(arch.lower(), _stub_desc(arch))

    header = f"""---
archetype: "{arch}"
n_players: {n_players}
n_teams_with_archetype: {n_teams}
as_of: "{AS_OF}"
---

# {arch}

{HUB_START}

## Profile

{desc}

## Statistical Fingerprint

{fingerprint(players)}

## Top 15 by Impact

{top15_table(players)}

## Distribution by Team

{team_distribution(players)}

## Tags Commonly Co-occurring

{common_tags(players)}

## Comparable Archetypes

{comparable_archetypes(arch, all_players)}

{HUB_END}
"""
    return header


# ---------------------------------------------------------------------------
# Player-note back-link injection (idempotent)
# ---------------------------------------------------------------------------
ARCH_PAGE_MARKER = "**Archetype page:**"


def inject_arch_link(p: dict) -> bool:
    """Add  **Archetype page:** [[Archetypes/<slug>]]  below the archetype line."""
    text = p["text"]
    sl = slug(p["archetype"])
    link_line = f"{ARCH_PAGE_MARKER} [[Archetypes/{sl}]]"

    if ARCH_PAGE_MARKER in text:
        return False  # already present

    # Insert right after the Archetype line
    arch_re = re.compile(
        r"(\*\*Archetype:\*\*[^\n]*(?:\n\*\(secondary:[^\n]*\))?\n)"
    )
    m = arch_re.search(text)
    if m:
        new_text = text[: m.end()] + link_line + "\n" + text[m.end() :]
    else:
        # Fallback: insert after first heading line
        m2 = re.search(r"(^#[^\n]*\n)", text, re.M)
        if m2:
            new_text = text[: m2.end()] + link_line + "\n" + text[m2.end() :]
        else:
            new_text = link_line + "\n" + text

    if new_text != text:
        p["path"].write_text(new_text, encoding="utf-8")
        return True
    return False


# ---------------------------------------------------------------------------
# Archetypes Index MOC
# ---------------------------------------------------------------------------
def build_index(arch_groups: dict[str, list[dict]]) -> str:
    lines = [
        "<!-- ARCHETYPES-INDEX v1 -->",
        "# Archetypes Index",
        "",
        f"Generated {AS_OF}. {sum(len(v) for v in arch_groups.values())} players across "
        f"{len(arch_groups)} archetypes.",
        "",
        "| Archetype | Players | Description |",
        "|---|---|---|",
    ]
    for arch, players in sorted(arch_groups.items(), key=lambda x: -len(x[1])):
        sl = slug(arch)
        desc_snippet = ARCH_DESC.get(arch.lower(), _stub_desc(arch))[:80].rstrip() + "…"
        lines.append(
            f"| [[Archetypes/{sl}|{arch}]] | {len(players)} | {desc_snippet} |"
        )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(dry_run: bool = False) -> None:
    print("Loading player files …", file=sys.stderr)
    all_players: list[dict] = []
    errors = 0
    for f in sorted(PLAYERS_DIR.glob("*.md")):
        try:
            all_players.append(parse_player_file(f))
        except Exception as exc:
            print(f"[WARN] {f.name}: {exc}", file=sys.stderr)
            errors += 1

    print(f"  Loaded {len(all_players)} players ({errors} errors)", file=sys.stderr)

    # Group by primary archetype
    arch_groups: dict[str, list[dict]] = defaultdict(list)
    for p in all_players:
        arch_groups[p["archetype"]].append(p)

    # Create Archetypes dir
    if not dry_run:
        ARCHETYPES_DIR.mkdir(parents=True, exist_ok=True)

    written_hubs = 0
    for arch, players in sorted(arch_groups.items(), key=lambda x: -len(x[1])):
        sl = slug(arch)
        out_path = ARCHETYPES_DIR / f"{sl}.md"
        content = arch_hub(arch, players, all_players)

        if not dry_run:
            existing = out_path.read_text(encoding="utf-8") if out_path.exists() else ""
            # Replace block if already exists; otherwise write fresh
            if HUB_START in existing and HUB_END in existing:
                inner_new = re.search(
                    re.escape(HUB_START) + r"(.*?)" + re.escape(HUB_END),
                    content,
                    re.S,
                ).group(0)
                new_content = re.sub(
                    re.escape(HUB_START) + r".*?" + re.escape(HUB_END),
                    inner_new,
                    existing,
                    flags=re.S,
                )
            else:
                new_content = content
            out_path.write_text(new_content, encoding="utf-8")
        written_hubs += 1

    # Write index
    idx_content = build_index(arch_groups)
    if not dry_run:
        INDEX_PATH.write_text(idx_content, encoding="utf-8")

    # Back-fill player notes
    injected = 0
    if not dry_run:
        for p in all_players:
            try:
                if inject_arch_link(p):
                    injected += 1
            except Exception as exc:
                print(f"[WARN] inject {p['path'].name}: {exc}", file=sys.stderr)

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print(f"\n=== build_archetype_pages summary ===")
    print(f"  Players parsed  : {len(all_players)}")
    print(f"  Archetypes found: {len(arch_groups)}")
    print(f"  Hub pages written : {written_hubs}  -> {ARCHETYPES_DIR}/")
    print(f"  Archetypes_Index  : {INDEX_PATH}")
    print(f"  Player notes backfilled: {injected}")

    # -----------------------------------------------------------------------
    # Print 2 sample hub pages
    # -----------------------------------------------------------------------
    sample_archs = sorted(arch_groups.items(), key=lambda x: -len(x[1]))[:2]
    print("\n" + "=" * 60)
    for arch, players in sample_archs:
        sl = slug(arch)
        out_path = ARCHETYPES_DIR / f"{sl}.md"
        print(f"\n--- SAMPLE: {out_path} ---\n")
        if out_path.exists():
            raw = out_path.read_text(encoding="utf-8")
            print(raw.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace"))
        else:
            raw = arch_hub(arch, players, all_players)
            print(raw.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace"))
        print()


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    main(dry_run=dry)
