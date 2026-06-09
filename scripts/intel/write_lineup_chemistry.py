"""
Insert a "## Lineup Chemistry (CV-tracked)" block into each team note.

Source: data/intelligence/pair_chemistry.parquet
  - 998 player-pair rows with chemistry_score, dominant_feature, top3_features,
    sample size (n_games), and z-scores across 14 CV-derived behavior features.

Per team, rank the strongest in-team pairs by |chemistry_score|, show top 5 positive
+ top 3 negative (anti-chemistry) with the feature that drives the signal.

Idempotent via <!-- LINEUP-CHEMISTRY START --> / <!-- LINEUP-CHEMISTRY END -->.
"""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PLAYERS_DIR = ROOT / "vault" / "Intelligence" / "Players"
TEAMS_DIR = ROOT / "vault" / "Intelligence" / "Teams"
PAIR_PARQUET = ROOT / "data" / "intelligence" / "pair_chemistry.parquet"

MARK_START = "<!-- LINEUP-CHEMISTRY START -->"
MARK_END = "<!-- LINEUP-CHEMISTRY END -->"

FEATURE_LABEL = {
    "paint_dwell_pct": "paint dwell",
    "touches_per_100frames": "touches",
    "preshot_velocity_peak": "pre-shot burst",
    "drive_rate": "drives",
    "paint_approach_rate": "paint approaches",
    "fast_break_rate": "fast breaks",
    "potential_assists": "potential assists",
    "possession_duration_avg": "possession length",
    "avg_spacing": "spacing",
    "velocity_mean": "movement speed",
    "isolation_rate": "iso rate",
    "shot_zone_paint_pct": "paint shot share",
    "shot_zone_3pt_pct": "3PT shot share",
    "contested_shot_rate": "contested-shot rate",
}


def _player_team_and_link():
    """pid (str) -> (tri, slug_full, name) by scanning player notes."""
    out = {}
    for f in PLAYERS_DIR.glob("*.md"):
        pid = f.stem.split("_", 1)[0]
        try:
            t = f.read_text(encoding="utf-8")
        except Exception:
            continue
        m_team = re.search(r"\*\*Team:\*\*\s*\[\[([A-Z]{3})\]\]", t)
        m_name = re.search(r"^#\s+(.+?)\s*$", t, re.M)
        out[pid] = (
            m_team.group(1) if m_team else None,
            f.stem,
            m_name.group(1).strip() if m_name else pid,
        )
    return out


def _label_feature(raw: str) -> str:
    return FEATURE_LABEL.get(raw, raw.replace("_", " "))


def _render_pairs(pairs, header_word, n=5):
    L = []
    L.append("| # | Pair | Dominant signal | Δ (σ) | n_games |")
    L.append("|---|---|---|---|---|")
    for i, p in enumerate(pairs[:n], 1):
        link_a = f"[[{p['slug_a']}\\|{p['name_a']}]]"
        link_b = f"[[{p['slug_b']}\\|{p['name_b']}]]"
        feat_label = _label_feature(p["dominant_feature"])
        z = p["max_abs_z"] if p["chemistry_score"] >= 0 else -abs(p["max_abs_z"])
        L.append(f"| {i} | {link_a} + {link_b} | {feat_label} | {z:+.2f} | {int(p['n_games'])} |")
    return "\n".join(L)


def _build_block(team_tri: str, pairs):
    # Pairs already sorted: positive desc, then negative asc
    pos = [p for p in pairs if p["chemistry_score"] > 0][:5]
    neg = [p for p in pairs if p["chemistry_score"] < 0]
    neg = sorted(neg, key=lambda p: p["chemistry_score"])[:3]
    if not pos and not neg:
        return None

    L = []
    L.append("*CV pair-chemistry (Δ in behavior z-space when player A shares the court with player B vs. without). Sample = CV-tracked games only.*")
    L.append("")
    if pos:
        L.append("**Strongest in-team chemistry**")
        L.append("")
        L.append(_render_pairs(pos, "with"))
        L.append("")
    if neg:
        L.append("**Anti-chemistry (lineups that don't fit)**")
        L.append("")
        L.append(_render_pairs(neg, "with"))
        L.append("")
    return "\n".join(L)


def _upsert(text: str, block_md: str) -> str:
    full = f"\n## Lineup Chemistry (CV-tracked)\n\n{MARK_START}\n\n{block_md}\n{MARK_END}\n"
    if MARK_START in text and MARK_END in text:
        return re.sub(
            r"\n## Lineup Chemistry \(CV-tracked\)\s*\n\s*" + re.escape(MARK_START) +
            r".*?" + re.escape(MARK_END) + r"\n?",
            full, text, flags=re.S,
        )
    # Insert before the SCHEME-AUTO START block (after Roster Dossiers)
    m = re.search(r"\n<!-- SCHEME-AUTO START -->", text)
    if m:
        return text[:m.start()] + full + text[m.start():]
    m = re.search(r"\n<!-- ROSTER-AUTO START -->", text)
    if m:
        return text[:m.start()] + full + text[m.start():]
    return text.rstrip() + "\n" + full


def main():
    import pandas as pd
    if not PAIR_PARQUET.exists():
        print("pair_chemistry.parquet not found")
        return

    df = pd.read_parquet(PAIR_PARQUET)
    df = df.dropna(subset=["player_A_id", "player_B_id", "chemistry_score"])
    df["player_A_id"] = df["player_A_id"].astype(int).astype(str)
    df["player_B_id"] = df["player_B_id"].astype(int).astype(str)

    player_map = _player_team_and_link()

    # Build per-team pair list (both players on same team)
    by_team = {}
    for _, r in df.iterrows():
        a_info = player_map.get(r["player_A_id"])
        b_info = player_map.get(r["player_B_id"])
        if not a_info or not b_info:
            continue
        tri_a, slug_a, name_a = a_info
        tri_b, slug_b, name_b = b_info
        if not tri_a or tri_a != tri_b:
            continue
        # dedupe symmetric pairs by sorted ids
        key = tuple(sorted((r["player_A_id"], r["player_B_id"])))
        existing = by_team.setdefault(tri_a, {}).get(key)
        record = {
            "slug_a": slug_a, "name_a": str(r["player_A_name"]) or name_a,
            "slug_b": slug_b, "name_b": str(r["player_B_name"]) or name_b,
            "chemistry_score": float(r["chemistry_score"]),
            "max_abs_z": float(r["max_abs_z"]),
            "dominant_feature": str(r["dominant_feature"]),
            "n_games": int(r["n_games"]),
        }
        if not existing or abs(record["chemistry_score"]) > abs(existing["chemistry_score"]):
            by_team[tri_a][key] = record

    # Sort each team's pairs by signed chemistry (positive first, then negative)
    updated = 0
    for tri, pairs_map in by_team.items():
        pairs = list(pairs_map.values())
        # sort: positives by descending, negatives separately
        pairs_sorted = sorted(pairs, key=lambda p: -p["chemistry_score"])
        block = _build_block(tri, pairs_sorted)
        if not block:
            continue
        team_file = TEAMS_DIR / f"{tri}.md"
        if not team_file.exists():
            continue
        text = team_file.read_text(encoding="utf-8")
        new = _upsert(text, block)
        if new != text:
            team_file.write_text(new, encoding="utf-8")
            updated += 1
    print(f"teams_with_chemistry: {len(by_team)}")
    print(f"teams_updated: {updated}")


if __name__ == "__main__":
    main()
