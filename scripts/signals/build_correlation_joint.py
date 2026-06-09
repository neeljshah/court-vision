"""Wave 1 builder: per-player JOINT / CORRELATION signals.

Sources: data/nba/gamelog_full_{pid}_{season}.json, data/models/player_archetype_*.json,
         data/models/prop_corr_archetype_*.json, data/cache/on_off_features.parquet

Output: data/cache/signals/correlation_joint.parquet — one row per player_id with:
  own-stat pairwise rho (pts/reb/ast/fg3m/stl/blk/tov pairs),
  archetype-recalibrated rho (split-half validated, refined=True cells),
  per-stat volatility (std-dev, season-aggregate),
  teammate on-off differential.

Leak rule: SEASON-AGGREGATE (all historical games, no shift). Safe for consumer B
  (correlation/SGP pricing) and consumer A (vault scouting). NOT a point-model feature.
Joins: accumulate on player_id only; no game_id int() calls.

  python scripts/signals/build_correlation_joint.py
"""
from __future__ import annotations

import glob
import json
import os
import re
from collections import defaultdict

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NBA_DIR = os.path.join(ROOT, "data", "nba")
MODELS_DIR = os.path.join(ROOT, "data", "models")
OUT_DIR = os.path.join(ROOT, "data", "cache", "signals")
OUT = os.path.join(OUT_DIR, "correlation_joint.parquet")

MIN_GAMES = 20
STAT_PAIRS = [
    ("pts", "reb"), ("pts", "ast"), ("pts", "fg3m"), ("reb", "ast"),
    ("ast", "tov"), ("pts", "stl"), ("pts", "blk"),
]
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]


def _pearsonr(x: list[float], y: list[float]) -> float | None:
    """Pearson r; None when fewer than MIN_GAMES or zero variance."""
    if len(x) < MIN_GAMES:
        return None
    xa, ya = np.array(x, dtype=float), np.array(y, dtype=float)
    mask = np.isfinite(xa) & np.isfinite(ya)
    xa, ya = xa[mask], ya[mask]
    if len(xa) < MIN_GAMES:
        return None
    xm, ym = xa - xa.mean(), ya - ya.mean()
    denom = np.sqrt((xm**2).sum() * (ym**2).sum())
    if denom == 0.0:
        return None
    r = float((xm * ym).sum() / denom)
    return round(r, 4) if np.isfinite(r) else None


def _load_gamelogs() -> dict[str, dict]:
    """Load all gamelog_full_{pid}_{season}.json; skip DNP rows (min<=0).

    Returns {pid_str: {name, games: [{pts,reb,ast,fg3m,stl,blk,tov,game_date}]}}
    """
    pattern = re.compile(r"gamelog_full_(\d+)_[\d-]+\.json$")
    files = glob.glob(os.path.join(NBA_DIR, "gamelog_full_*.json"))
    print(f"[corr] Loading {len(files)} gamelog files...")
    players: dict[str, dict] = defaultdict(lambda: {"name": "", "games": []})

    for fpath in files:
        m = pattern.match(os.path.basename(fpath))
        if not m:
            continue
        pid = m.group(1)
        try:
            rows = json.load(open(fpath, encoding="utf-8"))
            if isinstance(rows, dict):
                rows = list(rows.values())
        except Exception:
            continue

        for row in rows:
            if not isinstance(row, dict):
                continue
            min_val = str(row.get("min", row.get("MIN", "0"))).strip()
            if min_val in ("0", "0:00", "", "None", "null"):
                continue
            try:
                if float(min_val.split(":")[0]) < 1:
                    continue
            except Exception:
                pass

            def _get(*keys: str) -> float:
                for k in keys:
                    v = row.get(k)
                    if v is not None:
                        try:
                            return float(v)
                        except (ValueError, TypeError):
                            pass
                return float("nan")

            if not players[pid]["name"]:
                name = str(row.get("player_name", row.get("PLAYER_NAME", "")))
                if name and name != "nan":
                    players[pid]["name"] = name

            players[pid]["games"].append({
                "pts": _get("pts", "PTS"), "reb": _get("reb", "REB"),
                "ast": _get("ast", "AST"), "fg3m": _get("fg3m", "FG3M"),
                "stl": _get("stl", "STL"), "blk": _get("blk", "BLK"),
                "tov": _get("tov", "TOV"),
            })
    return dict(players)


def _load_arch_maps() -> tuple[dict[int, str], dict[int, str]]:
    """Return (sameplayer_arch_map, teammate_arch_map) as {int(pid): arch_str}."""
    def _load(path: str) -> dict[int, str]:
        if not os.path.exists(path):
            return {}
        try:
            return {int(k): str(v) for k, v in json.load(open(path, encoding="utf-8")).items()}
        except Exception:
            return {}
    return (
        _load(os.path.join(MODELS_DIR, "player_archetype_sameplayer.json")),
        _load(os.path.join(MODELS_DIR, "player_archetype_teammate.json")),
    )


def _load_arch_rho_table() -> dict[tuple[str, str, str], float]:
    """Load archetype-refined sameplayer rho (refined=True cells only).

    Returns {(archetype, stat_a_sorted, stat_b_sorted): rho}.
    """
    path = os.path.join(MODELS_DIR, "prop_corr_archetype_sameplayer.json")
    if not os.path.exists(path):
        return {}
    try:
        data = json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}
    out: dict[tuple[str, str, str], float] = {}
    for arch, cells in data.get("archetypes", {}).items():
        for pair_key, cell in cells.items():
            if not cell.get("refined", False):
                continue
            rho = cell.get("rho")
            if rho is None:
                continue
            parts = pair_key.split("_")
            if len(parts) != 2:
                continue
            sa, sb = sorted(parts)
            out[(arch, sa, sb)] = float(rho)
    return out


