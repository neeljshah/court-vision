"""domains.tennis.pregame_features -- leak-free walk-forward pregame feature builder.

Streams matches in pinned chronological order and, for each match, records
STRICTLY-PRIOR (leak-free) candidate features that might deepen the Elo prior:

  recent_form_diff : (p1 last-N win-rate) - (p2 last-N win-rate)  [signed, [-1,1]]
  h2h_diff         : signed prior head-to-head margin between the two players,
                     shrunk: (w1 - w2) / (w1 + w2 + 2)            [signed, (-1,1)]
  rest_diff        : log1p(p1 days-rest) - log1p(p2 days-rest)    [signed]
  fatigue_diff     : (p2 last-3d games) - (p1 last-3d games)      [signed; +favors p1]

All features are computed from matches with date STRICTLY BEFORE the current row,
so they are leak-free by construction (mirrors the Elo as-of contract). The Elo
columns themselves come from elo_walkforward.walk_forward_elo and are joined here.

PRIVATE: F5-clean -- stdlib + numpy/pandas + domains.tennis.* only. No edge claim;
features are gated vs plain Elo on OOS calibration (see pregame_feature_gate.py).
Sackmann data CC BY-NC-SA -- private research only.
"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Optional

import numpy as np
import pandas as pd

from domains.tennis.elo_core import _is_walkover, _sorted
from domains.tennis.elo_walkforward import walk_forward_elo

RECENT_N: int = 10          # window for recent-form win-rate
FATIGUE_DAYS: int = 3       # lookback days for short-term fatigue


def _games_in_score(score: object) -> int:
    """Approx games played in a match from its score string (fatigue proxy)."""
    if not isinstance(score, str) or not score.strip():
        return 0
    total = 0
    for tok in score.split():
        for half in tok.split("-"):
            digits = "".join(ch for ch in half if ch.isdigit())
            if digits:
                try:
                    total += int(digits[:2])
                except ValueError:
                    pass
    return total


def build_features(matches_df: pd.DataFrame) -> pd.DataFrame:
    """Return ``walk_forward_elo`` output + leak-free pregame feature columns.

    Added columns (all signed so + favors p1, matching ``win_prob_p1``):
      recent_form_diff, h2h_diff, rest_diff, fatigue_diff.

    Each is computed from STRICTLY-PRIOR matches only. The current match never
    contributes to its own features.
    """
    wf = walk_forward_elo(matches_df)          # already _sorted + leak-free Elo
    df = wf.reset_index(drop=True)
    dates = pd.to_datetime(df["date"])

    recent: dict[int, deque] = defaultdict(lambda: deque(maxlen=RECENT_N))
    h2h: dict[tuple[int, int], list[int]] = defaultdict(lambda: [0, 0])  # (lo,hi)->[lo_wins,hi_wins]
    last_date: dict[int, pd.Timestamp] = {}
    recent_games: dict[int, deque] = defaultdict(deque)  # (date, games) tuples

    rf, hh, rd, fd = [], [], [], []

    for i in range(len(df)):
        p1 = int(df["p1_id"].iloc[i]); p2 = int(df["p2_id"].iloc[i])
        d = dates.iloc[i]
        score = df["score"].iloc[i] if "score" in df.columns else ""
        winner = int(df["winner"].iloc[i])

        # ---- recent form (win-rate over last RECENT_N) ----
        f1 = float(np.mean(recent[p1])) if recent[p1] else 0.5
        f2 = float(np.mean(recent[p2])) if recent[p2] else 0.5
        rf.append(f1 - f2)

        # ---- head-to-head (shrunk signed margin, ordered key) ----
        lo, hi = (p1, p2) if p1 < p2 else (p2, p1)
        w_lo, w_hi = h2h[(lo, hi)]
        # express as p1 - p2 margin
        w1, w2 = (w_lo, w_hi) if p1 == lo else (w_hi, w_lo)
        hh.append((w1 - w2) / (w1 + w2 + 2.0))

        # ---- rest (days since last match) ----
        r1 = (d - last_date[p1]).days if p1 in last_date else 14
        r2 = (d - last_date[p2]).days if p2 in last_date else 14
        rd.append(float(np.log1p(max(r1, 0)) - np.log1p(max(r2, 0))))

        # ---- fatigue (games played in last FATIGUE_DAYS) ----
        def _recent_games(pid: int) -> int:
            dq = recent_games[pid]
            while dq and (d - dq[0][0]).days > FATIGUE_DAYS:
                dq.popleft()
            return sum(g for _, g in dq)
        g1 = _recent_games(p1); g2 = _recent_games(p2)
        fd.append(float(g2 - g1))  # + favors p1 (p2 more tired)

        # ---- UPDATE state (post-match) ----
        if not _is_walkover(score):
            recent[p1].append(1 if winner == 1 else 0)
            recent[p2].append(1 if winner == 2 else 0)
            if p1 == lo:
                h2h[(lo, hi)][0] += 1 if winner == 1 else 0
                h2h[(lo, hi)][1] += 1 if winner == 2 else 0
            else:
                h2h[(lo, hi)][0] += 1 if winner == 2 else 0
                h2h[(lo, hi)][1] += 1 if winner == 1 else 0
            gms = _games_in_score(score)
            recent_games[p1].append((d, gms)); recent_games[p2].append((d, gms))
        last_date[p1] = d; last_date[p2] = d

    df["recent_form_diff"] = rf
    df["h2h_diff"] = hh
    df["rest_diff"] = rd
    df["fatigue_diff"] = fd
    return df


def elo_logit(df: pd.DataFrame, eps: float = 1e-9) -> np.ndarray:
    """Return the Elo win-prob logit column as a numpy array (clipped)."""
    p = np.clip(df["win_prob_p1"].to_numpy(dtype=float), eps, 1.0 - eps)
    return np.log(p / (1.0 - p))


FEATURE_COLS: tuple[str, ...] = (
    "recent_form_diff", "h2h_diff", "rest_diff", "fatigue_diff",
)
