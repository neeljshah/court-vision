"""Name-derived metric fallback for ask()'s phrasing router.

Closes the 337-unaliased-metrics discoverability gap (audit 2026-07-17):
every VERIFIED claim metric whose family has a .index.jsonl sidecar becomes
reachable by simply SAYING ITS NAME in a question ("gf diff", "whiff rate",
"home minus away ppg") -- no hand alias required.  The hand-curated
_METRIC_SYNONYMS dict in ask_index still wins first (human phrasings);
this fallback only fires when no alias matched.

Honesty properties:
  * exact normalized-name matching only (underscores -> spaces) -- never a
    fuzzy guess;
  * longest-name-wins, and a TIE between two DIFFERENT metrics at the same
    length returns None (honest refuse, never a coin flip);
  * formula-shaped metric strings (containing '(', '/', '*', '-' with
    spaces) are skipped -- they are computations, not names anyone says.

Families without an index sidecar are invisible here until
claims_index.build_index runs for them (pod job).  Safe failure mode:
unmatched phrasing keeps refusing exactly as before.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DEFAULT_CLAIMS_DIR = (Path(__file__).resolve().parents[3]
                      / "data" / "cache" / "intel_claims")
_CACHE: tuple[float, dict[str, set[str]]] | None = None
_NAME_RE = re.compile(r"^[a-z0-9_]+$")


def _phrase(metric: str) -> str | None:
    """metric name -> spoken phrase, or None if formula-shaped."""
    if not _NAME_RE.match(metric):
        return None
    return metric.replace("_", " ").strip()


def _build(claims_dir: Path) -> dict[str, set[str]]:
    """phrase -> set of real metric names (a set >1 means ambiguous)."""
    out: dict[str, set[str]] = {}
    for idx in claims_dir.glob("*.index.jsonl"):
        try:
            with open(idx, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        m = json.loads(line).get("metric")
                    except json.JSONDecodeError:
                        continue
                    if not m or not isinstance(m, str):
                        continue
                    ph = _phrase(m.lower())
                    if ph and len(ph) >= 4:  # single tiny tokens too collision-prone
                        out.setdefault(ph, set()).add(m)
        except OSError:
            continue
    return out


def _name_map(claims_dir: Path) -> dict[str, set[str]]:
    """mtime-keyed cache: rebuilt only when the newest index sidecar changes."""
    global _CACHE
    try:
        stamp = max((p.stat().st_mtime for p in claims_dir.glob("*.index.jsonl")),
                    default=0.0)
    except OSError:
        stamp = 0.0
    if _CACHE is None or _CACHE[0] != stamp:
        _CACHE = (stamp, _build(claims_dir))
    return _CACHE[1]


def metric_from_name(text: str, claims_dir: Path) -> str | None:
    """Longest metric-name-as-phrase found in `text`, or None.

    Ambiguity at the winning length (two DIFFERENT metrics) -> None:
    refusing is honest, guessing is not.

    Text is underscore-normalized the same way `_phrase()` normalizes
    metric names (underscores -> spaces) before matching -- otherwise a
    literal "usage_pct" in a question never matches the "usage pct" phrase
    key, and a short, unrelated real metric name that happens to appear as
    a bare word (e.g. a metric literally named "rank") wins by default
    (regression 2026-07-19: "rank on usage_pct" resolved to "rank").
    """
    low = (text or "").lower().replace("_", " ")
    names = _name_map(claims_dir)
    best_len = -1
    best: set[str] | None = None
    for ph, metrics in names.items():
        if ph in low and len(ph) > best_len:
            best_len, best = len(ph), metrics
    if not best:
        return None
    if len(best) > 1:
        return None  # same phrase, different metrics -- honest refuse
    return next(iter(best))
