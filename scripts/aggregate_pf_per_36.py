"""aggregate_pf_per_36.py — build per-(player_id, date) ROLLING EXPANDING
PF/36 series, EXCLUDING the target game (cycle 91b, loop 5).

Input:  data/player_pf.parquet  (game_id, player_id, team_abbreviation,
                                 game_date, pf, min)
Output: data/player_pf_per36.parquet (player_id, game_date, season_pf_per_36)

The expanding window per (player_id) is sorted by game_date and uses
shift(1) so the row for game_date d holds the PF/36 ESTIMATE computed
from all that player's PRIOR games strictly before d — zero leakage.

PF/36 formula:  sum(prior_pf) * 36.0 / max(sum(prior_min), 1.0).
First game per player (no prior history) emits NaN — callers should fall
back to a league-average default if needed.

Also exposes a tiny helper function used directly by prop_pergame:
    build_pf_per36_lookup() -> Dict[(int, str), float]
"""
from __future__ import annotations

import os
import sys
from typing import Dict, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_IN_PATH = os.path.join(PROJECT_DIR, "data", "player_pf.parquet")
_OUT_PATH = os.path.join(PROJECT_DIR, "data", "player_pf_per36.parquet")


def compute_pf_per36(df):
    """Compute (player_id, game_date) -> season_pf_per_36 from a PF DataFrame.

    Returns a DataFrame with columns: player_id, game_date, season_pf_per_36.
    Uses pandas expanding+shift(1) so the value attached to each game is
    derived ONLY from that player's strictly-prior games.
    """
    import pandas as pd  # noqa: PLC0415

    df = df.copy()
    df["game_date"] = df["game_date"].astype(str)
    df = df[df["game_date"] != ""]
    df = df.sort_values(["player_id", "game_date"]).reset_index(drop=True)

    # Cumulative PF and MIN per player, shifted by 1 so row d sees only
    # rows strictly before d.
    cum_pf  = df.groupby("player_id")["pf"].cumsum().shift(1)
    cum_min = df.groupby("player_id")["min"].cumsum().shift(1)
    # Mask shift(1) carry-over from a different player_id (first row per pid).
    first_mask = df.groupby("player_id").cumcount() == 0
    cum_pf  = cum_pf.where(~first_mask)
    cum_min = cum_min.where(~first_mask)

    pf_per_36 = (cum_pf * 36.0) / cum_min.replace(0.0, float("nan"))

    out = pd.DataFrame({
        "player_id": df["player_id"].astype(int),
        "game_date": df["game_date"].astype(str),
        "season_pf_per_36": pf_per_36.astype(float),
    })
    return out


def build_pf_per36_lookup(parquet_path: str = _OUT_PATH) -> Dict[Tuple[int, str], float]:
    """Load the per-36 parquet into a (player_id, game_date_iso) -> float lookup.

    Returns an empty dict when the parquet is absent or pandas import fails.
    Never raises.
    """
    if not os.path.exists(parquet_path):
        return {}
    try:
        import pandas as pd  # noqa: PLC0415
        df = pd.read_parquet(parquet_path)
    except Exception:
        return {}
    out: Dict[Tuple[int, str], float] = {}
    for _, r in df.iterrows():
        try:
            pid = int(r["player_id"])
        except (TypeError, ValueError, KeyError):
            continue
        v = r.get("season_pf_per_36")
        try:
            v_f = float(v)
        except (TypeError, ValueError):
            continue
        if v_f != v_f:  # NaN
            continue
        out[(pid, str(r["game_date"]))] = v_f
    return out


def main():
    import pandas as pd  # noqa: PLC0415
    if not os.path.exists(_IN_PATH):
        print(f"[pf36] missing input: {_IN_PATH}")
        sys.exit(1)
    df = pd.read_parquet(_IN_PATH)
    print(f"[pf36] read {len(df)} PF rows; "
          f"unique players: {df['player_id'].nunique()}")
    out = compute_pf_per36(df)
    non_null = out["season_pf_per_36"].notna().sum()
    print(f"[pf36] computed {len(out)} rows; "
          f"{non_null} with prior history (rest are first-game NaNs)")
    out.to_parquet(_OUT_PATH, index=False)
    print(f"[pf36] wrote {_OUT_PATH}")


if __name__ == "__main__":
    main()
