"""
Add a "## Comparable Players" section to every player note in
vault/Intelligence/Players/<id>_<slug>.md.

Two sources, merged:
  1. CV-based similarity from data/intelligence/player_similarity.parquet
     (Euclidean distance in 19-d z-space, ~221 players have entries).
  2. Archetype + usage cohort fallback for players the CV index doesn't cover —
     same primary archetype, smallest |usage_rate| delta, top 5.

Idempotent via <!-- COMPARABLES START --> / <!-- COMPARABLES END -->.
Inserted after the "## Playstyle Narrative" block. UTF-8 output.
"""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PLAYERS_DIR = ROOT / "vault" / "Intelligence" / "Players"
SIM_PARQUET = ROOT / "data" / "intelligence" / "player_similarity.parquet"

MARK_START = "<!-- COMPARABLES START -->"
MARK_END = "<!-- COMPARABLES END -->"


def _parse_player(text: str) -> dict:
    d = {}
    m = re.search(r"^#\s+(.+?)\s*$", text, re.M)
    d["name"] = m.group(1).strip() if m else "Player"
    m = re.search(r"\*\*Archetype:\*\*\s*([^·\n]+)", text)
    d["archetype"] = m.group(1).strip() if m else "Role Player"
    m = re.search(r"\*\*Team:\*\*\s*\[\[([A-Z]{3})\]\]", text)
    d["tri"] = m.group(1) if m else None
    # usage
    m = re.search(r"\*\*(?:[^*\n]*?\s)?Usage rate\s*:?\s*\*\*\s*([\d.]+)%?", text)
    d["usage"] = float(m.group(1))/100 if (m and float(m.group(1)) > 1) else (float(m.group(1)) if m else 0)
    # minutes
    m = re.search(r"\*\*(?:[^*\n]*?\s)?Minutes per game\s*:?\s*\*\*\s*([\d.]+)", text)
    d["mpg"] = float(m.group(1)) if m else 0
    # impact rank
    m = re.search(r"\*\*(?:[^*\n]*?\s)?Impact % rank\s*:?\s*\*\*\s*([\d.]+)", text)
    d["impact"] = float(m.group(1)) if m else 0
    return d


def _scan_players():
    """Return list of dicts: pid, name, archetype, tri, usage, mpg, impact, path, slug_full."""
    out = []
    for f in PLAYERS_DIR.glob("*.md"):
        pid = f.stem.split("_", 1)[0]
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        if "<!-- PLAYSTYLE-EXPORT v1 -->" not in text:
            continue
        d = _parse_player(text)
        d["pid"] = pid
        d["path"] = f
        d["slug_full"] = f.stem
        out.append(d)
    return out


def _cv_neighbors_map():
    """pid (str) -> list of (rank, name, neighbor_pid, distance, shared_arch)."""
    try:
        import pandas as pd
    except ImportError:
        return {}
    if not SIM_PARQUET.exists():
        return {}
    df = pd.read_parquet(SIM_PARQUET)
    out = {}
    for pid_a, sub in df.groupby("player_id_a"):
        rows = sub.sort_values("rank").head(8)
        out[str(int(pid_a))] = [
            (int(r["rank"]), str(r["player_b_name"]), str(int(r["player_id_b"])),
             float(r["distance"]), bool(r["shared_archetype"]))
            for _, r in rows.iterrows()
        ]
    return out


def _archetype_cohort_neighbors(p, all_players, k=5):
    """Find k closest players by same archetype + min |usage delta|, then minutes delta."""
    same = [q for q in all_players
            if q["pid"] != p["pid"] and q["archetype"] == p["archetype"]]
    if not same:
        return []
    def score(q):
        return (abs(q["usage"] - p["usage"]) * 100, abs(q["mpg"] - p["mpg"]))
    return sorted(same, key=score)[:k]


def _render_block(p, cv_neighbors, all_by_pid, all_players):
    L = []
    if cv_neighbors:
        L.append("**CV-tracked similarity** (Euclidean distance in 19-D behavior z-space):")
        L.append("")
        L.append("| Rank | Player | Team | Distance | Shared archetype |")
        L.append("|---|---|---|---|---|")
        for rank, name, pid, dist, shared in cv_neighbors[:6]:
            other = all_by_pid.get(pid)
            link = f"[[{other['slug_full']}\\|{other['name']}]]" if other else name
            tri = f"[[{other['tri']}]]" if other and other.get('tri') else "—"
            L.append(f"| {rank} | {link} | {tri} | {dist:.2f} | {'✓' if shared else '—'} |")
        L.append("")
    cohort = _archetype_cohort_neighbors(p, all_players, k=5)
    if cohort:
        L.append(f"**Archetype cohort** ({p['archetype']}, closest by usage & minutes):")
        L.append("")
        L.append("| Player | Team | Usage% | MPG | Impact rank |")
        L.append("|---|---|---|---|---|")
        for q in cohort:
            link = f"[[{q['slug_full']}\\|{q['name']}]]"
            tri = f"[[{q['tri']}]]" if q.get('tri') else "—"
            u = f"{q['usage']*100:.1f}%" if q['usage'] <= 1 else f"{q['usage']:.1f}%"
            L.append(f"| {link} | {tri} | {u} | {q['mpg']:.1f} | {q['impact']:.0f} |")
        L.append("")
    if not L:
        L.append("_No comparable players in current similarity index — thin data._")
        L.append("")
    return "\n".join(L)


def _upsert(text: str, block_md: str) -> str:
    full = f"\n## Comparable Players\n\n{MARK_START}\n\n{block_md}\n{MARK_END}\n"
    if MARK_START in text and MARK_END in text:
        return re.sub(
            r"\n## Comparable Players\s*\n\s*" + re.escape(MARK_START) + r".*?" + re.escape(MARK_END) + r"\n?",
            full, text, flags=re.S,
        )
    # Insert after the PLAYSTYLE-NARRATIVE block if present
    m = re.search(r"<!-- PLAYSTYLE-NARRATIVE END -->\n?", text)
    if m:
        idx = m.end()
        return text[:idx] + full + text[idx:]
    # Else insert before CV Behavioral header
    m = re.search(r"\n## CV Behavioral\b", text)
    if m:
        return text[:m.start()] + full + text[m.start():]
    return text.rstrip() + "\n" + full


def main():
    all_players = _scan_players()
    all_by_pid = {p["pid"]: p for p in all_players}
    cv_map = _cv_neighbors_map()

    written = 0
    cv_used = 0
    cohort_used = 0
    no_data = 0
    for p in all_players:
        cvn = cv_map.get(p["pid"])
        block = _render_block(p, cvn or [], all_by_pid, all_players)
        if cvn:
            cv_used += 1
        elif _archetype_cohort_neighbors(p, all_players):
            cohort_used += 1
        else:
            no_data += 1
        text = p["path"].read_text(encoding="utf-8")
        new = _upsert(text, block)
        if new != text:
            p["path"].write_text(new, encoding="utf-8")
            written += 1
    print(f"players_total: {len(all_players)}")
    print(f"updated: {written}")
    print(f"cv_similarity_used: {cv_used}")
    print(f"cohort_fallback_used: {cohort_used}")
    print(f"no_neighbors_available: {no_data}")


if __name__ == "__main__":
    main()
