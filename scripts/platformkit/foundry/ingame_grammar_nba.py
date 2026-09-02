"""S102: the FROZEN NBA in-game grammar -- derived state hypotheses over the tick corpus.

The NBA in-play tick corpus (`data/cache/inplay_odds/nba_checkpoints_full.parquet`, and the
S86 SCREEN-side archive derived from it) carries only score / period / clock / margin /
market / outcome per tick. Every NBA in-game arm charged so far was ONE hand-picked form.
This module freezes a GRAMMAR of DERIVED state instead, so the screen is an enumeration
rather than a hand-pick.

TICK-TIME AS-OF CONTRACT (inherited verbatim from S82 `foundry/ingame_screen.py`)
--------------------------------------------------------------------------------
Every base column at tick t of game g is a function of the ticks of g with timestamp <= t
ONLY. Enforced, not asserted: `ingame_screen.assert_tick_asof` rebuilds the table from the
causal prefix and requires row k to be unchanged (truncation invariance). Every operation
below is backward-only (shift, cumulative count, expanding EW, forward-fill), so a peek at
a later tick would change a probe row and raise `TickTimeLeak`.

THE FROZEN GRID -- 16 base columns x 6 transforms x 6 conditionings = 576 hypotheses
------------------------------------------------------------------------------------
base        margin trajectory (dmargin over k=3,5,10,20 ticks), run length (consecutive
            ticks of same-sign margin change), lead changes so far and their rate, scoring
            pace and pace vs the game's OWN period-1 pace, time-decayed margin at halflives
            60/180/600 s, margin x time-remaining interactions, and the two raw state
            anchors (margin, minutes remaining).
transform   raw, ew(halflife = 3, 5, 10, 20 ticks), delta_vs_prior -- the tick-grain subset
            of the frozen 9-transform alphabet; rank_in_league / z_vs_league /
            ratio_to_opponent need league or opponent tables that do not exist at tick
            grain, so they are NOT enumerated and are named here rather than dropped.
conditioning  unconditional, and phase = 1, 2, 3, 4, 5 (5 = any overtime period). A
            conditioned hypothesis is the column masked to that phase; the tier's own
            "missing != bad" rule falls a masked tick back to the null on BOTH arms.

Hypotheses are `foundry.grammar.Hypothesis` values and are deduped by `semantic_hash`, so
this grammar cannot silently double-count a form. NOT SUPPLIED by this corpus, named and
never proxied: the pregame total (so "pace vs the pregame implied pace" is unavailable and
the game's own period-1 pace is used as the reference instead), possession counts, lineups,
free-throw / foul state, and any event grain finer than the poller's tick.

A SCREEN IS A NON-FINDING: nothing here charges a ledger, seals a prereg or reads K.
Calibration language only. ASCII only.
Per-file test: python -m pytest tests/platformkit/foundry/test_ingame_grammar_nba.py -q
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.foundry.grammar import Hypothesis, semantic_hash

FAMILY = "ingame_nba_tickgrid"
SPORT, HORIZON, MARKET = "nba", "live_tick", "inplay"
DMARGIN_K: Tuple[int, ...] = (3, 5, 10, 20)
HALFLIVES_S: Tuple[int, ...] = (60, 180, 600)
EW_HALFLIVES: Tuple[int, ...] = (3, 5, 10, 20)
PHASES: Tuple[str, ...] = ("1", "2", "3", "4", "5")   # 5 = any overtime period
MIN_ELAPSED = 0.5                                     # minutes; the clock floor for a rate
# The 16 frozen base columns, in the order the family spec lists them as members.
BASE: Tuple[str, ...] = (
    "margin", "rem",
    "dmargin_k3", "dmargin_k5", "dmargin_k10", "dmargin_k20",
    "run_len_signed", "lead_changes", "lead_change_rate",
    "pace_total", "pace_ratio_p1",
    "tdm_h60", "tdm_h180", "tdm_h600",
    "margin_x_rem", "margin_over_sqrt_rem",
)
# (transform, params) -- the tick-grain subset of the frozen 9-transform alphabet.
TRANSFORMS: Tuple[Tuple[str, tuple], ...] = (
    ("raw", ()),
    *tuple(("ew", (("halflife", h),)) for h in EW_HALFLIVES),
    ("delta_vs_prior", ()),
)
NOT_ENUMERATED = ("rank_in_league", "z_vs_league", "ratio_to_opponent")
NOT_SUPPLIED = ("pregame_total", "possessions", "lineup_on_court", "foul_state",
                "free_throw_state", "event_grain_below_tick")
REQUIRED = ("game", "ts", "period", "margin", "rem", "elapsed", "score_home", "score_away")


def transform_key(transform: str, params: tuple) -> str:
    """The short, frozen suffix a transform contributes to a grid column name."""
    if transform == "ew":
        return "ew%d" % dict(params)["halflife"]
    return {"raw": "raw", "delta_vs_prior": "dprior"}[transform]


def column_key(base: str, transform: str, params: tuple) -> str:
    return "%s|%s" % (base, transform_key(transform, params))


def _scan(games: np.ndarray, margin: np.ndarray, ts: np.ndarray) -> Dict[str, np.ndarray]:
    """One backward-only pass: run length, lead changes, and the three time-decayed margins.

    Every value written at row i depends on rows < i of the SAME game plus row i, so
    withholding the ticks after i cannot change it (truncation invariance).
    """
    n = len(margin)
    run, leads = np.zeros(n), np.zeros(n)
    tdm = {h: np.zeros(n) for h in HALFLIVES_S}
    state = {h: 0.0 for h in HALFLIVES_S}
    prev_game, prev_margin, prev_ts = None, 0.0, 0.0
    prev_sign, prev_lead, run_len = 0, 0, 0.0
    for i in range(n):
        game, m, t = games[i], float(margin[i]), float(ts[i])
        if game != prev_game:
            prev_game, run_len, prev_sign = game, 0.0, 0
            prev_lead, changes = int(np.sign(m)), 0.0
            for h in HALFLIVES_S:
                state[h] = m
        else:
            step = int(np.sign(m - prev_margin))
            run_len = (run_len + step) if step != 0 and step == prev_sign else float(step)
            prev_sign = step if step != 0 else prev_sign
            changes = leads[i - 1]
            lead = int(np.sign(m))
            if lead != 0 and prev_lead != 0 and lead != prev_lead:
                changes += 1.0
            if lead != 0:
                prev_lead = lead
            gap = max(0.0, t - prev_ts)
            for h in HALFLIVES_S:
                a = 0.5 ** (gap / float(h))
                state[h] = a * state[h] + (1.0 - a) * m
        run[i], leads[i] = run_len, changes
        for h in HALFLIVES_S:
            tdm[h][i] = state[h]
        prev_margin, prev_ts = m, t
    out = {"run_len_signed": run, "lead_changes": leads}
    for h in HALFLIVES_S:
        out["tdm_h%d" % h] = tdm[h]
    return out


def build_state(src: pd.DataFrame) -> pd.DataFrame:
    """The 16 frozen base columns, causal, returned in the SAME row order as `src`."""
    missing = [c for c in REQUIRED if c not in src.columns]
    if missing:
        raise ValueError("the NBA tick corpus is missing %s" % missing)
    frame = src.sort_values(["game", "ts"], kind="stable")
    group = frame.groupby("game", sort=False)
    margin = frame["margin"].astype(float)
    rem = frame["rem"].astype(float)
    elapsed = frame["elapsed"].astype(float).clip(lower=MIN_ELAPSED)
    period = frame["period"].to_numpy()
    out = pd.DataFrame(index=frame.index)
    out["margin"], out["rem"] = margin, rem
    for k in DMARGIN_K:
        out["dmargin_k%d" % k] = margin - group["margin"].shift(k).astype(float)
    for name, values in _scan(frame["game"].to_numpy(), margin.to_numpy(),
                              frame["ts"].to_numpy(dtype=float)).items():
        out[name] = values
    out["lead_change_rate"] = out["lead_changes"] / elapsed
    out["pace_total"] = (frame["score_home"] + frame["score_away"]).astype(float) / elapsed
    p1 = out["pace_total"].where(period == 1).groupby(frame["game"].to_numpy()).ffill()
    out["pace_ratio_p1"] = np.where(period > 1,
                                    out["pace_total"] / p1.replace(0.0, np.nan), np.nan)
    out["margin_x_rem"] = margin * rem
    out["margin_over_sqrt_rem"] = margin / np.sqrt(np.clip(rem, 0.0, None) + 1.0)
    return out[list(BASE)].reindex(src.index)


def build_grid(src: pd.DataFrame) -> pd.DataFrame:
    """The 96 transformed columns (16 base x 6 transforms), causal, in `src` row order.

    `ew` is an expanding exponentially-weighted mean over the game's OWN ticks so far and
    `delta_vs_prior` is the change against the previous tick of the same game -- both
    backward-only, so both survive the truncation-invariance probe.
    """
    state = build_state(src)
    frame = state.assign(game=src["game"].to_numpy(), ts=src["ts"].to_numpy())
    frame = frame.sort_values(["game", "ts"], kind="stable")
    group = frame.groupby("game", sort=False)[list(BASE)]
    out = pd.DataFrame(index=frame.index)
    for transform, params in TRANSFORMS:
        if transform == "raw":
            block = frame[list(BASE)]
        elif transform == "ew":
            block = group.ewm(halflife=float(dict(params)["halflife"]),
                              ignore_na=True).mean().reset_index(level=0, drop=True)
        else:
            block = group.diff(1)
        for base in BASE:
            out[column_key(base, transform, params)] = block[base]
    return out.reindex(src.index)


def conditioned(values: pd.Series, period: pd.Series, phase: str) -> pd.Series:
    """The column masked to one phase; phase 5 is ANY overtime period (period >= 5)."""
    array = np.asarray(period)
    keep = array >= 5 if phase == "5" else array == int(phase)
    return values.where(keep)


def enumerate_hypotheses() -> List[Hypothesis]:
    """Every hypothesis of the frozen grid, deduped by `grammar.semantic_hash`.

    Enumeration is CLOSED: it reads no corpus, no disk state and no result, so the count
    is a property of the grammar and cannot move once a screen has been run.
    """
    seen: Dict[str, Hypothesis] = {}
    for base in BASE:
        for transform, params in TRANSFORMS:
            for phase in (None,) + PHASES:
                conditioning = frozenset() if phase is None else frozenset({"phase=%s" % phase})
                hypothesis = Hypothesis(SPORT, base, transform, params, conditioning,
                                        HORIZON, MARKET, FAMILY, True)
                seen.setdefault(semantic_hash(hypothesis), hypothesis)
    return [seen[key] for key in sorted(seen)]


def hypothesis_column(hypothesis: Hypothesis) -> str:
    """The grid column a hypothesis reads before its phase mask is applied."""
    return column_key(hypothesis.feature, hypothesis.transform, hypothesis.params)


def hypothesis_phase(hypothesis: Hypothesis) -> str:
    """The phase this hypothesis is conditioned on, or "" when it is unconditional."""
    for item in sorted(hypothesis.conditioning):
        if item.startswith("phase="):
            return item.split("=", 1)[1]
    return ""


def hypothesis_label(hypothesis: Hypothesis) -> str:
    """A stable ASCII name: <column> or <column>@p<phase>. Used as the sqlite row key."""
    phase = hypothesis_phase(hypothesis)
    return hypothesis_column(hypothesis) + ("@p%s" % phase if phase else "")


def grid_summary() -> Dict[str, object]:
    """The frozen counts, for the family spec and the memo. Reads nothing."""
    hypotheses = enumerate_hypotheses()
    return {"family": FAMILY, "sport": SPORT, "horizon": HORIZON, "market": MARKET,
            "n_base": len(BASE), "n_transforms": len(TRANSFORMS),
            "n_conditionings": 1 + len(PHASES), "n_hypotheses": len(hypotheses),
            "members": list(BASE), "not_enumerated": list(NOT_ENUMERATED),
            "not_supplied": list(NOT_SUPPLIED)}


def main() -> int:
    summary = grid_summary()
    print("frozen NBA in-game grammar: %d base x %d transforms x %d conditionings = %d "
          "hypotheses (deduped by semantic_hash)"
          % (summary["n_base"], summary["n_transforms"], summary["n_conditionings"],
             summary["n_hypotheses"]))
    print("family %s | not enumerated: %s | not supplied: %s"
          % (FAMILY, ", ".join(NOT_ENUMERATED), ", ".join(NOT_SUPPLIED)))
    for hypothesis in enumerate_hypotheses()[:5]:
        print("  %-28s %s" % (hypothesis_label(hypothesis), semantic_hash(hypothesis)[:16]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
