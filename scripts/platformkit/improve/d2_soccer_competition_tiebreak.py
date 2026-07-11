"""D2 (WEEKEND_WATCHBOARD.md section 4): soccer mechanisms #38
(trailing_team_shot_rate) and #41 (setpiece_xg_persistence) each clear their
declared bar on split-half-1 (even/odd index for #38; per-competition median
date for #41) but MISS it on split-half-2 (mechanisms.md:369, :429 /
validation_ledger.jsonl trailing_team_shot_rate__split_B p=5.73e-16 eff
0.01871<0.02; setpiece_xg_persistence__by_index p=0.0416>0.01). WATCHBOARD
prescription: a 3rd INDEPENDENT split -- whole-COMPETITION assignment (cached
locally, no network) -- as the tiebreak.

PRE-REGISTERED RULE (fixed before this script is run against data):
  For each mechanism, compute the competition-level split using the EXACT
  metric/bar/alpha the ORIGINAL test declared (reused verbatim, not
  re-derived, from validate_research_wave2.py / validate_research_wave4.py):
    - same SIGN as the original positive finding, AND clears the original
      |effect|>=bar AND p<alpha bar -> 2 of 3 independent splits now clear
      the bar -> label UPGRADES to CONFIRMED_LOCAL (family convention: 2/3
      independent splits = CONFIRMED_LOCAL, same rule ULTRA16 ADJ-1 uses).
    - opposite sign, or same-sign but short of the bar, WITH adequate n
      (>= the original test's min-n floor: 20 team-match units for #38,
      5 common teams for #41) -> label DOWNGRADES to NULL_LOCAL (2 of 3 now
      miss the bar).
    - n below that floor (too few common teams / competitions confounded)
      -> UNDERPOWERED, n cited, not a directional verdict.
    - split literally impossible to compute (NaN, <5 common teams) ->
      NOT_TESTABLE.

Split construction: assign each of the 80 competitions in
match_meta_full.parquet (3,961/4,235 dated matches) to group A or B by greedy
match-count balancing (largest competition first, always to the
currently-smaller group) -- deterministic, no match crosses a group, and it
is orthogonal to both prior splits (by-index cuts across competitions freely;
by-date cuts WITHIN each competition; this one cuts BETWEEN competitions).

Reuses `_accumulate`/`_score_trailing`/`_row`/`_verdict` from
validate_research_wave2.py and `_setpiece_xg_by_team`/`_persistence` from
validate_research_wave4.py verbatim -- no new statistical logic, only a new
grouping key. Leak audit: identical to the parent scripts (within-match
structural comparison for #38, split-half correlation of closed matches for
#41 -- no future-into-past leak either way).

Run: python -m scripts.platformkit.improve.d2_soccer_competition_tiebreak
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pandas as pd

from domains.soccer.knowledge._data import EVENTS_DIR, LEDGER_PATH, extract_match_facts, load_events
from domains.soccer.knowledge.validate_research_wave2 import (
    ALPHA as TRAIL_ALPHA, MIN_EFFECT as TRAIL_MIN_EFFECT, _accumulate, _row as _trail_row,
    _score_trailing, _verdict as _trail_verdict,
)
from domains.soccer.knowledge.validate_research_wave4 import (
    MIN_SHOTS_PER_HALF, _persistence, _row as _sp_row, _setpiece_xg_by_team,
    _verdict as _sp_verdict,
)
from scripts.platformkit.io_atomic import append_jsonl_atomic

TRAIL_MIN_N = 20  # team-match units; well under original split-half n~2000, generous floor
SP_MIN_N = MIN_SHOTS_PER_HALF // 2  # common-teams floor below which persistence r is noise


def competition_groups() -> Dict[str, str]:
    """comp -> 'A'/'B', greedy match-count balancing, deterministic order."""
    meta = pd.read_parquet(EVENTS_DIR.parent / "match_meta_full.parquet")
    counts = meta.groupby("competition").size().sort_values(ascending=False)
    totals = {"A": 0, "B": 0}
    out: Dict[str, str] = {}
    for comp, n in counts.items():
        g = "A" if totals["A"] <= totals["B"] else "B"
        out[comp] = g
        totals[g] += int(n)
    return out


def match_groups() -> Tuple[Dict[str, str], pd.DataFrame]:
    """match_id -> group, restricted to the 3,961 dated matches (same
    dated-subset restriction #41's by_date split already uses)."""
    meta = pd.read_parquet(EVENTS_DIR.parent / "match_meta_full.parquet")
    cg = competition_groups()
    meta = meta[meta["competition"].isin(cg)].copy()
    meta["grp"] = meta["competition"].map(cg)
    return dict(zip(meta["match_id"], meta["grp"])), meta


def _single_pass(mgroup: Dict[str, str]):
    """ponytail: one read per event file feeds BOTH mechanisms (was 3 separate
    full-corpus passes -- trailing-split, pooled-trailing, setpiece-split --
    re-reading the same ~3,900 multi-MB StatsBomb match files 3x; this box
    runs ~45 other python processes concurrently, so I/O was the bottleneck).
    """
    accs = {g: {k: [] for k in ("early_shift", "late_shift", "trailing_rate", "tied_rate")}
            for g in ("A", "B")}
    half: Dict[str, Dict[str, List[float]]] = {"A": {}, "B": {}}
    n_scanned = {"A": 0, "B": 0}
    for match_id, grp in mgroup.items():
        fp = EVENTS_DIR / ("%s.json" % match_id)
        if not fp.is_file():
            continue
        n_scanned[grp] += 1
        events = load_events(match_id)
        _accumulate(extract_match_facts(events), accs[grp])
        for team, xgs in _setpiece_xg_by_team(events).items():
            half[grp].setdefault(team, []).extend(xgs)
    return accs, half, n_scanned


def trailing_competition_split(accs, n_scanned) -> List[Dict[str, Any]]:
    rows = []
    for g in ("A", "B"):
        eff, p = _score_trailing(accs[g])
        rows.append(_trail_row("trailing_team_shot_rate__split_competition_%s" % g,
                                len(accs[g]["trailing_rate"]), eff, p,
                                "split-half(whole-competition group) robustness check, group=%s, "
                                "n_matches_scanned=%d" % (g, n_scanned[g])))
    return rows


def setpiece_competition_split(half, n_scanned) -> Dict[str, Any]:
    r, p, n = _persistence(half["A"], half["B"])
    return _sp_row("setpiece_xg_persistence__by_competition", n, r, p,
                   "split-half(whole-competition group) Pearson r of per-team mean set-piece "
                   "statsbomb_xg, teams with >=%d set-piece shots/half, group_A_matches=%d, "
                   "group_B_matches=%d" % (MIN_SHOTS_PER_HALF, n_scanned["A"], n_scanned["B"]))


def tiebreak(original_sign_positive: bool, effect: float, p: float, n: int, min_n: int,
             verdict_fn) -> str:
    """Pre-registered rule applied post-hoc to one competition-split result."""
    if p is None or p != p:
        return "NOT_TESTABLE"
    if n < min_n:
        return "UNDERPOWERED(n=%d,need>=%d)" % (n, min_n)
    same_sign = (effect > 0) == original_sign_positive
    cleared = verdict_fn(p, effect) == "CONFIRMED_LOCAL"
    if same_sign and cleared:
        return "CONFIRMED_LOCAL -> label upgrades (2/3 splits clear the bar)"
    return "NULL_LOCAL -> label downgrades (2/3 splits miss the bar)"


def main() -> int:
    mgroup, meta = match_groups()
    print("competition groups: %d dated matches (%d comps)" % (len(mgroup), meta["competition"].nunique()))

    accs, half, n_scanned = _single_pass(mgroup)

    trail_rows = trailing_competition_split(accs, n_scanned)
    for r in trail_rows:
        r.update(sport="soccer", corpus="statsbomb_events_full__competition_split", edge_claimed=False)
        append_jsonl_atomic(LEDGER_PATH, r)
        print("%-46s %-40s n=%-6d eff=%+.5f p=%.4g" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"]))
    # pooled group A+B (paired-t is symmetric, so pool the two groups' raw rate lists
    # for one pooled effect/p, same convention as validate_research_wave2.py::run())
    pooled_acc = {k: accs["A"][k] + accs["B"][k] for k in accs["A"]}
    eff, p = _score_trailing(pooled_acc)
    n = len(pooled_acc["trailing_rate"])
    verdict38 = tiebreak(True, eff, p, n, TRAIL_MIN_N, lambda pp, ee: _trail_verdict(pp, ee, TRAIL_MIN_EFFECT))
    print("#38 pooled competition-split: n=%d eff=%+.5f p=%.4g -> %s" % (n, eff, p, verdict38))

    sp_row = setpiece_competition_split(half, n_scanned)
    sp_row.update(sport="soccer", corpus="statsbomb_events_full__research_wave4_competition",
                  edge_claimed=False)
    append_jsonl_atomic(LEDGER_PATH, sp_row)
    print("%-46s %-40s n=%-6d eff=%+.5f p=%.4g" % (
        sp_row["hypothesis"], sp_row["verdict"], sp_row["n"],
        sp_row["effect"] if sp_row["effect"] is not None else float("nan"),
        sp_row["p"] if sp_row["p"] is not None else float("nan")))
    verdict41 = tiebreak(True, sp_row["effect"] or 0.0, sp_row["p"] if sp_row["p"] == sp_row["p"] else float("nan"),
                          sp_row["n"], SP_MIN_N, _sp_verdict)
    print("#41 competition-split: n=%d -> %s" % (sp_row["n"], verdict41))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: tiebreak rule behaves per the pre-registered spec."""
    v = lambda p, e: "CONFIRMED_LOCAL" if (p < 0.01 and abs(e) >= 0.02) else "NULL_LOCAL"
    assert tiebreak(True, 0.03, 0.001, 100, 20, v).startswith("CONFIRMED_LOCAL")
    assert tiebreak(True, 0.01, 0.001, 100, 20, v).startswith("NULL_LOCAL")  # short of effect bar
    assert tiebreak(True, -0.03, 0.001, 100, 20, v).startswith("NULL_LOCAL")  # opposite sign
    assert tiebreak(True, 0.03, 0.001, 5, 20, v).startswith("UNDERPOWERED")
    assert tiebreak(True, 0.03, float("nan"), 100, 20, v) == "NOT_TESTABLE"
    print("self-check OK")
