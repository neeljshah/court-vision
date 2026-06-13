"""scripts.platform.atlas.build_all — Multi-sport atlas build driver.

Usage: python scripts/platform/atlas/build_all.py [--sport SPORT] [--out DIR] [--full]
  --full           runs per-sport extras (StyleMatchups, StyleTrends, Scouting, …) and
                   cross-sport META generators (GraphReport, SignalsHub, …).
  --with-catalogs  runs signal_catalog + signal_catalog_joint for tennis/soccer/mlb
                   (NBA has no catalog).  SLOW — each sport hits the real gate.
Discipline: Py3.9, from __future__ import annotations, type hints, ≤300 LOC.
"""
from __future__ import annotations

import argparse
import importlib
import inspect
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# (sport_id, display_name, adapter_module, corpus_hint)
_SPORT_MANIFEST: List[Tuple[str, str, str, str]] = [
    ("tennis_atp",     "Tennis",         "domains.tennis.atlas",               "data/domains/tennis"),
    ("soccer_fd",      "Soccer",         "domains.soccer.atlas",               "data/domains/soccer"),
    ("mlb_sbro",       "MLB",            "domains.mlb.atlas",                  "data/domains/mlb"),
    ("basketball_nba", "Basketball_NBA", "domains.basketball_nba.memory_atlas", "data"),
]
_ALIASES: Dict[str, str] = {
    "tennis": "tennis_atp", "tennis_atp": "tennis_atp",
    "soccer": "soccer_fd",  "soccer_fd":  "soccer_fd",
    "mlb":    "mlb_sbro",   "mlb_sbro":   "mlb_sbro",
    "nba": "basketball_nba", "basketball": "basketball_nba",
    "basketball_nba": "basketball_nba", "all": "all",
}

# Per-sport extra generators (--full only): (domain, module_suffix, fn_name, subdir, corpus_kwarg)
_EXTRA_GENS: List[Tuple[str, str, str, str, str]] = [
    ("tennis",         "atlas_style_matchups",     "build_style_matchups",    "StyleMatchups",     "corpus_dir"),
    ("tennis",         "atlas_style_trends",        "build_style_trends",      "StyleTrends",       "corpus_dir"),
    ("tennis",         "atlas_scouting",            "build_scouting",          "Scouting",          "vault_tennis_dir"),
    ("soccer",         "atlas_style_matchups",     "build_style_matchups",    "StyleMatchups",     "corpus_dir"),
    ("soccer",         "atlas_style_trends",        "build_style_trends",      "StyleTrends",       "corpus_dir"),
    ("soccer",         "atlas_scheme_transitions",  "build_scheme_transitions","SchemeTransitions",  "corpus_dir"),
    ("soccer",         "atlas_scouting",            "build_scouting",          "Scouting",          "corpus_dir"),
    ("mlb",            "atlas_style_matchups",     "build_style_matchups",    "StyleMatchups",     "corpus_dir"),
    ("mlb",            "atlas_style_trends",        "build_style_trends",      "StyleTrends",       "corpus_dir"),
    ("mlb",            "atlas_home_environment",    "build_home_environment",  "HomeEnvironment",   "corpus_dir"),
    ("mlb",            "atlas_scouting",            "build_scouting",          "Scouting",          "corpus_dir"),
    ("basketball_nba", "memory_atlas_trends",       "build_trends",            "Trends",            "data_dir"),
    ("basketball_nba", "atlas_scouting",            "build_scouting",          "Scouting",          "corpus_dir"),
]
# Cross-sport META generators (--full, run after all sports): (module_suffix, fn_name)
_META_GENS: List[Tuple[str, str]] = [
    ("graph_report", "build_graph_report"), ("signals_hub", "build_signals_hub"),
    ("archetype_taxonomy", "build_taxonomy"), ("intelligence_overview", "build_intelligence_overview"),
    ("graph_health", "build_graph_health"),
]
# --with-catalogs: (loader_mod, cat_mod, joint_mod, joint_fn, seasons, display, corpus_hint)
# joint_fn: tennis/soccer="run_joint_catalog"; mlb joint module uses "run_catalog".
_CAT: List[Tuple[str, str, str, str, List[int], str, str]] = [  # noqa: E501
    ("scripts.platform.proof_tennis.run_proof", "domains.tennis.signal_catalog", "domains.tennis.signal_catalog_joint", "run_joint_catalog", list(range(2015, 2027)), "Tennis", "data/domains/tennis"),  # noqa: E501
    ("scripts.platform.proof_soccer.run_proof", "domains.soccer.signal_catalog", "domains.soccer.signal_catalog_joint", "run_joint_catalog", list(range(2015, 2026)), "Soccer", "data/domains/soccer"),  # noqa: E501
    ("scripts.platform.proof_mlb.run_proof", "domains.mlb.signal_catalog", "domains.mlb.signal_catalog_joint", "run_catalog", list(range(2010, 2022)), "MLB", "data/domains/mlb"),  # noqa: E501
]


