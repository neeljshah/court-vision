"""scripts.platformkit.omni.replay_harness -- replay(date, sport) v0.

Materializes the decision context as-of a past date and grades it: for every
game ON ``date`` in a sport's corpus, walk the REAL production Elo rating
(``domains.<sport>.ratings.replay``) through strictly-PRIOR games only, predict
the moneyline win probability with that sport's own ``_p_home`` (never a
reimplementation), grade vs the realized outcome (Brier) and -- where a
captured closing line exists -- vs the devigged close via
``scripts.platformkit.grade_paper_close`` (missing close = None, never
fabricated).

Leak-free by construction: ``ratings.replay(games, until=date)`` processes only
rows with ``date < until`` (see domains/<sport>/ratings.py docstring).

v0 scope: moneyline only (Elo has no totals distribution) -- CRPS/totals grading
is a follow-up, not implemented here.

Output: one row per (game, market) written atomically to
``data/omni/replay/<sport>/<date>.parquet`` (tmp + os.replace). Deterministic:
rows sorted by game_id before write, so two runs on the same date are
frame-identical.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII; never
claims an edge (Brier/CRPS are calibration, not $).

CLI: python -m scripts.platformkit.omni.replay_harness --date 2026-04-08 --sport nba
Tests: python -m pytest tests/platformkit/test_omni_replay_harness.py -q
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PIPELINE_VERSION = "omni-replay-v0"
_MARKET = "moneyline"

DateLike = Union[str, dt.date, dt.datetime]


def _to_date(d: DateLike) -> dt.date:
    if isinstance(d, dt.datetime):
        return d.date()
    if isinstance(d, dt.date):
        return d
    return pd.to_datetime(str(d)).date()


# ---------------------------------------------------------------------------
# Per-sport corpus loaders + rating adapters (thin: real domains modules only)
# ---------------------------------------------------------------------------

def _load_games_nba() -> pd.DataFrame:
    from domains.basketball_nba.adapter import _season_to_int
    df = pd.read_parquet(_REPO_ROOT / "data/domains/basketball_nba/games.parquet")
    df = df.copy()
    df["season"] = df["season"].apply(_season_to_int)
    return df


def _load_games_mlb() -> pd.DataFrame:
    paths = ["data/domains/mlb/games.parquet", "data/domains/mlb/games_current.parquet"]
    frames = [pd.read_parquet(_REPO_ROOT / p) for p in paths if (_REPO_ROOT / p).exists()]
    df = pd.concat(frames, ignore_index=True)
    return df.drop_duplicates(subset=["event_id"], keep="last")


_SPORT_CFG: Dict[str, Dict[str, Any]] = {
    "nba": {"loader": _load_games_nba, "id_col": "game_id", "win_col": "home_win",
            "close_sport": "nba"},
    "mlb": {"loader": _load_games_mlb, "id_col": "event_id", "win_col": "target_home_win",
            "close_sport": "mlb"},
}


def _p_home_fn(sport: str):
    """Import the sport's OWN leak-free win-prob formula. Never reimplemented."""
    if sport == "nba":
        from domains.basketball_nba.ratings import _p_home
        from domains.basketball_nba.elo_config import ELO_MEAN
    elif sport == "mlb":
        from domains.mlb.ratings import _p_home
        from domains.mlb.config import ELO_MEAN
    else:
        raise ValueError(f"unwired sport: {sport!r}")
    return _p_home, ELO_MEAN


def _build_state(sport: str, games: pd.DataFrame, until: dt.date):
    """Walk the sport's real ratings.replay(until=until) -- the leak-free seed."""
    if sport == "nba":
        from domains.basketball_nba.ratings import replay as _replay
    elif sport == "mlb":
        from domains.mlb.ratings import replay as _replay
    else:
        raise ValueError(f"unwired sport: {sport!r}")
    return _replay(games, until=until)


# ---------------------------------------------------------------------------
# Close-vs-market (best-effort; missing close = None, never fabricated)
# ---------------------------------------------------------------------------

