"""factory_source_manifest -- the DATA files the pod factory reads, and whether the pod has them.

S78: `pod_bootstrap.sh` ships the tracked TREE (`git archive`), but every source the real screen
predictor reads lives under `data/`, which is gitignored -- so a restarted pod boots a runner that
crashes at bind (nba games.parquet), then on tennis odds, then on a pre-S68 sidecar, then throws
363 FileNotFound screen_failed per pass. Each one was found only by running. 127 parquet + the 4
gate corpora + sidecars were shipped by hand on 2026-09-03.

This module DERIVES the required set from the same registries the factory reads, so it cannot
drift from them:

  * `combo.corpus_cache`      -- the 4 gate corpora + `_close` variants, their sidecars, and every
                                source each sidecar RECORDED (resolved through `_resolve_source`).
  * `foundry.asof_supply`     -- REGISTRY[*].source (comma lists and globs expanded) + season_table.
  * `foundry.catalogue`       -- NAMED + GLOBS, the frozen family parquet catalogue.
  * `eval_gate.family_bars`   -- load_families().families[*].sources (the FWER spec's own list).
  * `eval_gate.close_join*`   -- the soccer/tennis odds+matches+wta_matches spines from `_SPECS`,
                                and the module path constants of close_join_mlb / close_join_nba_mlb.
  * in-game tier stores       -- ingame_screen_soccer.STORE, ingame_supply_mlb.JOINED/SERIES,
                                ingame_screen_nba.S86_CSV, read as module constants.

HARDCODED, and only this: `screen_predictor._teams` builds its games paths inline inside the
function, so its three parquet (basketball_nba/games, mlb/games, mlb/games_current) are listed as
`_TEAMS_GAMES` below. Everything else is an import.

Digest is SHA-256 over the whole file (~76 MB total local, about a second), and the pod side runs
ONE `sha256sum` batch over ssh -- read-only, one round trip, no write on the pod.

    python scripts/platformkit/ops/factory_source_manifest.py            # local table
    python scripts/platformkit/ops/factory_source_manifest.py --check-pod
    python scripts/platformkit/ops/factory_source_manifest.py --check-pod --ship

Stdlib + the repo's own registries. ASCII only. Reads only; never writes data/registry/, never
boots, never kills, never flips a flag on. A SCREEN is a NON-FINDING; calibration language only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:  # run as a file path, not as -m
    sys.path.insert(0, str(_REPO_ROOT))

POD_REPO = "/workspace/nba-ai-system"
SSH = ("ssh", "-o", "BatchMode=yes", "-F", str(Path.home() / ".ssh" / "config.pod"), "pod")
# subprocess needs the expanded path; a PRINTED command needs the portable one.
SSH_DISPLAY = "ssh -o BatchMode=yes -F ~/.ssh/config.pod pod"

# The ONLY hardcoded entry: screen_predictor._teams() builds these inline (see module docstring).
_TEAMS_GAMES = ("data/domains/basketball_nba/games.parquet",
                "data/domains/mlb/games.parquet",
                "data/domains/mlb/games_current.parquet")


def _rel(path) -> str:
    p = Path(path)
    try:
        root = _REPO_ROOT.absolute()
        return (p if p.is_absolute() else root / p).absolute().relative_to(root).as_posix()
    except ValueError:
        return p.as_posix()


def _add(out: Dict[str, List[str]], spec: str, origin: str) -> None:
    """Record one repo-relative path or glob under *origin*, expanding globs that match."""
    spec = str(spec).strip()
    if not spec:
        return
    if any(ch in spec for ch in "*?["):
        pattern = Path(spec).relative_to(_REPO_ROOT) if Path(spec).is_absolute() else Path(spec)
        hits = sorted(_REPO_ROOT.glob(pattern.as_posix()))
        for hit in hits:
            out.setdefault(_rel(hit), []).append(origin)
        if hits:
            return                      # a matching glob contributes its members, not the pattern
    out.setdefault(_rel(spec), []).append(origin)


def _corpora(out: Dict[str, List[str]]) -> None:
    from scripts.platformkit.combo import corpus_cache
    from scripts.platformkit.eval_gate import close_join_nba_mlb as cjnm
    pairs = [(s, corpus_cache._corpus_path(s)) for s in sorted(corpus_cache.SPORTS)]
    pairs += [(s + "_close", cjnm.close_corpus_path(s)) for s in sorted(cjnm.CLOSE_BUILDERS)]
    for sport, corpus in pairs:
        sidecar = corpus.with_name(corpus.name.replace(".parquet", ".sources.json"))
        _add(out, _rel(corpus), "corpus:%s" % sport)
        _add(out, _rel(sidecar), "corpus:%s" % sport)
        if not sidecar.exists():
            continue
        manifest = json.loads(sidecar.read_text(encoding="utf-8"))
        for src in manifest.get("sources", {}):
            _add(out, _rel(corpus_cache._resolve_source(src)), "sidecar:%s" % sport)


def _registries(out: Dict[str, List[str]]) -> None:
    from scripts.platformkit.eval_gate import family_bars
    from scripts.platformkit.foundry import asof_supply, catalogue
    for family, spec in asof_supply.REGISTRY.items():
        for part in spec.source.split(","):
            _add(out, part, "asof_supply:%s" % family)
        if spec.season_table:
            _add(out, spec.season_table, "asof_supply:%s" % family)
    for name in catalogue.NAMED:
        _add(out, name, "catalogue")
    for pattern in catalogue.GLOBS:
        _add(out, pattern, "catalogue-glob")
    for fam in family_bars.load_families().families:
        for src in fam.sources:
            _add(out, src, "families:%s:%s" % (fam.horizon, fam.name))
    for src in _TEAMS_GAMES:
        _add(out, src, "screen_predictor._teams (HARDCODED)")


def _spines(out: Dict[str, List[str]]) -> None:
    from scripts.platformkit.eval_gate import close_join
    from scripts.platformkit.eval_gate import close_join_nba_mlb as cjnm
    for sport, spec in close_join._SPECS.items():
        base = "data/domains/%s/" % sport
        for filename in ("odds.parquet",) + (spec.spine_files or ("matches.parquet",)):
            _add(out, base + filename, "close_join:%s" % sport)
    for sport, paths in cjnm.SOURCES.items():   # nba: checkpoints/pregame/games; mlb: series/spine
        for path in paths:
            _add(out, _rel(path), "close_join_close:%s" % sport)


def _ingame(out: Dict[str, List[str]]) -> None:
    """The in-game tier's stores. A directory store contributes its files, not the directory.

    `ingame_grade_joined/` is WRITTEN on the pod (it is the paper node), so a DIFFERS there
    means the LOCAL copy is behind -- never a pod defect, and never a reason to ship.
    """
    from scripts.platformkit.foundry import ingame_screen_nba as isn
    from scripts.platformkit.foundry import ingame_screen_soccer as iss
    from scripts.platformkit.foundry import ingame_supply_mlb as ism
    _add(out, _rel(isn.S86_CSV), "ingame:nba")
    _add(out, _rel(ism.SERIES), "ingame:mlb")
    for store, origin in ((iss.STORE, "ingame:soccer"), (ism.JOINED, "ingame:mlb")):
        _add(out, _rel(store) + "/*.jsonl", origin)


def on_pod_path(origins: Iterable[str]) -> bool:
    """True when at least one origin is on the POD RUNNER's own path.

    S78's bar is "every source the sidecars + screen_predictor name". `foundry_runner` screens
    T0/T1 through `screen_predictor.corpus_states`, so the boot gate keeps: the corpora and their
    sidecar-recorded sources, the asof_supply bridge, the soccer/tennis close_join spines, the
    PREGAME families' own sources, and screen_predictor._teams. Enumerated but NOT gated, because
    no pod pass reads them and a gate that fails on them would be a false gate:

      ingame:*            the in-game tier's stores (run locally, never in a pod pass)
      families:<horizon>  a live_tick / period family's tick stores
      catalogue / -glob   the enumeration catalogue; `catalogue.absent()` explicitly allows a
                          NAMED path to be absent, and every path a screen actually READS also
                          arrives through asof_supply / families / the sidecars
      close_join_close:*  the close-corpus BUILDERS' inputs; the pod loads the built
                          gate_corpus_<sport>_close.parquet (S113 opt-in), never rebuilds it
    """
    skip = ("ingame:", "catalogue", "close_join_close:")
    for origin in origins:
        if origin.startswith(skip):
            continue
        if origin.startswith("families:") and not origin.startswith("families:pregame:"):
            continue
        return True
    return False


def required(ingame: bool = True) -> Dict[str, List[str]]:
    """{repo-relative path or unmatched glob: [origins]} -- every source the factory reads.

    `ingame=False` keeps only what `on_pod_path` accepts -- the set the pod's boot gate asserts.
    """
    out: Dict[str, List[str]] = {}
    _corpora(out)
    _registries(out)
    _spines(out)
    _ingame(out)
    return {k: v for k, v in sorted(out.items()) if ingame or on_pod_path(v)}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_rows(paths: Optional[Iterable[str]] = None) -> List[Tuple[str, int, str]]:
    """[(path, size, sha256)] for every required source PRESENT on this host."""
    rows = []
    for rel in (required() if paths is None else paths):
        full = _REPO_ROOT / rel
        if full.is_file():
            rows.append((rel, full.stat().st_size, _sha256(full)))
    return rows


def missing_local(paths: Optional[Iterable[str]] = None) -> List[str]:
    """Required sources absent on THIS host -- what the pod-side functional probe asserts empty."""
    return [rel for rel in (required() if paths is None else paths)
            if not (_REPO_ROOT / rel).is_file()]


def classify(local: Iterable[Tuple[str, int, str]],
             pod: Dict[str, str]) -> Dict[str, str]:
    """OK / DIFFERS / MISSING per path, from a local (path,size,sha) list + a pod sha listing."""
    return {rel: ("MISSING" if pod.get(rel) is None else
                  "OK" if pod[rel] == sha else "DIFFERS")
            for rel, _size, sha in local}


def pod_digests(paths: Iterable[str], repo: str = POD_REPO) -> Dict[str, str]:
    """ONE read-only ssh batch: `sha256sum` over the path list, fed on stdin. -> {path: sha}.

    Sent as BYTES on purpose: `text=True` newline-translates the stdin write on Windows, the pod
    then reads every path but the last with a trailing CR, and a broken listing reads as "the pod
    is missing 60 of 61 sources" -- a fail-open that looks exactly like the real finding.
    `sha256sum` exits nonzero when any listed file is absent (the normal case here), so an EMPTY
    stdout is the only transport failure, and it raises rather than reporting phantom MISSINGs.
    """
    listing = "\n".join(paths).encode("ascii")
    remote = "cd %s && xargs -d '\\n' -r sha256sum 2>/dev/null" % repo
    proc = subprocess.run(list(SSH) + [remote], input=listing, capture_output=True, timeout=900)
    if not proc.stdout.strip():
        raise RuntimeError("no sha256sum output from the pod (rc=%d): %s"
                           % (proc.returncode, proc.stderr.decode("utf-8", "replace")[-300:]))
    out: Dict[str, str] = {}
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            out[parts[1].strip().lstrip("*")] = parts[0]
    return out


def ship_command(missing: Iterable[str], repo: str = POD_REPO) -> str:
    """The exact tar-over-ssh command for the missing set. PRINTED, never run."""
    files = list(missing)
    if not files:
        return "(nothing missing -- no ship needed)"
    return ("printf '%s\\n' \\\n  " + " \\\n  ".join(files)
            + " \\\n  | tar -czf - -T - \\\n  | " + SSH_DISPLAY
            + " 'tar -xzf - -C %s'" % repo)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="factory data-source manifest (S78)")
    ap.add_argument("--check-pod", action="store_true",
                    help="compare against the pod in ONE read-only ssh sha256sum batch")
    ap.add_argument("--ship", action="store_true",
                    help="PRINT (never run) the tar-over-ssh command for the missing set")
    ap.add_argument("--verify-local", action="store_true",
                    help="exit nonzero when a required source is absent on THIS host")
    ap.add_argument("--pod-path-only", action="store_true",
                    help="only the pod runner's own pregame set (see on_pod_path)")
    args = ap.parse_args(argv)

    need = required(ingame=not args.pod_path_only)
    absent = missing_local(need)
    print("REQUIRED: %d source(s) from %d origin group(s)"
          % (len(need), len({o.split(":")[0] for v in need.values() for o in v})))
    if args.verify_local:
        for rel in absent:
            print("  ABSENT %s  <- %s" % (rel, ", ".join(sorted(set(need[rel])))))
        print("RESULT: %s" % ("FAIL -- %d absent" % len(absent) if absent
                              else "OK -- every required source present"))
        return 1 if absent else 0

    rows = local_rows(need)
    total = sum(size for _r, size, _s in rows)
    print("LOCAL: %d present, %d absent, %.1f MB" % (len(rows), len(absent), total / 1e6))
    for rel in absent:
        print("  LOCAL-ABSENT %s  <- %s" % (rel, ", ".join(sorted(set(need[rel])))))
    if not args.check_pod:
        for rel, size, sha in rows:
            print("  %-72s %10d  %s" % (rel, size, sha[:12]))
        return 0

    verdicts = classify(rows, pod_digests([r for r, _s, _h in rows]))
    counts = {v: sum(1 for x in verdicts.values() if x == v) for v in ("OK", "DIFFERS", "MISSING")}
    for rel, verdict in sorted(verdicts.items()):
        if verdict != "OK":
            print("  %-8s %s" % (verdict, rel))
    print("POD: OK %d / DIFFERS %d / MISSING %d (of %d compared)"
          % (counts["OK"], counts["DIFFERS"], counts["MISSING"], len(verdicts)))
    if args.ship:
        print("SHIP COMMAND (print only -- run it yourself):")
        print(ship_command(r for r, v in sorted(verdicts.items()) if v != "OK"))
    return 0 if counts["MISSING"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
