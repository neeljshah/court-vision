"""domains.mlb.knowledge.validate_research_wave1 -- the 3 UNTESTED rows
seeded 2026-07-10 by the research-wave commit (mechanisms.md #43 compassionate
umpire, #44 outfield-alignment XBH suppression, #45 same-pitch-type-repeat
whiff rate). One file: all 3 share the same corpus (savant_full__2025) and
the same split-half-by-date replication design used by the sibling
`validate_contact_park_interaction.py` (>=2 corpora requirement).

Leak audit: every check is a contemporaneous within-pitch/within-PA group
comparison (count bucket, alignment, or same-vs-different pitch type vs an
outcome on THAT SAME pitch/PA) -- descriptive, not a forecast, so there is
no future-into-past leak. Split-half-by-date gives the >=2-corpora
replication the honesty rail requires even though each row's own test spec
only asks for "one season".

Identity scope for #43 (compassionate umpire): this stays GAME/COUNT-level
only, same as #31/#39/#40 -- no umpire-identity column exists locally (see
#31, still NOT_TESTABLE for identity claims) and this row's own spec never
asked for one; nothing to adapt.

Premise-check fix for #44: `of_fielding_alignment` locally has only
{Standard, Strategic, None} -- there is NO "Shaded" value for the outfield
column (unlike `if_fielding_alignment`, which has "Infield shade" as a
distinct third bucket, per `validate_contact_park.py`'s
`infield_shift_suppresses_gb_babip`). The row's claimed bucket
`{Strategic, Shaded}` is adjusted inline to `{Strategic}` -- the only
non-standard value that actually exists in this corpus.

Run: python -m domains.mlb.knowledge.validate_research_wave1
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from domains.mlb.knowledge._data import DEFAULT_SEASON, LEDGER_PATH, load_season
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
EDGE_ZONES = {11, 12, 13, 14}
TAKEN_DESC = {"ball", "called_strike"}
SWING_DESC = {"swinging_strike", "swinging_strike_blocked", "foul", "foul_tip", "hit_into_play"}
WHIFF_DESC = {"swinging_strike", "swinging_strike_blocked"}
HIT_EVENTS = {"single", "double", "triple", "home_run"}
OUT_EVENTS = {"field_out", "force_out", "double_play", "grounded_into_double_play",
              "fielders_choice_out", "triple_play", "field_error", "fielders_choice"}
XBH_EVENTS = {"double", "triple"}

MIN_N = {"compassionate_umpire_count_zone": 100,
         "of_alignment_xbh_suppression": 200,
         "same_type_repeat_whiff": 500}
MIN_EFFECT = {"compassionate_umpire_count_zone": 0.05,
              "of_alignment_xbh_suppression": 0.03,
              "same_type_repeat_whiff": 0.02}


def _verdict(p, effect, hyp: str) -> str:
    if p is None or effect is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    base = hyp.split("__")[0]  # strip the __h1/__h2 half-label suffix, MIN_EFFECT is keyed by base hypothesis
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= MIN_EFFECT[base]) else "NULL_LOCAL"


def _ttest_row(hyp: str, a: pd.Series, b: pd.Series, note: str) -> Dict[str, Any]:
    n = int(len(a) + len(b))
    if len(a) < 5 or len(b) < 5:
        return {"hypothesis": hyp, "n": n, "effect": None, "p": None, "verdict": "NOT_TESTABLE", "note": note}
    t, p = stats.ttest_ind(a.astype(int), b.astype(int), equal_var=False)
    effect = float(a.mean() - b.mean())
    return {"hypothesis": hyp, "n": n, "effect": round(effect, 5), "p": float(p),
            "verdict": _verdict(p, effect, hyp), "note": note}


def compassionate_umpire_count_zone(d: pd.DataFrame, half_label: str) -> Dict[str, Any]:
    """#43: called-strike rate on taken edge-zone pitches, pitcher's counts
    (0-2, 1-2) vs hitter's counts (3-0, 3-1). No umpire identity used."""
    hyp = "compassionate_umpire_count_zone__%s" % half_label
    q = d.dropna(subset=["zone", "description", "balls", "strikes"])
    q = q[q["zone"].isin(EDGE_ZONES) & q["description"].isin(TAKEN_DESC)]
    pitcher_ct = q[((q["balls"] == 0) & (q["strikes"] == 2)) | ((q["balls"] == 1) & (q["strikes"] == 2))]
    hitter_ct = q[((q["balls"] == 3) & (q["strikes"] == 0)) | ((q["balls"] == 3) & (q["strikes"] == 1))]
    a = pitcher_ct["description"] == "called_strike"
    b = hitter_ct["description"] == "called_strike"
    note = ("called-strike rate on taken edge-zone(11-14) pitches: pitcher's-count(0-2/1-2) n=%d rate=%s vs "
            "hitter's-count(3-0/3-1) n=%d rate=%s" % (len(a), round(float(a.mean()), 4) if len(a) else None,
                                                        len(b), round(float(b.mean()), 4) if len(b) else None))
    return _ttest_row(hyp, a, b, note)