def write_hub(out_dir: Path, built_sports: List[Tuple[str, str, int]]) -> Path:
    """Write (or overwrite) <out_dir>/_Hub.md.  Returns the hub path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    built_ids = {sid for sid, _, _ in built_sports}
    rows: List[str] = []
    for sport_id, display_name, _, corpus_hint in _SPORT_MANIFEST:
        if sport_id in built_ids:
            count = next(n for s, _, n in built_sports if s == sport_id)
            link = f"[[{display_name}/_Index]] · {count} notes"
        else:
            link = f"[[{display_name}/_Index]] *(pending)* · module absent — skipped"
        rows.append(f"| {display_name} | `{Path(corpus_hint).name}` | {link} |")
    today, table = date.today().isoformat(), "\n".join(rows)
    nba = ("- [[Home]] — platform home note\n- [[Intelligence/_Scout_Index]] — NBA scout index\n"
           "- [[MOC-CV]] · [[MOC-Models]] · [[MOC-Betting]] · [[MOC-Strategy]]")
    hub_path = out_dir / "_Hub.md"
    hub_path.write_text(
        f"---\ntags: [sport, memory-graph, hub, index]\nupdated: {today}\n---\n"
        "# Multi-Sport Intelligence Hub\n\n"
        "> Registry-driven knowledge graph spanning every sport domain.\n"
        "> Auto-generated by `scripts/platform/atlas/build_all.py` — edit the driver, not this file.\n\n"
        "Each sport has its own folder under `vault/Sports/<Sport>/` with an `_Index` entry point.\n\n---\n\n"
        f"## Sport Index\n\n| Sport | Corpus | Index |\n|-------|--------|-------|\n{table}\n\n---\n\n"
        "## NBA Intelligence Vault (existing)\n\nNBA artifacts live in `vault/` not `vault/Sports/`.\n\n"
        f"{nba}\n\n---\n\n#sport #memory-graph #hub #index\n\n"
        f"*Generated {today} by `scripts/platform/atlas/build_all.py`*\n", encoding="utf-8")
    return hub_path


def _load_build_fn(adapter_module: str):  # type: ignore[return]
    try: mod = importlib.import_module(adapter_module)
    except ImportError as exc: log.debug("ImportError for %s: %s", adapter_module, exc); return None
    fn = getattr(mod, "build_atlas", None)
    if fn is None: log.warning("%s has no build_atlas() — skipping.", adapter_module)
    return fn


def _derive_domain(m: str) -> str:
    p = m.split(".")
    return p[1] if len(p) >= 2 and p[0] == "domains" else p[0]


def _call_optional(fn, out_dir: Path, corpus_dir: Path, corpus_kwarg: str) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    sig = inspect.signature(fn)
    notes: List[Path] = fn(out_dir, **{corpus_kwarg: corpus_dir}) if corpus_kwarg in sig.parameters else fn(out_dir)
    return len(notes) if notes is not None else 0


def _try_build_optional(
    module_path: str, fn_name: str, subdir: str,
    sport_out: Path, corpus_dir: Path, corpus_kwarg: str = "corpus_dir",
) -> int:
    try: mod = importlib.import_module(module_path)
    except ImportError: log.debug("No %s — skipping.", module_path); return 0
    fn = getattr(mod, fn_name, None)
    if fn is None: return 0
    try:
        count = _call_optional(fn, sport_out / subdir, corpus_dir, corpus_kwarg)
        log.info("  %s (%s): %d note(s)", subdir, module_path.rsplit(".", 1)[-1], count)
        return count
    except Exception as exc:  # noqa: BLE001
        log.warning("  %s.%s raised %s: %s — skipping.", module_path, fn_name, type(exc).__name__, exc); return 0


def _try_build_h2h(d: str, so: Path, cd: Path) -> int:
    return _try_build_optional(f"domains.{d}.atlas_h2h", "build_h2h", "Matchups", so, cd)


def _try_build_playstyles(d: str, so: Path, cd: Path) -> int:
    if d == "basketball_nba":
        return _try_build_optional(f"domains.{d}.memory_atlas_archetypes", "build_archetypes", "Archetypes", so, cd, "data_dir")
    return _try_build_optional(f"domains.{d}.atlas_playstyles", "build_playstyles", "Playstyles", so, cd)


def _try_build_tournaments(d: str, so: Path, cd: Path) -> int:
    return _try_build_optional(f"domains.{d}.atlas_tournaments", "build_tournaments", "Tournaments", so, cd) if d == "tennis" else 0


def _try_build_seasons(d: str, so: Path, cd: Path) -> int:
    if d == "basketball_nba":
        return _try_build_optional(f"domains.{d}.memory_atlas_seasons", "build_seasons", "Seasons", so, cd, "data_dir")
    return _try_build_optional(f"domains.{d}.atlas_seasons", "build_seasons", "Seasons", so, cd) if d in {"soccer", "mlb"} else 0


def _build_extras(domain: str, sport_out: Path, corpus_dir: Path) -> int:
    total = 0
    for (gd, ms, fn, sub, kw) in _EXTRA_GENS:
        if gd != domain: continue
        ad = sport_out if kw not in ("corpus_dir", "data_dir") else corpus_dir
        total += _try_build_optional(f"domains.{domain}.{ms}", fn, sub, sport_out, ad, kw)
    return total


def _build_meta(out_dir: Path) -> List[str]:
    written: List[str] = []
    for (ms, fn_name) in _META_GENS:
        try: mod = importlib.import_module(f"scripts.platform.atlas.{ms}")
        except ImportError: continue
        fn = getattr(mod, fn_name, None)
        if fn is None: continue
        try:
            result: Path = fn(out_dir) if inspect.signature(fn).parameters else fn()
            log.info("  META %s: wrote %s", fn_name, result.name if result else "?")
            if result: written.append(result.name)
        except Exception as exc:  # noqa: BLE001
            log.warning("  META %s raised %s: %s — skipping.", fn_name, type(exc).__name__, exc)
    return written


def _run_catalogs(out_dir: Path) -> List[str]:
    """Run signal_catalog + signal_catalog_joint per sport (--with-catalogs).  SLOW (real gate).
    Skips gracefully if corpus absent or import fails.  Returns written file names.
    """
    written: List[str] = []
    for (loader_mod, cat_mod, joint_mod, joint_fn, seasons, display, corpus_hint) in _CAT:
        corpus_dir = _REPO_ROOT / corpus_hint
        log.info("  Catalog %s (seasons %s–%s) …", display, seasons[0], seasons[-1])
        try:
            adapter: Any = importlib.import_module(loader_mod)._load_adapter(corpus_dir)  # type: ignore[attr-defined]
        except (ImportError, AttributeError) as exc:
            log.warning("  %s: loader unavailable (%s) — skipping.", display, exc); continue
        if adapter is None:
            log.warning("  %s: corpus absent at %s — skipping.", display, corpus_dir); continue
        sig_out = out_dir / display / "Signals"
        sig_out.mkdir(parents=True, exist_ok=True)
        for mod_path, fn_name, fname in [(cat_mod, "run_catalog", "_Catalog.md"),
                                         (joint_mod, joint_fn, "_Catalog_Joint.md")]:
            try:
                fn = getattr(importlib.import_module(mod_path), fn_name, None)
                if fn is None: continue
                fn(adapter, seasons, out_path=sig_out / fname)
                written.append(f"{display}/Signals/{fname}")
                log.info("  %s: %s written.", display, fname)
            except ImportError:
                log.debug("  %s: %s not importable — skipping.", display, mod_path)
            except Exception as exc:  # noqa: BLE001
                log.warning("  %s %s raised %s: %s — skipping.", display, fn_name, type(exc).__name__, exc)
    return written


def build_sport(
    sport_id: str, display_name: str, adapter_module: str,
    corpus_hint: str, out_dir: Path, full: bool = False,
) -> Optional[int]:
    """Build atlas + H2H + Playstyles + Tournaments + Seasons (+ extras if full) for one sport."""
    log.info("Building atlas: %s (%s) …", display_name, sport_id)
    build_fn = _load_build_fn(adapter_module)
    if build_fn is None:
        log.warning("  Skipping %s — module %s not importable.", display_name, adapter_module); return None
    sport_out = out_dir / display_name
    sport_out.mkdir(parents=True, exist_ok=True)
    corpus_dir = _REPO_ROOT / corpus_hint
    try:
        sig = inspect.signature(build_fn)
        notes: List[Path] = build_fn(sport_out, corpus_dir=corpus_dir) if "corpus_dir" in sig.parameters else build_fn(sport_out)
    except Exception as exc:  # noqa: BLE001
        log.warning("  build_atlas for %s raised %s: %s — skipping.", display_name, type(exc).__name__, exc); return None
    count = len(notes) if notes is not None else 0
    log.info("  %s: %d atlas note(s) written to %s", display_name, count, sport_out)
    domain = _derive_domain(adapter_module)
    total = (count + _try_build_h2h(domain, sport_out, corpus_dir)
             + _try_build_playstyles(domain, sport_out, corpus_dir)
             + _try_build_tournaments(domain, sport_out, corpus_dir)
             + _try_build_seasons(domain, sport_out, corpus_dir))
    if full: total += _build_extras(domain, sport_out, corpus_dir)
    return total


def main(argv: Optional[List[str]] = None) -> int:
    """Build atlases and write hub.  Returns 0 on success."""
    parser = argparse.ArgumentParser(prog="build_all.py", description="Build per-sport Obsidian atlases.")
    parser.add_argument("--sport", default="all", metavar="SPORT", help="tennis|soccer|mlb|nba|all")
    parser.add_argument("--out", default="vault/Sports", metavar="DIR")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--full", action="store_true", help="Also run per-sport extras + META generators.")
    parser.add_argument("--with-catalogs", action="store_true",
                        help="Run signal_catalog + signal_catalog_joint per sport (SLOW — hits real gate).")
    args = parser.parse_args(argv)
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    resolved = _ALIASES.get(args.sport.lower())
    if resolved is None:
        log.error("Unknown --sport %r.  Valid: %s", args.sport, sorted(_ALIASES)); return 1
    out_dir = _REPO_ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)
    targets = _SPORT_MANIFEST if resolved == "all" else [e for e in _SPORT_MANIFEST if e[0] == resolved]
    if not targets:
        log.error("No manifest entry for %r.", resolved); return 1
    built: List[Tuple[str, str, int]] = []
    for sport_id, display_name, adapter_module, corpus_hint in targets:
        count = build_sport(sport_id, display_name, adapter_module, corpus_hint, out_dir, full=args.full)
        if count is not None:
            built.append((sport_id, display_name, count))
    hub_path = write_hub(out_dir, built)
    meta_written: List[str] = []
    if args.full:
        log.info("Running cross-sport META generators …"); meta_written = _build_meta(out_dir)
    catalog_written: List[str] = []
    if args.with_catalogs:
        log.info("Running signal catalogs (SLOW — real gate) …"); catalog_written = _run_catalogs(out_dir)

    def _disp(p: Path) -> str:
        try: return str(p.relative_to(_REPO_ROOT))
        except ValueError: return str(p)

    sep = "=" * 60
    print(f"\n{sep}\nMulti-sport atlas build complete")
    print(f"  Hub note : {_disp(hub_path)}\n  Out dir  : {_disp(out_dir)}")
    if args.full: print(f"  --full   : extras + {len(meta_written)} meta note(s) written")
    if args.with_catalogs: print(f"  --with-catalogs: {len(catalog_written)} catalog file(s) written")
    print()
    for _, display_name, note_count in built:
        print(f"  {display_name:<20} {note_count:>4} note(s)")
    for sid, dn, _, _ in targets:
        if sid not in {s for s, _, _ in built}:
            print(f"  {dn:<20}  --- skipped (module absent)")
    if meta_written:
        print("\n  META notes:\n" + "\n".join(f"    {n}" for n in meta_written))
    if catalog_written:
        print("\n  Catalog files:\n" + "\n".join(f"    {n}" for n in catalog_written))
    print(sep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