def _devig_home_prob(home_dec: float, away_dec: float) -> Optional[float]:
    """Proportional (multiplicative) devig -- adequate for a v0 close reference."""
    if home_dec <= 1.0 or away_dec <= 1.0:
        return None
    ih, ia = 1.0 / home_dec, 1.0 / away_dec
    tot = ih + ia
    return (ih / tot) if tot > 0 else None


def _close_prob(sport: str, home: str, away: str, date_str: str) -> Optional[float]:
    """Best-effort devigged home win prob from the captured close, else None.

    Routes through the existing resolver (scripts.platformkit.grade_paper_close
    .close_from_store) rather than a new direct join -- this call degrades to
    None on any lookup miss (unmapped team-name form, no captured line for that
    date), which is the module's own documented, non-fabricating contract.
    """
    try:
        from scripts.platformkit.grade_paper_close import close_from_store
    except Exception:  # noqa: BLE001
        return None
    bet = {"sport": sport, "home": home, "away": away,
           "matchup": f"{away}@{home}", "game_date": date_str}
    try:
        res = close_from_store(bet)
    except Exception:  # noqa: BLE001
        return None
    if res is None:
        return None
    home_dec, away_dec, _is_true, _bh, _ba = res
    return _devig_home_prob(home_dec, away_dec)


# ---------------------------------------------------------------------------
# Core replay
# ---------------------------------------------------------------------------

def replay(date: DateLike, sport: str, *, write: bool = True,
           out_dir: Optional[Path] = None) -> pd.DataFrame:
    """replay(date, sport) -> graded rows for every game ON date.

    Leak-free: the rating state is built via the sport's own
    ``ratings.replay(games, until=date)`` (strictly-prior games only).
    Deterministic: rows sorted by game_id before return/write.
    """
    sport = sport.strip().lower()
    if sport not in _SPORT_CFG:
        raise ValueError(f"unwired sport {sport!r}; have {list(_SPORT_CFG)}")
    d = _to_date(date)
    cfg = _SPORT_CFG[sport]
    games = cfg["loader"]()
    games["_d"] = pd.to_datetime(games["date"]).dt.date
    on_date = games[games["_d"] == d]

    state = _build_state(sport, games, until=d)
    p_home, elo_mean = _p_home_fn(sport)
    replayed_at = dt.datetime.now(dt.timezone.utc).isoformat()

    rows: List[Dict[str, Any]] = []
    for _, r in on_date.iterrows():
        home, away = str(r["home_team"]), str(r["away_team"])
        eh = state.elo.get(home, elo_mean)
        ea = state.elo.get(away, elo_mean)
        model_p = p_home(eh, ea)
        realized = float(r[cfg["win_col"]])
        brier = (model_p - realized) ** 2
        close_p = _close_prob(cfg["close_sport"], home, away, d.isoformat())
        rows.append({
            "sport": sport, "date": d.isoformat(), "game_id": str(r[cfg["id_col"]]),
            "market": _MARKET, "model_prob_or_value": model_p,
            "close_value_or_None": close_p, "realized": realized,
            "brier_or_crps": brier, "pipeline_version": _PIPELINE_VERSION,
            "replayed_at": replayed_at,
        })

    out = pd.DataFrame(rows, columns=[
        "sport", "date", "game_id", "market", "model_prob_or_value",
        "close_value_or_None", "realized", "brier_or_crps",
        "pipeline_version", "replayed_at",
    ]).sort_values("game_id", kind="mergesort").reset_index(drop=True)

    if write:
        _write_atomic(out, _out_path(sport, d, out_dir))
    return out


def _out_path(sport: str, d: dt.date, out_dir: Optional[Path]) -> Path:
    root = out_dir or (_REPO_ROOT / "data" / "omni" / "replay")
    return Path(root) / sport / f"{d.isoformat()}.parquet"


def _write_atomic(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--sport", required=True)
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args(argv)
    df = replay(args.date, args.sport, write=not args.no_write)
    print(f"[{args.sport}] {args.date}: {len(df)} rows, "
          f"mean_brier={df['brier_or_crps'].mean() if len(df) else float('nan')}, "
          f"n_with_close={int(df['close_value_or_None'].notna().sum())}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