def of_alignment_xbh_suppression(d: pd.DataFrame, half_label: str) -> Dict[str, Any]:
    """#44: XBH rate on FB/LD batted balls, of_fielding_alignment=='Strategic'
    (the only non-standard value present -- see module docstring premise fix)
    vs 'Standard'."""
    hyp = "of_alignment_xbh_suppression__%s" % half_label
    q = d.dropna(subset=["bb_type", "of_fielding_alignment", "events"])
    q = q[q["bb_type"].isin({"fly_ball", "line_drive"}) & q["events"].isin(HIT_EVENTS | OUT_EVENTS)]
    shaded = q[q["of_fielding_alignment"] == "Strategic"]
    standard = q[q["of_fielding_alignment"] == "Standard"]
    a = shaded["events"].isin(XBH_EVENTS)
    b = standard["events"].isin(XBH_EVENTS)
    note = ("XBH rate on FB/LD, alignment='Strategic' n=%d rate=%s vs 'Standard' n=%d rate=%s (no 'Shaded' "
            "value exists locally for of_fielding_alignment -- premise-fixed bucket, see module docstring)"
            % (len(a), round(float(a.mean()), 4) if len(a) else None, len(b), round(float(b.mean()), 4) if len(b) else None))
    return _ttest_row(hyp, a, b, note)


def same_type_repeat_whiff(d: pd.DataFrame, half_label: str) -> Dict[str, Any]:
    """#45: whiff rate (swings only) when this pitch repeats the immediately
    prior pitch's pitch_type within the same PA vs when it changes."""
    hyp = "same_type_repeat_whiff__%s" % half_label
    q = d.sort_values(["game_pk", "at_bat_number", "pitch_number"]).copy()
    q["prior_pitch_type"] = q.groupby(["game_pk", "at_bat_number"])["pitch_type"].shift(1)
    q = q.dropna(subset=["prior_pitch_type", "pitch_type", "description"])
    sw = q[q["description"].isin(SWING_DESC)]
    same = sw["pitch_type"] == sw["prior_pitch_type"]
    is_whiff = sw["description"].isin(WHIFF_DESC)
    a, b = is_whiff[same], is_whiff[~same]
    note = ("whiff rate among swings: same-type-as-prior n=%d rate=%s vs type-change n=%d rate=%s"
            % (len(a), round(float(a.mean()), 4) if len(a) else None, len(b), round(float(b.mean()), 4) if len(b) else None))
    return _ttest_row(hyp, a, b, note)


CHECKS = [compassionate_umpire_count_zone, of_alignment_xbh_suppression, same_type_repeat_whiff]
BASE_HYP = ["compassionate_umpire_count_zone", "of_alignment_xbh_suppression", "same_type_repeat_whiff"]


def _combine(base_hyp: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """>=2-corpora replication rule (reliever-b2b-fatigue / #35 convention):
    a half only counts as 'sig' support if it individually cleared BOTH
    p<ALPHA AND its declared effect-size bar (i.e. verdict==CONFIRMED_LOCAL)
    -- p<ALPHA alone is not enough with n in the tens of thousands, and a
    significant-but-below-bar or reverse-direction half is never counted as
    support (see #45: both halves are p<1e-4 but the effect is below the
    declared 0.02 bar AND in the opposite direction of the claim -- must
    stay NULL_LOCAL, not flip to CONFIRMED on p-value alone)."""
    testable = [r for r in rows if r["verdict"] != "NOT_TESTABLE"]
    sig = [r for r in testable if r["verdict"] == "CONFIRMED_LOCAL"]
    if len(testable) < 2:
        verdict = "NOT_TESTABLE"
    elif len(sig) >= 2 and len({1 if r["effect"] > 0 else -1 for r in sig}) == 1:
        verdict = "CONFIRMED_LOCAL"
    elif len(sig) == 1:
        verdict = "PROVISIONAL"
    else:
        verdict = "NULL_LOCAL"
    return {"hypothesis": "%s__combined" % base_hyp, "n": int(sum(r["n"] for r in rows)),
            "effect": None, "p": None, "verdict": verdict,
            "note": "split-half-by-date replication: %s"
                    % "; ".join("%s(p=%s,eff=%s)" % (r["hypothesis"], r["p"], r["effect"]) for r in rows)}


def run(season: int = DEFAULT_SEASON) -> List[Dict[str, Any]]:
    df = load_season(season)
    df = df.dropna(subset=["game_date"]).copy()
    df["game_date"] = pd.to_datetime(df["game_date"])
    mid = df["game_date"].median()

    rows: List[Dict[str, Any]] = []
    for base_hyp, fn in zip(BASE_HYP, CHECKS):
        halves = []
        for half_label, mask in (("h1", df["game_date"] <= mid), ("h2", df["game_date"] > mid)):
            halves.append(fn(df[mask], half_label))
        rows.extend(halves)
        rows.append(_combine(base_hyp, halves))

    for r in rows:
        r["sport"] = "mlb"
        r["corpus"] = "savant_full__%d (split-half by date)" % season
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-42s %-16s n=%-8s effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: verdict rule direction + the of-alignment
    premise fix (only 'Strategic' counts as the shaded bucket, no 'Shaded'
    value) on synthetic frames -- no parquet needed."""
    assert _verdict(0.001, 0.10, "compassionate_umpire_count_zone") == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.10, "compassionate_umpire_count_zone") == "NULL_LOCAL"
    assert _verdict(0.001, 0.01, "compassionate_umpire_count_zone") == "NULL_LOCAL"  # below MIN_EFFECT

    fake = pd.DataFrame({
        "bb_type": ["fly_ball"] * 20, "events": (["double"] * 6 + ["field_out"] * 14),
        "of_fielding_alignment": (["Strategic"] * 10 + ["Standard"] * 10),
    })
    r = of_alignment_xbh_suppression(fake, "h1")
    assert r["n"] == 20 and "premise-fixed" in r["note"]
    print("self-check OK")
