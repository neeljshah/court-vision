"""domains.soccer.knowledge.validate_research_wave4 -- research-wave-4 UNTESTED
row #41 (team set-piece xG-per-shot persistence) from
domains/soccer/knowledge/mechanisms.md, against the full local StatsBomb
event cache (4,235 matches). Leak audit: split-half correlation of a team's
own historical set-piece xG-per-shot against itself in a disjoint half of the
corpus -- no future-into-past leak (descriptive trait-stability check of
already-closed possessions, same leak profile as #5/#35's split-half
persistence designs). Two INDEPENDENT split methods, per row #41's declared
2-group replication bar: (1) match-DATE split (median date per corpus, using
`match_meta_full.parquet` for the 3,961/4,235 matches that carry a date --
mirrors `validate_season_structure.py::finishing_skill_persistence_split_half`),
(2) match-INDEX split (even/odd position in the raw event-file glob, no date
join needed -- mirrors `validate_research_wave3.py::run_split_half`).

Run: python -m domains.soccer.knowledge.validate_research_wave4
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pandas as pd
from scipy import stats

from domains.soccer.knowledge._data import EVENTS_DIR, LEDGER_PATH, load_events
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
MIN_EFFECT_R = 0.15  # pearson r, per row #41's declared bar
MIN_SHOTS_PER_HALF = 10  # per row #41's declared min-n floor
SET_PIECE_TYPES = {"Corner", "Free Kick"}


def _verdict(p: float, effect: float) -> str:
    if p is None or p != p:  # NaN-safe
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= MIN_EFFECT_R) else "NULL_LOCAL"


def _setpiece_xg_by_team(events: List[Dict[str, Any]]) -> Dict[str, List[float]]:
    """Per-team list of `shot.statsbomb_xg` for shots with
    `shot.type.name` in {Corner, Free Kick} in one match."""
    out: Dict[str, List[float]] = {}
    for e in events:
        if (e.get("type") or {}).get("name") != "Shot":
            continue
        shot = e.get("shot") or {}
        if (shot.get("type") or {}).get("name") not in SET_PIECE_TYPES:
            continue
        xg = shot.get("statsbomb_xg")
        team = (e.get("team") or {}).get("name")
        if xg is None or not team:
            continue
        out.setdefault(team, []).append(float(xg))
    return out


def _persistence(half_a: Dict[str, List[float]], half_b: Dict[str, List[float]]) -> Tuple[float, float, int]:
    """Split-half Pearson r of per-team mean set-piece xG, teams with
    >=MIN_SHOTS_PER_HALF set-piece shots in BOTH halves."""
    keep_a = {t: sum(v) / len(v) for t, v in half_a.items() if len(v) >= MIN_SHOTS_PER_HALF}
    keep_b = {t: sum(v) / len(v) for t, v in half_b.items() if len(v) >= MIN_SHOTS_PER_HALF}
    common = sorted(set(keep_a) & set(keep_b))
    if len(common) < 5:
        return float("nan"), float("nan"), len(common)
    r, p = stats.pearsonr([keep_a[t] for t in common], [keep_b[t] for t in common])
    return float(r), float(p), len(common)


def _row(hyp: str, n: int, effect: float, p: float, note: str) -> Dict[str, Any]:
    return {"hypothesis": hyp, "n": n,
            "effect": round(effect, 5) if effect == effect else None,
            "p": float(p) if p == p else None, "verdict": _verdict(p, effect), "note": note}


def setpiece_xg_persistence_by_date() -> Dict[str, Any]:
    """Split A: match-date median split within each competition, using
    `match_meta_full.parquet` (3,961 of 4,235 event files carry a date;
    undated files are excluded from this reading only -- the index-split
    reading below covers all 4,235)."""
    from domains.soccer.knowledge._data import STATSBOMB_DIR
    meta = pd.read_parquet(STATSBOMB_DIR / "match_meta_full.parquet")
    meta["match_date"] = pd.to_datetime(meta["match_date"])
    half_a: Dict[str, List[float]] = {}
    half_b: Dict[str, List[float]] = {}
    n_matches = 0
    for comp, grp in meta.groupby("competition"):
        mid = grp["match_date"].median()
        for _, row in grp.iterrows():
            fp = EVENTS_DIR / ("%s.json" % row["match_id"])
            if not fp.is_file():
                continue
            n_matches += 1
            target = half_a if row["match_date"] <= mid else half_b
            for team, xgs in _setpiece_xg_by_team(load_events(row["match_id"])).items():
                target.setdefault(team, []).extend(xgs)
    r, p, n = _persistence(half_a, half_b)
    return _row("setpiece_xg_persistence__by_date", n, r, p,
                "split-half(per-competition median match date) Pearson r of per-team mean "
                "set-piece statsbomb_xg, teams with >=%d set-piece shots/half, "
                "n_matches_scanned=%d (dated subset)" % (MIN_SHOTS_PER_HALF, n_matches))


def setpiece_xg_persistence_by_index() -> Dict[str, Any]:
    """Split B: even/odd position in the raw event-file glob -- the 2nd
    independent group, covers the full 4,235-match cache (no date join)."""
    import glob
    from pathlib import Path

    half_a: Dict[str, List[float]] = {}
    half_b: Dict[str, List[float]] = {}
    n_matches = 0
    for i, fp in enumerate(glob.glob(str(EVENTS_DIR / "*.json"))):
        n_matches += 1
        target = half_a if i % 2 == 0 else half_b
        for team, xgs in _setpiece_xg_by_team(load_events(Path(fp).stem)).items():
            target.setdefault(team, []).extend(xgs)
    r, p, n = _persistence(half_a, half_b)
    return _row("setpiece_xg_persistence__by_index", n, r, p,
                "split-half(even/odd event-file index) Pearson r of per-team mean set-piece "
                "statsbomb_xg, teams with >=%d set-piece shots/half, n_matches_scanned=%d"
                % (MIN_SHOTS_PER_HALF, n_matches))


def run() -> List[Dict[str, Any]]:
    rows = [setpiece_xg_persistence_by_date(), setpiece_xg_persistence_by_index()]
    for r in rows:
        r["sport"] = "soccer"
        r["corpus"] = "statsbomb_events_full__research_wave4"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        eff = "%+.5f" % r["effect"] if r["effect"] is not None else "--"
        p = "%.4g" % r["p"] if r["p"] is not None else "--"
        print("%-38s %-16s n=%-6d effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], eff, p, r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: verdict thresholds behave as declared."""
    assert _verdict(0.001, 0.2) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.2) == "NULL_LOCAL"
    assert _verdict(float("nan"), 0.2) == "NOT_TESTABLE"
    assert _verdict(0.001, 0.05) == "NULL_LOCAL"  # p ok but effect below bar
    print("self-check OK")
