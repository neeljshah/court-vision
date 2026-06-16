"""tests.fixtures.proof.mlb._gen -- deterministic tiny MLB proof fixture generator.

Produces games.parquet / odds.parquet / pitchers.parquet under this directory with the
SAME filenames + columns the three MLB proofs read (beat_the_close_ml,
beat_the_close_total, ingame_accuracy). ~420 synthetic-but-realistic games across two
seasons with latent team strengths so a leak-free Elo / run-rate model warms up and the
beat-the-close proofs return status='ok' with a FINITE Brier / RMSE gap, and the in-game
proof reconstructs checkpoints.

Deterministic: fixed numpy seed, no wall-clock. Re-run to regenerate identical parquets:
    python -m tests.fixtures.proof.mlb._gen
Keeps each parquet well under 200 KB. NOT a model; only schema + realistic distributions.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_SEED = 20260615
_TEAMS = ["BOS", "NYY", "ARI", "SDG", "ATL", "CUB", "LAD", "SFG",
          "HOU", "TEX", "TBR", "BAL", "CLE", "MIN", "STL", "MIL"]
_SEASONS = (2020, 2021)
_GAMES_PER_SEASON = 210            # 420 total -> tiny parquet, > 60 holdout each proof


def _innings_string(total: int, n_innings: int, rng: np.random.Generator,
                    is_home: bool) -> str:
    """Distribute `total` runs across `n_innings` half-innings; home bottom-9 may be 'x'."""
    if n_innings <= 0:
        n_innings = 9
    per = np.zeros(n_innings, dtype=int)
    for _ in range(total):
        per[rng.integers(0, n_innings)] += 1
    toks = [str(int(v)) for v in per]
    if is_home and len(toks) >= 9:
        # home team often does not bat in the 9th when already ahead -> 'x'
        if rng.random() < 0.5:
            toks[8] = "x"
    return ",".join(toks)


def build() -> None:
    rng = np.random.default_rng(_SEED)
    # latent team strength (runs-scored offset) -> gives the model something to learn
    strength = {t: rng.normal(0.0, 0.6) for t in _TEAMS}

    g_rows, o_rows, p_rows = [], [], []
    for season in _SEASONS:
        # one synthetic "season day index" per game for chronological ordering
        for k in range(_GAMES_PER_SEASON):
            h, a = rng.choice(_TEAMS, size=2, replace=False)
            h, a = str(h), str(a)
            month = 4 + (k * 6) // _GAMES_PER_SEASON          # Apr..Sep spread
            day = 1 + (k % 27)
            date = pd.Timestamp(f"{season}-{month:02d}-{day:02d}")
            game_seq = 1 + int(rng.integers(0, 2))            # occasional doubleheader g2
            event_id = f"{season}{month:02d}{day:02d}-{h}-{a}-{game_seq}"

            # per-game starting-pitcher edge: a real signal the MARKET prices but the
            # pitcher-blind Elo cannot see (so the close ends up sharper -> honest MATCH/BEHIND).
            sp_edge = rng.normal(0.0, 0.55)
            # poisson runs around a 4.5 league mean, tilted by latent strength + sp + small HFA
            lam_h = max(0.5, 4.5 + strength[h] - 0.3 * strength[a] + 0.5 * sp_edge + 0.12)
            lam_a = max(0.5, 4.5 + strength[a] - 0.3 * strength[h] - 0.5 * sp_edge)
            hr = int(rng.poisson(lam_h))
            ar = int(rng.poisson(lam_a))
            if hr == ar:                                      # break ties (no extras logic)
                if rng.random() < 0.5:
                    hr += 1
                else:
                    ar += 1
            home_win = int(hr > ar)
            league = "AL" if _TEAMS.index(h) % 2 == 0 else "NL"

            g_rows.append({
                "event_id": event_id, "date": date, "season": season,
                "home_team": h, "away_team": a, "home_runs": hr, "away_runs": ar,
                "target_home_win": np.int8(home_win), "game_seq": np.int8(game_seq),
                "home_league": league,
            })

            # ---- odds: devigged-ish moneyline that roughly tracks the true win prob ----
            # the market sees BOTH latent strength AND the per-game sp_edge (+ tiny noise),
            # so the devigged close is sharper than the pitcher-blind Elo -> honest verdict.
            true_p_mkt = 1.0 / (1.0 + 10.0 ** (
                -((strength[h] - strength[a]) + sp_edge + 0.18) / 1.2))
            noise = rng.normal(0.0, 0.008)
            p_mkt = float(np.clip(true_p_mkt + noise, 0.10, 0.90))
            vig = 0.024
            imp_h = p_mkt * (1 + vig)
            imp_a = (1 - p_mkt) * (1 + vig)
            ml_h = (-100.0 * imp_h / (1 - imp_h)) if imp_h >= 0.5 else (100.0 * (1 - imp_h) / imp_h)
            ml_a = (-100.0 * imp_a / (1 - imp_a)) if imp_a >= 0.5 else (100.0 * (1 - imp_a) / imp_a)
            # closing total line tracks expected runs + small noise (RMSE comparator)
            closeou = float(np.round((lam_h + lam_a + rng.normal(0.0, 0.4)) * 2) / 2)
            o_rows.append({
                "event_id": event_id, "date": date, "season": season,
                "ml_open_home_am": float(np.round(ml_h)) - 4.0,
                "ml_open_away_am": float(np.round(ml_a)) + 4.0,
                "ml_close_home_am": float(np.round(ml_h)),
                "ml_close_away_am": float(np.round(ml_a)),
                "dec_open_home": np.float32(1.9), "dec_open_away": np.float32(1.9),
                "dec_close_home": np.float32(1.9), "dec_close_away": np.float32(1.9),
                "book": "fixture", "runline": np.float32(np.nan),
                "runline_odds": np.float32(-110.0), "openou": np.float32(closeou),
                "openou_odds": np.float32(-110.0), "closeou": np.float32(closeou),
                "closeou_odds": np.float32(-110.0),
            })

            # ---- pitchers: per-inning line scores summing to the run totals ----
            home_innings = _innings_string(hr, 9, rng, is_home=True)
            away_innings = _innings_string(ar, 9, rng, is_home=False)
            p_rows.append({
                "event_id": event_id, "date": date, "season": season,
                "home_team": h, "away_team": a,
                "home_sp_name": f"{h}-SP", "away_sp_name": f"{a}-SP",
                "home_sp_present": True, "away_sp_present": True,
                "home_innings": home_innings, "away_innings": away_innings,
            })

    games = pd.DataFrame(g_rows)
    odds = pd.DataFrame(o_rows)
    pitchers = pd.DataFrame(p_rows)
    # enforce dtypes that match the real corpus where it matters
    games["home_runs"] = games["home_runs"].astype("int64")
    games["away_runs"] = games["away_runs"].astype("int64")
    games["season"] = games["season"].astype("int64")

    games.to_parquet(_HERE / "games.parquet", index=False)
    odds.to_parquet(_HERE / "odds.parquet", index=False)
    pitchers.to_parquet(_HERE / "pitchers.parquet", index=False)
    print(f"wrote {len(games)} games / {len(odds)} odds / {len(pitchers)} pitchers to {_HERE}")


if __name__ == "__main__":
    build()
