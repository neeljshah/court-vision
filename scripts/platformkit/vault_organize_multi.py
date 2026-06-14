"""vault_organize_multi.py — Canonical multi-sport Obsidian vault organizer.

Builds a deduped, PERSON-FREE, DENSE organized tree under vault/_Organized/ covering
NBA, MLB, Soccer, and Tennis.  Default = person-free: NO per-player notes; each team
gets a ``_Identity.md`` style hub (style signature + scheme/driver tags + archetype
distribution) with NO roster, NO named players, NO matchup lines.  ``with_named=True``
(CLI ``--with-named``) restores legacy named output (per-player notes + ``_Team.md``).
Non-destructive: writes only under out_dir.  An intelligence MAP, not a betting edge;
markets efficient; calibration is not edge.

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
# Concept tokens — these combos are NOT person names (archetype/scheme/style terms)
_CONCEPT_TOKENS = frozenset((
    "style trends season seasons archetype archetypes scheme schemes trend "
    "index overview summary report health model big guard forward wing center "
    "usage two off ball identity stretch bench contributor dominant versatile "
    "creator picks pick three and rim floor high low primary lead movement "
    "scoring combo profile cross sport digest read validated drivers "
    "mechanisms coverage brain moc what wins balanced contender grinder "
    "prevention power run variance pitching sp hand inning total runs game "
    "mode defensive attacking draw prone leaky risk home aggressive passive "
    "specialist interior playmaking rebounding role player "
).split())

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.vault_organize import (   # noqa: E402
    _collect_players,
    _read_safe,
    _write,
)
from scripts.platformkit.vault_person_free_lint import (  # noqa: E402
    _fmt_bytes,
    lint_vault,
)
from scripts.platformkit.vault_sources import (    # noqa: E402
    SportSpec,
    source_specs,
    build_identity,
    roster_aggregate,
    scrub_person_lines,
)

_UNASSIGNED = "_Unassigned"
_BOILERPLATE = ("Intelligence map only — markets efficient; calibration is not edge.")


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
        for row in sorted(agg["rows"], key=lambda x: x["stem"]):
            lines.append(f"| [[{row['stem']}]] | {row['archetype']} | "
                         f"{row['position']} | {row['usage']} |")
        lines += ["\n### Archetype Distribution\n", "| Archetype | Count | Share |",
                  "|---|---|---|"]
        for arch, cnt in sorted(agg["arch_hist"].items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"| {arch} | {cnt} | {cnt * 100 // n}% |")
        lines.append("\n### Position Distribution\n")
        for pos, cnt in sorted(agg["pos_hist"].items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"- {pos}: {cnt}")
    return "\n".join(lines) + "\n"

def _is_person_stem(stem: str) -> bool:
    """True if stem looks like a player name (person-free violation).
    Skips mixed/upper-case (archetype/hub nodes) and concept-token combos.
    """
    if _PLAYER_ID_STEM_RE.match(stem):
        return True
    clean = stem.lower()
    if clean != stem or any(c.isdigit() for c in clean):
        return False
    parts = re.split(r"[_-]", clean)
    if len(parts) < 2 or not all(re.match(r"^[a-z]{2,}$", p) for p in parts):
        return False
    non_suffix = [p for p in parts if p not in ("ii", "iii", "jr", "sr")]
    return not any(p in _CONCEPT_TOKENS for p in non_suffix)


def _copy_category(src_dirs: List[Path], out_cat: Path) -> int:
    """Copy .md files from src_dirs into out_cat/, scrubbing person matchup lines.
    Person-named files (first_last or id_first) are skipped to keep graph clean."""
    n = 0
    for src in (d for d in src_dirs if d.is_dir()):
        for path in sorted(src.rglob("*.md")):
            if not path.is_file():
                continue
            if _is_person_stem(path.stem):
                continue   # skip player-named files — person-free invariant
            text = _read_safe(path)
            if text is not None:
                _write(out_cat / path.relative_to(src), scrub_person_lines(text))
                n += 1
    return n


def _organize_sport(spec: SportSpec, sport_out: Path, with_named: bool = False) -> Dict:
    """Build the <SPORT>/ subtree.  Person-free by default; *with_named* restores the
    legacy per-player notes + roster ``_Team.md`` hub.  Returns per-sport stats dict.
    """
    cats: Dict[str, int] = {}
    n_players = n_teams = dupes = skipped = 0
    # ---- player records (parsed for archetype distribution either way) ----
    canonical: Dict[str, dict] = {}
    by_team: Dict[str, List[dict]] = {}

    if spec.players_dir is not None:
        canonical, dupes, skipped = _collect_players(spec.players_dir)
        for rec in canonical.values():
            team = rec.get("team") or _UNASSIGNED
            by_team.setdefault(team, []).append(rec)
        if with_named:
            # legacy escape hatch: emit per-player notes (reversible / opt-in)
            n_players = len(canonical)
            for rec in sorted(canonical.values(), key=lambda r: r["stem"]):
                if spec.is_solo:
                    _write(sport_out / "Players" / f"{rec['stem']}.md", rec["text"])
                else:
                    team = rec.get("team") or _UNASSIGNED
                    _write(sport_out / "Teams" / team / f"{rec['stem']}.md", rec["text"])

    # ---- team hubs --------------------------------------------------------
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

    # ---- intel categories -------------------------------------------------
    cats["Archetypes"] = _copy_category(spec.archetype_dirs, sport_out / "Archetypes")
    cats["Schemes"] = _copy_category(spec.scheme_dirs, sport_out / "Schemes")
    cats["Trends"] = _copy_category(spec.trend_dirs, sport_out / "Trends")
    cats["Reference"] = _copy_category(spec.reference_dirs, sport_out / "Reference")

    return {
        "n_players": n_players,
        "n_teams": n_teams,
        "duplicates_collapsed": dupes,
        "skipped": skipped,
        "categories": cats,
    }


# --------------------------------------------------------------------------- #
# per-sport _Index.md
# --------------------------------------------------------------------------- #

def _write_sport_index(spec: SportSpec, sport_out: Path, stats: Dict,
                       with_named: bool = False) -> None:
    cats = stats["categories"]
    hub = "_Team" if with_named else "_Identity"
    lines = [
        "---\ntags: [organized, index]\n---",
        f"# {spec.name} — Intelligence Index\n",
        "> Intelligence map. Markets efficient; calibration is not edge. "
        "Auto-generated by `scripts/platformkit/vault_organize_multi.py`.\n",
        f"**Teams:** {stats['n_teams']}  |  **Players:** {stats['n_players']}  |  "
        + "  ".join(f"**{c}:** {n}" for c, n in sorted(cats.items()) if n > 0),
        "",
    ]
    if stats["n_teams"] > 0:
        lines.append("## Teams\n")
        teams_dir = sport_out / "Teams"
        if teams_dir.is_dir():
            for t in sorted(d.name for d in teams_dir.iterdir() if d.is_dir()):
                lines.append(f"- [[Teams/{t}/{hub}|{t}]]")
    for cat, n in sorted(cats.items()):
        if n > 0:
            lines.append(f"\n## {cat} ({n})\n")
            cat_dir = sport_out / cat
            if cat_dir.is_dir():
                for f in sorted(cat_dir.rglob("*.md")):
                    rel = f.relative_to(cat_dir).as_posix()
                    lines.append(f"- [[{cat}/{rel}|{f.stem}]]")
    _write(sport_out / "_Index.md", "\n".join(lines) + "\n")


def _write_brain(out_dir: Path, sport_stats: Dict[str, Dict]) -> None:
    hdr = ("---\ntags: [organized, brain, moc]\n---\n"
           "# Organized Vault — Brain (Multi-Sport)\n\n"
           "> **An intelligence MAP, not a betting edge; markets efficient; "
           "calibration is not edge.**\n> Non-destructive copy — live vault/ untouched.\n\n"
           "## Sports\n")
    rows = [
        f"- **[[{sp}/_Index|{sp}]]** — {st['n_teams']} teams · {st['n_players']} players"
        f" · {', '.join(f'{c}={n}' for c, n in sorted(st['categories'].items()) if n > 0)}"
        for sp, st in sorted(sport_stats.items())
    ]
    _write(out_dir / "_Index" / "_Brain.md", hdr + "\n".join(rows) + "\n")


def organize_all(vault_dir: Optional[Path] = None, out_dir: Optional[Path] = None,
                 with_named: bool = False) -> Dict:
    """Build the full multi-sport organized tree. PERSON-FREE by default.
    *with_named* restores legacy named output. Returns a structured report dict.
    """
    vault_dir = Path(vault_dir) if vault_dir is not None else (_REPO_ROOT / "vault")
    out_dir = Path(out_dir) if out_dir is not None else (vault_dir / "_Organized")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    before = lint_vault(vault_dir)
    specs = source_specs(vault_dir)
    sport_stats: Dict[str, Dict] = {}
    for spec in specs:
        sport_out = out_dir / spec.name
        stats = _organize_sport(spec, sport_out, with_named=with_named)
        _write_sport_index(spec, sport_out, stats, with_named=with_named)
        sport_stats[spec.name] = stats
    _write_brain(out_dir, sport_stats)
    after = lint_vault(out_dir)
    aml = after["leak_counts"].get("matchup_vs", 0)
    return {
        "vault_dir": str(vault_dir), "out_dir": str(out_dir),
        "person_free": (not with_named) and aml == 0, "with_named": with_named,
        "before": {"n_files": before["n_files"], "total_bytes": before["total_bytes"],
                   "person_leaks": sum(before["leak_counts"].values()),
                   "matchup_vs_leaks": before["leak_counts"].get("matchup_vs", 0)},
        "after": {"n_files": after["n_files"], "total_bytes": after["total_bytes"],
                  "person_leaks": sum(after["leak_counts"].values()),
                  "matchup_vs_leaks": aml},
        "per_sport": sport_stats,
    }


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    vault_dir_arg = next((a for a in argv if not a.startswith("-")), None)
    vault_dir = Path(vault_dir_arg) if vault_dir_arg else None
    rep = organize_all(vault_dir=vault_dir, with_named="--with-named" in argv)
    if "--json" in argv:
        print(json.dumps(rep, indent=2))
        return 0
    b, a = rep["before"], rep["after"]
    print(f"source : {rep['vault_dir']}\nout    : {rep['out_dir']}")
    print(f"mode   : {'NAMED (legacy)' if rep['with_named'] else 'PERSON-FREE'}  "
          f"person_free={rep['person_free']}")
    for tag, d in (("BEFORE", b), ("AFTER", a)):
        print(f"{tag:7}{d['n_files']:>7} files  {_fmt_bytes(d['total_bytes']):>9}  "
              f"leaks={d['person_leaks']:>5}  matchup_vs={d['matchup_vs_leaks']:>5}")
    for sport, st in sorted(rep["per_sport"].items()):
        cat_str = " ".join(f"{c[:3]}={n}" for c, n in sorted(st["categories"].items()))
        print(f"  {sport:8} teams={st['n_teams']:>3} players={st['n_players']:>4} {cat_str}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
