"""S123(c): which arm an NBA in-game screen anchors on.

S92 measured the three NBA in-game arms on identical rows and found the order
market < recal_null < ladder_base by Brier on BOTH tick corpora (0.142877 /
0.144293 / 0.146850 on 661 games; 0.144101 / 0.146843 / 0.153324 on 284).  The
S102 screen anchors on the RAW MARKET (`ingame_screen_nba.load_screen` puts the
market probability in the tier's `p_e4` slot) and its null arm recalibrates it,
so the bar already lands on the gain over the recalibrated line.  This module
lets a future screen say so EXPLICITLY -- and lets it anchor on the ladder BASE
instead, to measure a candidate against the incumbent S84/S92 used.

Nothing here is fit twice: `recal_null` is `s94_nba_early_shrinkage._recal`, the
S94 global recalibration itself, and `ladder_base` is
`nba_mechanism_ladder._fit_predict` on that module's own BASE triple.  Only the
fold rule is restated, and it is `ingame_screen.walk_forward_feature`'s rule
(block-ordered, game-disjoint, purged on the game's LAST tick with a symmetric
`embargo_days` gap), asserted per fold.

DESCRIPTIVE plumbing.  No bar moved (BAR stays `ingame_screen.BAR`), no ledger
row, no charge.  Calibration language only.  ASCII.
Per-file test: python -m pytest tests/platformkit/foundry/test_ingame_screen_nba.py -q
"""
from __future__ import annotations

from typing import Iterator, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.s94_nba_early_shrinkage import _recal, logit
from scripts.platformkit.foundry.ingame_screen import EMBARGO_DAYS
from scripts.platformkit.ingame.nba_mechanism_ladder import _fit_predict

INCUMBENTS = ("market", "recal_null", "ladder_base")
LADDER_BASE_COLS = ["logit_p0", "margin_s", "z"]
REGULATION_MINUTES = 48.0        # nba_mechanism_ladder.load_corpus' own clock


def ladder_base_columns(rows: pd.DataFrame) -> pd.DataFrame:
    """`nba_mechanism_ladder.load_corpus`' BASE triple, rebuilt from the tick rows.

    logit of the game's FIRST traded price, the signed margin, and
    margin / sqrt(remaining fraction).  `rows.rem` is minutes of a 48-minute game,
    clipped to the ladder's own [1/96, 1] floor.
    """
    first = rows.sort_values("ts", kind="stable").groupby("game")["market"].first()
    rem = np.clip(rows["rem"].to_numpy(dtype=float) / REGULATION_MINUTES, 1.0 / 96.0, 1.0)
    margin = rows["margin"].to_numpy(dtype=float)
    return pd.DataFrame({"logit_p0": logit(rows["game"].map(first).to_numpy(dtype=float)),
                         "margin_s": margin, "z": margin / np.sqrt(rem)}, index=rows.index)


def folds(rows: pd.DataFrame,
          embargo_days: int = EMBARGO_DAYS) -> Iterator[Tuple[pd.DataFrame, pd.DataFrame]]:
    """`walk_forward_feature`'s fold rule, restated for a multi-column anchor fit.

    Blocks in `game_date` order, block 0 train-only; a train game's LAST tick must
    precede the fold's first tick by `embargo_days`.  Game-disjointness and the purge
    are ASSERTED per fold, exactly as the tier asserts them.
    """
    last_ts = rows.groupby("game")["ts"].max()
    blocks = sorted(rows["game_date"].unique())
    for block in blocks[1:]:
        test = rows[rows["game_date"] == block]
        if test.empty:
            continue
        cut = (pd.Timestamp(test["ts"].min()) - pd.Timedelta(days=embargo_days)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")     # same layout as the tick stamps, so `<` is a real order
        train = rows[rows["game"].isin(last_ts.index[last_ts < cut])]
        if train.empty or train["y"].nunique() < 2:
            continue
        assert not (set(train["game"]) & set(test["game"])), "fold not game-disjoint"
        assert train["ts"].max() < test["ts"].min(), "purge violated: train outlives the fold"
        yield train, test


def anchor_series(rows: pd.DataFrame, kind: str,
                  embargo_days: int = EMBARGO_DAYS) -> pd.Series:
    """The incumbent's probability per row.  NaN wherever no out-of-fold fit exists."""
    if kind == "market":
        return rows["market"].astype(float)
    if kind not in INCUMBENTS:
        raise ValueError("unknown incumbent %r; expected one of %s" % (kind, INCUMBENTS))
    frame = rows if kind == "recal_null" else rows.join(ladder_base_columns(rows))
    out = pd.Series(np.nan, index=rows.index, dtype=float)
    for train, test in folds(frame, embargo_days):
        if kind == "recal_null":
            model = _recal(train.assign(logit_market=logit(train["market"])))
            probability = model.predict_proba(
                logit(test["market"]).reshape(-1, 1))[:, 1]
        else:
            probability = _fit_predict(train.assign(outcome_home_win=train["y"]),
                                       test, LADDER_BASE_COLS)
        out.loc[test.index] = probability
    return out


def apply_incumbent(rows: pd.DataFrame, kind: str,
                    embargo_days: int = EMBARGO_DAYS) -> pd.DataFrame:
    """Put `kind`'s probability in the tier's anchor slot `p_e4`.

    A FITTED anchor exists only out of fold, so the train-only seed block has none and
    those rows are dropped; the caller re-blocks the survivors to keep its fold count.
    Re-blocking cannot leak: every surviving row's anchor was fit on games that ended at
    least `embargo_days` before its own fold, hence before any block it can land in.
    `kind == "market"` returns `rows` UNTOUCHED -- the default screen is byte-identical.
    """
    if kind == "market":
        return rows
    anchor = anchor_series(rows, kind, embargo_days)
    keep = anchor.notna()
    out = rows[keep].copy()
    out["p_e4"] = anchor[keep].to_numpy()
    out["incumbent"] = kind
    return out.reset_index(drop=True)