def _load_on_off() -> pd.DataFrame:
    """Load on_off_features.parquet; keep latest season per player."""
    path = os.path.join(ROOT, "data", "cache", "on_off_features.parquet")
    if not os.path.exists(path):
        return pd.DataFrame(columns=["player_id", "on_off_diff", "on_off_net_rating_diff"])
    df = pd.read_parquet(path, columns=["player_id", "season", "on_off_diff", "on_off_net_rating_diff"])
    return df.sort_values("season", ascending=False).drop_duplicates("player_id")[
        ["player_id", "on_off_diff", "on_off_net_rating_diff"]
    ]


def build() -> pd.DataFrame:
    """Build one-row-per-player correlation_joint signal frame."""
    player_data = _load_gamelogs()
    sp_arch, tm_arch = _load_arch_maps()
    arch_rho_tbl = _load_arch_rho_table()
    on_off = _load_on_off().set_index("player_id")

    rows = []
    for pid_str, d in player_data.items():
        games = d["games"]
        if len(games) < MIN_GAMES:
            continue
        pid_int = int(pid_str)

        # Build per-stat float arrays from all historical games
        stat_arr: dict[str, list[float]] = {s: [g[s] for g in games] for s in STATS}

        # Own-stat pairwise rho
        own_rhos = {f"rho_{sa}_{sb}": _pearsonr(stat_arr[sa], stat_arr[sb]) for sa, sb in STAT_PAIRS}

        # Archetype-recalibrated rho (refined=True validated cells)
        arch = sp_arch.get(pid_int, "")
        arch_rhos: dict[str, float | None] = {}
        for sa, sb in [("pts", "reb"), ("pts", "ast"), ("pts", "fg3m"), ("reb", "ast")]:
            key = (arch, *sorted([sa, sb]))
            arch_rhos[f"arch_rho_{sa}_{sb}"] = arch_rho_tbl.get(key) if arch else None  # type: ignore[arg-type]

        # Per-stat volatility (std-dev, season-aggregate)
        vol: dict[str, float | None] = {}
        for s in STATS:
            arr = np.array([v for v in stat_arr[s] if np.isfinite(v)], dtype=float)
            vol[f"vol_{s}"] = round(float(arr.std(ddof=1)), 3) if len(arr) >= MIN_GAMES else None

        # Teammate on-off from on_off_features (season-aggregate)
        on_off_diff = on_off_net = None
        if pid_int in on_off.index:
            oo = on_off.loc[pid_int]
            if pd.notna(oo["on_off_diff"]):
                on_off_diff = round(float(oo["on_off_diff"]), 3)
            if pd.notna(oo["on_off_net_rating_diff"]):
                on_off_net = round(float(oo["on_off_net_rating_diff"]), 3)

        rows.append({
            "player_id": pid_int,
            "player_name": d.get("name", ""),
            "archetype_sameplayer": sp_arch.get(pid_int, ""),
            "archetype_teammate": tm_arch.get(pid_int, ""),
            "n_games_corr": len(games),
            **own_rhos, **arch_rhos, **vol,
            "on_off_diff": on_off_diff,
            "on_off_net_rating_diff": on_off_net,
        })

    out = pd.DataFrame(rows)
    assert out.player_id.duplicated().sum() == 0, "Duplicate player_ids — join blowup!"
    out["vol_pts_pctile"] = out["vol_pts"].rank(pct=True, ascending=True, na_option="keep").mul(100).round(0)
    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    out = build()
    out.to_parquet(OUT, index=False)
    print(f"\nDONE: correlation_joint signals -> {OUT}")
    print(f"  rows={len(out)}  distinct players={out.player_id.nunique()}")
    print("\n  Sample rows (3):")
    print(out.head(3).to_string())

    # Sanity: boom/bust scorers by pts volatility
    top_vol = out.nlargest(8, "vol_pts")[
        ["player_id", "player_name", "vol_pts", "vol_pts_pctile",
         "rho_pts_ast", "archetype_sameplayer", "on_off_diff"]
    ]
    print("\n  Highest pts volatility (boom/bust, useful for joint sizing):")
    for r in top_vol.itertuples(index=False):
        print(f"    pid={r.player_id:>10}  {str(r.player_name or ''):24s}  "
              f"vol_pts={r.vol_pts}  pctile={r.vol_pts_pctile:.0f}  "
              f"rho_pts_ast={r.rho_pts_ast}  arch={r.archetype_sameplayer}  on_off={r.on_off_diff}")

    # Sanity: highest arch-refined pts/fg3m rho
    arch_sample = out[out["arch_rho_pts_fg3m"].notna()].nlargest(5, "arch_rho_pts_fg3m")[
        ["player_id", "player_name", "archetype_sameplayer", "arch_rho_pts_fg3m", "rho_pts_fg3m"]
    ]
    print("\n  Highest arch-refined pts/fg3m rho (3-heavy players):")
    for r in arch_sample.itertuples(index=False):
        print(f"    pid={r.player_id:>10}  {str(r.player_name or ''):24s}  "
              f"arch_rho={r.arch_rho_pts_fg3m}  raw_rho={r.rho_pts_fg3m}  arch={r.archetype_sameplayer}")


if __name__ == "__main__":
    main()
