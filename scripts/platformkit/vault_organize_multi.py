"""vault_organize_multi.py — Canonical multi-sport Obsidian vault organizer.

Builds a deduped, PERSON-FREE, DENSE tree under vault/_Organized/ (NBA/MLB/Soccer/Tennis).
Each team gets a ``_Identity.md`` style hub; copied Archetype/Scheme/Trend/Reference intel
runs through ``content_person_free_scrub`` so NO specific player/team names survive while
the CONCEPT (stat-signature, thresholds, prevalence %, deltas, mechanism prose) is kept.
``with_named=True`` (CLI ``--with-named``) restores legacy named output.  Non-destructive.
An intelligence MAP, not a betting edge; markets efficient; calibration is not edge.

CLI: ``python -m scripts.platformkit.vault_organize_multi [--json] [--with-named]``
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Player-id filename prefix (e.g. "2544_lebron") — person leak
_PLAYER_ID_STEM_RE = re.compile(r"^\d{3,}_[a-z]", re.IGNORECASE)
# Concept tokens — a two-word Title-Case combo containing ANY is a CONCEPT, not a person.
# Covers archetype/scheme/style terms PLUS stat/section headers we KEEP (e.g. position codes).
_CONCEPT_TOKENS = frozenset((
    "style trends season seasons archetype archetypes scheme schemes trend index "
    "overview summary report health model big guard forward wing center usage two off "
    "ball identity stretch bench contributor dominant versatile creator picks pick three "
    "and rim floor high low primary lead movement scoring combo profile cross sport "
    "digest read validated drivers mechanisms coverage brain moc what wins balanced "
    "contender grinder prevention power run variance pitching sp hand inning total runs "
    "game mode defensive attacking draw prone leaky risk home aggressive passive "
    "specialist interior playmaking rebounding role player statistical fingerprint "
    "signature thresholds threshold classification rule metric median minutes position "
    "baseline reading concedes allows fortifies points rebounds assists steals blocks "
    "rate pace transition halfcourt closeout iso post drop switch zone man help coverage "
    "offense defense pg sg sf pf used teams team links fingerprints stat signatures "
    "differential percentage star stars opponent opponents over under environment "
).split())

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.vault_organize import (  # noqa: E402
    _collect_players, _read_safe, _write)
from scripts.platformkit.vault_person_free_lint import _fmt_bytes, lint_vault  # noqa: E402
from scripts.platformkit.vault_sources import (  # noqa: E402
    SportSpec, source_specs, build_identity, roster_aggregate,
    scrub_person_lines, scrub_player_links)

_UNASSIGNED = "_Unassigned"
_BOILERPLATE = "Intelligence map only — markets efficient; calibration is not edge."
def _build_team_hub(team: str, source_text: Optional[str], recs: List[dict]) -> str:
    """LEGACY ``_Team.md`` (with_named only). Person-FULL — opt-in escape hatch."""
    agg = roster_aggregate(recs) if recs else None
    lines = ["---\ntags: [organized, team, hub]\n---", f"# {team} — Team Hub\n",
             f"> Dense canonical hub. Auto-generated. {_BOILERPLATE}\n"]
    if agg and agg["style_signature"]:
        lines.append(f"**Team style signature:** {agg['style_signature']}\n")
    if source_text:
        lines += ["## Source Intelligence\n", source_text.strip(), ""]
    if agg:
        n = agg["n"]
        lines += [f"\n## Roster ({n} canonical player(s))\n",
                  "| Player | Archetype | Position | Usage |", "|---|---|---|---|"]
        lines += [f"| [[{r['stem']}]] | {r['archetype']} | {r['position']} | {r['usage']} |"
                  for r in sorted(agg["rows"], key=lambda x: x["stem"])]
        lines += ["\n### Archetype Distribution\n", "| Archetype | Count | Share |", "|---|---|---|"]
        lines += [f"| {a} | {c} | {c * 100 // n}% |"
                  for a, c in sorted(agg["arch_hist"].items(), key=lambda kv: (-kv[1], kv[0]))]
        lines.append("\n### Position Distribution\n")
        lines += [f"- {p}: {c}"
                  for p, c in sorted(agg["pos_hist"].items(), key=lambda kv: (-kv[1], kv[0]))]
    return "\n".join(lines) + "\n"
def _is_person_stem(stem: str) -> bool:
    """True if stem looks like a player name (skips upper-case/concept-token combos)."""
    if _PLAYER_ID_STEM_RE.match(stem):
        return True
    clean = stem.lower()
    if clean != stem or any(c.isdigit() for c in clean):
        return False
    parts = re.split(r"[_-]", clean)
    if len(parts) < 2 or not all(re.match(r"^[a-z]{2,}$", p) for p in parts):
        return False
    return not any(p in _CONCEPT_TOKENS for p in parts if p not in ("ii", "iii", "jr", "sr"))
# --- person-free scrub regexes (see content_person_free_scrub docstring) ---
_NAME_SECTION_RE = re.compile(    # header of a person/team ROSTER/leaderboard section -> drop
    r"^#{1,6}\s+.*\b(top\s+\d+|by\s+impact|exploiter|strugglers?|"
    r"players?\s+(who|running|in\b)|teams?\s+(in\b|whose|links|that)|team\s+links|"
    r"frequent\s+opponent|distribution\s+by\s+team|roster|honou?rable\s+mention|"
    r"also\s+notable|leaderboard)", re.IGNORECASE)
_NAME_DUMP_PREFIX_RE = re.compile(    # inline name-dump prose ("Teams whose identity...:")
    r"^\s*\**(teams?\s+(whose|that|running|with)|honou?rable\s+mention|"
    r"also\s+notable|players?\s+(who|running))\b", re.IGNORECASE)
_TEAM_LINK_RE = re.compile(r"\[\[(?:Teams/[^\]|#]+|[A-Z]{2,4})(?:\|[^\]]+)?\]\]")  # team link
_TWOWORD_NAME_RE = re.compile(  # two-word Title-Case person name
    r"\b([A-Z][a-z]+(?:['’.-][A-Za-z]+)?)\s+([A-Z][a-z]+(?:['’.-][A-Za-z]+)?)")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
_HEADER_RE = re.compile(r"^#{1,6}\s")
_LIST_ITEM_RE = re.compile(r"^\s*[-*+]\s")
def _looks_like_person(line: str) -> bool:
    """True if *line* names a specific PERSON ('First Last', neither word a concept)."""
    return any(w1.lower() not in _CONCEPT_TOKENS and w2.lower() not in _CONCEPT_TOKENS
               for w1, w2 in _TWOWORD_NAME_RE.findall(line))
def _count_team_links(text: str) -> int:
    return len(_TEAM_LINK_RE.findall(text))
def content_person_free_scrub(text: str) -> str:
    """Make copied descriptive intel TRULY person-free while KEEPING the concept: (a) drop
    whole roster/leaderboard SECTIONS; (b) collapse inline name-dump prose to a 'Used by N
    teams' count; (c) drop table ROWS + list ITEMS naming a person/team; (d) de-link teams +
    drop person prose; then drop orphan table headers + empty section headers. Concept kept.
    """
    text = scrub_person_lines(text)            # legacy 'X vs Y' matchup-prose drop
    lines, out = text.splitlines(), []  # type: ignore[var-annotated]
    i, n = 0, len(lines)
    while i < n:
        ln = lines[i]
        if _NAME_SECTION_RE.match(ln):          # (a) drop whole name/roster section
            j = i + 1
            while j < n and not _HEADER_RE.match(lines[j]):
                j += 1
            cnt = _count_team_links("\n".join(lines[i + 1:j]))
            if cnt:
                out.append(f"_Used by {cnt} teams._")
            i = j
            continue
        if _NAME_DUMP_PREFIX_RE.match(ln):      # (b) inline name-dump prose -> count
            cnt = _count_team_links(ln)
            out.append(f"_Used by {cnt} teams._" if cnt else "")
            i += 1
            continue
        if (_TABLE_ROW_RE.match(ln) or _LIST_ITEM_RE.match(ln)) and not _TABLE_SEP_RE.match(ln):
            cleaned = _TEAM_LINK_RE.sub("", ln)  # (c) row/item naming a person/team -> drop
            if _looks_like_person(cleaned) or _count_team_links(ln):
                i += 1
                continue
            ln = cleaned
        else:                                    # (d) prose: de-link teams, drop if person
            ln = _TEAM_LINK_RE.sub("", ln)
            if _looks_like_person(ln):
                i += 1
                continue
        out.append(scrub_player_links(ln))
        i += 1
    return _drop_orphan_tables_and_headers(out, text.endswith("\n"))
def _drop_orphan_tables_and_headers(lines: List[str], trailing_nl: bool) -> str:
    """Drop header+separator pairs that lost all rows, then now-empty section headers."""
    keep: List[str] = []
    i, n = 0, len(lines)
    while i < n:                                 # pass 1: orphaned header+separator pair
        if (_TABLE_ROW_RE.match(lines[i]) and i + 1 < n and _TABLE_SEP_RE.match(lines[i + 1])
                and (i + 2 >= n or not _TABLE_ROW_RE.match(lines[i + 2]))):
            i += 2
            continue
        keep.append(lines[i])
        i += 1
    final: List[str] = []
    i, n = 0, len(keep)
    while i < n:                                 # pass 2: header with empty body
        if _HEADER_RE.match(keep[i]):
            j = i + 1
            while j < n and not keep[j].strip():
                j += 1
            if j >= n or _HEADER_RE.match(keep[j]):
                i = j
                continue
        final.append(keep[i])
        i += 1
    return "\n".join(final) + ("\n" if trailing_nl else "")
def _copy_category(src_dirs: List[Path], out_cat: Path) -> int:
    """Copy .md from src_dirs -> out_cat/, scrubbed person-free (player-named files skip)."""
    n = 0
    for src in (d for d in src_dirs if d.is_dir()):
        for path in sorted(src.rglob("*.md")):
            if not path.is_file():
                continue
            if _is_person_stem(path.stem) or "matchup" in path.stem.lower():
                continue   # skip player-named + matchup-themed files (person-free)
            text = _read_safe(path)
            if text is not None:
                _write(out_cat / path.relative_to(src),
                       content_person_free_scrub(text))
                n += 1
    return n
def _organize_sport(spec: SportSpec, sport_out: Path, with_named: bool = False) -> Dict:
    """Build the <SPORT>/ subtree (person-free; *with_named* restores legacy)."""
    cats: Dict[str, int] = {}
    n_players = n_teams = dupes = skipped = 0
    canonical: Dict[str, dict] = {}        # parsed for archetype distribution either way
    by_team: Dict[str, List[dict]] = {}
    if spec.players_dir is not None:
        canonical, dupes, skipped = _collect_players(spec.players_dir)
        for rec in canonical.values():
            by_team.setdefault(rec.get("team") or _UNASSIGNED, []).append(rec)
        if with_named:                     # legacy escape hatch: per-player notes (opt-in)
            n_players = len(canonical)
            for rec in sorted(canonical.values(), key=lambda r: r["stem"]):
                dest = ("Players" if spec.is_solo
                        else f"Teams/{rec.get('team') or _UNASSIGNED}")
                _write(sport_out / dest / f"{rec['stem']}.md", rec["text"])
    if spec.teams_dir is not None and spec.teams_dir.is_dir():
        for team_path in sorted(spec.teams_dir.glob("*.md")):
            if not team_path.is_file():
                continue
            team_name, src = team_path.stem, _read_safe(team_path)
            recs = by_team.get(team_name, [])
            fname, hub = (("_Team.md", _build_team_hub) if with_named
                          else ("_Identity.md", build_identity))
            _write(sport_out / "Teams" / team_name / fname, hub(team_name, src, recs))
            n_teams += 1
    for cat, dirs in (("Archetypes", spec.archetype_dirs), ("Schemes", spec.scheme_dirs),
                      ("Trends", spec.trend_dirs), ("Reference", spec.reference_dirs)):
        cats[cat] = _copy_category(dirs, sport_out / cat)
    return {"n_players": n_players, "n_teams": n_teams, "duplicates_collapsed": dupes,
            "skipped": skipped, "categories": cats}
def _write_sport_index(spec: SportSpec, sport_out: Path, stats: Dict,
                       with_named: bool = False) -> None:
    cats = stats["categories"]
    hub = "_Team" if with_named else "_Identity"
    counts = "  ".join(f"**{c}:** {n}" for c, n in sorted(cats.items()) if n > 0)
    lines = ["---\ntags: [organized, index]\n---", f"# {spec.name} — Intelligence Index\n",
             "> Intelligence map. Markets efficient; calibration is not edge. "
             "Auto-generated by `scripts/platformkit/vault_organize_multi.py`.\n",
             f"**Teams:** {stats['n_teams']}  |  **Players:** {stats['n_players']}  |  "
             + counts, ""]
    teams_dir = sport_out / "Teams"
    if stats["n_teams"] > 0 and teams_dir.is_dir():
        lines.append("## Teams\n")
        lines += [f"- [[Teams/{t}/{hub}|{t}]]"
                  for t in sorted(d.name for d in teams_dir.iterdir() if d.is_dir())]
    for cat, n in sorted(cats.items()):
        cat_dir = sport_out / cat
        if n > 0 and cat_dir.is_dir():
            lines.append(f"\n## {cat} ({n})\n")
            lines += [f"- [[{cat}/{f.relative_to(cat_dir).as_posix()}|{f.stem}]]"
                      for f in sorted(cat_dir.rglob("*.md"))]
    _write(sport_out / "_Index.md", "\n".join(lines) + "\n")
def _write_brain(out_dir: Path, sport_stats: Dict[str, Dict]) -> None:
    hdr = ("---\ntags: [organized, brain, moc]\n---\n"
           "# Organized Vault — Brain (Multi-Sport)\n\n"
           "> **An intelligence MAP, not a betting edge; markets efficient; "
           "calibration is not edge.**\n> Non-destructive copy — live vault/ untouched.\n\n"
           "## Sports\n")
    rows = [f"- **[[{sp}/_Index|{sp}]]** — {st['n_teams']} teams · {st['n_players']} players"
            f" · {', '.join(f'{c}={n}' for c, n in sorted(st['categories'].items()) if n > 0)}"
            for sp, st in sorted(sport_stats.items())]
    _write(out_dir / "_Index" / "_Brain.md", hdr + "\n".join(rows) + "\n")
def organize_all(vault_dir: Optional[Path] = None, out_dir: Optional[Path] = None,
                 with_named: bool = False) -> Dict:
    """Build the full PERSON-FREE multi-sport tree (*with_named* restores legacy)."""
    vault_dir = Path(vault_dir) if vault_dir is not None else (_REPO_ROOT / "vault")
    out_dir = Path(out_dir) if out_dir is not None else (vault_dir / "_Organized")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    before = lint_vault(vault_dir)
    sport_stats: Dict[str, Dict] = {}
    for spec in source_specs(vault_dir):
        sport_out = out_dir / spec.name
        stats = _organize_sport(spec, sport_out, with_named=with_named)
        _write_sport_index(spec, sport_out, stats, with_named=with_named)
        sport_stats[spec.name] = stats
    _write_brain(out_dir, sport_stats)
    after = lint_vault(out_dir)

    def _snap(r: Dict) -> Dict:  # person_free below = organizer's matchup invariant; the
        return {"n_files": r["n_files"], "total_bytes": r["total_bytes"],  # STRICT all-leak
                "person_leaks": sum(r["leak_counts"].values()),  # gate is in compute_gates.
                "matchup_vs_leaks": r["leak_counts"].get("matchup_vs", 0)}
    return {"vault_dir": str(vault_dir), "out_dir": str(out_dir),
            "person_free": (not with_named) and after["leak_counts"].get("matchup_vs", 0) == 0,
            "with_named": with_named, "before": _snap(before), "after": _snap(after),
            "per_sport": sport_stats}
def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    arg = next((a for a in argv if not a.startswith("-")), None)
    rep = organize_all(vault_dir=Path(arg) if arg else None,
                       with_named="--with-named" in argv)
    if "--json" in argv:
        print(json.dumps(rep, indent=2))
        return 0
    mode = "NAMED (legacy)" if rep["with_named"] else "PERSON-FREE"
    print(f"source : {rep['vault_dir']}\nout    : {rep['out_dir']}\n"
          f"mode   : {mode}  person_free={rep['person_free']}")
    for tag, d in (("BEFORE", rep["before"]), ("AFTER", rep["after"])):
        print(f"{tag:7}{d['n_files']:>7} files  {_fmt_bytes(d['total_bytes']):>9}  "
              f"leaks={d['person_leaks']:>5}  matchup_vs={d['matchup_vs_leaks']:>5}")
    for sp, st in sorted(rep["per_sport"].items()):
        print(f"  {sp:8} teams={st['n_teams']:>3} players={st['n_players']:>4}  " + " ".join(
            f"{c[:3]}={n}" for c, n in sorted(st["categories"].items())))
    return 0

if __name__ == "__main__":
    sys.exit(main())
