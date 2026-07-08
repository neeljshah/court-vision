"""domains.tennis.serve_return_interaction -- serve-tier x return-tier
matchup outcome tally, plus surface split and a rank-controlled check.

Buckets each qualifying player-season-tour (serve_return_profiles, floor
>=20 matches) into Big/Normal SERVE tier and Elite/Normal RETURN tier
(median split within tour+season), then -- for every REAL match -- builds
TWO perspective rows (each player's own serve tier vs the OPPONENT's return
tier) and tallies "does this player win the match" by that pairing
(floor >=100 matches/cell): Big-serve-vs-Elite-return, Big-vs-Normal,
Normal-vs-Elite, Normal-vs-Normal.

SURFACE SPLIT: same 4-cell tally repeated within Hard/Clay/Grass (matches.
parquet's own `surface` column) -- reported honestly if a surface x cell
combination falls below the floor (thin cells are common on Grass, the
smallest surface population).

BEYOND-RANK CHECK: matches.parquet carries p1_rank/p2_rank (ATP/WTA
ranking AT match time) -- a real, joinless strength reference, no need to
invent one. Restricting to "close-rank" matches (both players' season rank
tercile equal) and re-tallying the pairing answers whether serve/return-tier
pairing adds anything beyond the players simply being unevenly ranked.

Also builds the ONE claims-ready derived parquet consumed by
domains/tennis/claims_grid.py's tennis_serve_return_matchup_claims family.

NETWORK: zero. DESCRIPTIVE ONLY -- no market/$ edge claimed.

CLI: python -m domains.tennis.serve_return_interaction
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.tennis.serve_return_profiles import build_profiles  # noqa: E402

_ATP_MATCHES = _REPO / "data/domains/tennis/matches.parquet"
_WTA_MATCHES = _REPO / "data/domains/tennis/wta_matches.parquet"
_PAIRING_OUT = _REPO / "data/domains/tennis/serve_return_matchup_pairing.parquet"

MIN_CELL_MATCHES = 100


def _tier_lookup(profiles: pd.DataFrame) -> pd.DataFrame:
    """Median-split serve/return strength WITHIN (tour, season); add a rank-
    based strength tercile is done later (rank lives on matches, not here)."""
    p = profiles.copy()
    grp = p.groupby(["tour", "season"])
    serve_med = grp["serve_strength"].transform("median")
    return_med = grp["return_strength"].transform("median")
    p["serve_tier"] = (p["serve_strength"] >= serve_med).map({True: "Big", False: "Normal"})
    p["return_tier"] = (p["return_strength"] >= return_med).map({True: "Elite", False: "Normal"})
    return p


def _matches_with_tiers(tiers: pd.DataFrame) -> pd.DataFrame:
    """Load ATP+WTA matches, attach each of p1/p2's own serve_tier and the
    OPPONENT's return_tier (per that player-season-tour), plus rank tercile.
    Returns one row per (match, perspective) -- 2 rows/match."""
    key = tiers.set_index(["player_id", "season", "tour"])
    frames = []
    for tour, path in (("ATP", _ATP_MATCHES), ("WTA", _WTA_MATCHES)):
        m = pd.read_parquet(path).copy()
        m["season"] = pd.to_datetime(m["date"]).dt.year
        m["tour"] = tour
        for me, opp in (("p1", "p2"), ("p2", "p1")):
            idx_me = pd.MultiIndex.from_arrays([m[f"{me}_id"], m["season"], m["tour"]])
            idx_opp = pd.MultiIndex.from_arrays([m[f"{opp}_id"], m["season"], m["tour"]])
            self_serve = idx_me.map(key["serve_tier"])
            opp_return = idx_opp.map(key["return_tier"])
            self_rank = m[f"{me}_rank"]
            self_won = (m["winner"] == (1 if me == "p1" else 2)).astype(int)
            frames.append(pd.DataFrame({
                "event_id": m["event_id"], "surface": m["surface"],
                "self_serve_tier": self_serve, "opp_return_tier": opp_return,
                "self_rank": self_rank, "self_won": self_won,
            }))
    out = pd.concat(frames, ignore_index=True)
    return out.dropna(subset=["self_serve_tier", "opp_return_tier"])


def _tally_cells(df: pd.DataFrame) -> pd.DataFrame:
    grp = df.groupby(["self_serve_tier", "opp_return_tier"])
    out = pd.DataFrame({"n": grp.size(), "self_win_rate": grp["self_won"].mean()}).reset_index()
    return out.sort_values("n", ascending=False)


def build_report() -> dict:
    profiles = build_profiles()
    tiers = _tier_lookup(profiles)
    rows = _matches_with_tiers(tiers)

    overall = _tally_cells(rows)
    by_surface = {
        surf: _tally_cells(rows[rows["surface"] == surf])
        for surf in ("Hard", "Clay", "Grass")
    }

    rows_ranked = rows.dropna(subset=["self_rank"]).copy()
    rows_ranked["rank_tercile"] = pd.qcut(
        rows_ranked["self_rank"], 3, labels=["Top", "Mid", "Bottom"], duplicates="drop")
    close_rank = rows_ranked  # cell tallies computed per tercile band below
    controlled = _tally_cells(close_rank[close_rank["rank_tercile"] == "Mid"])

    return {
        "profiles": profiles, "overall": overall, "by_surface": by_surface,
        "controlled_mid_rank": controlled, "n_rows_total": len(rows),
    }


def build_pairing_claims_source(out_path: Path = _PAIRING_OUT) -> Path:
    """Write the ONE derived parquet the claims_grid family reads: one row
    per (match, perspective) with pairing_key ('Big_vs_Elite' etc.), a
    unique row_id, and self_win outcome -- mirrors soccer's
    style_matchup_pairing.parquet precedent."""
    profiles = build_profiles()
    tiers = _tier_lookup(profiles)
    rows = _matches_with_tiers(tiers).reset_index(drop=True)
    out = pd.DataFrame({
        "row_id": rows["event_id"].astype(str) + "_" + rows.index.astype(str),
        "pairing_key": rows["self_serve_tier"] + "_vs_" + rows["opp_return_tier"],
        "self_win": rows["self_won"],
    })
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(out, preserve_index=False), out_path)
    return out_path


def main() -> int:
    report = build_report()
    print(f"player-season-tour profiles: {len(report['profiles'])}  perspective-rows: {report['n_rows_total']}")
    print("\n--- SERVE-TIER vs OPPONENT RETURN-TIER pairing (self_win_rate, floor n>=100) ---")
    print(report["overall"].to_string(index=False))
    for surf, table in report["by_surface"].items():
        print(f"\n--- surface={surf} ---")
        print(table.to_string(index=False))
    print("\n--- MID-RANK-TERCILE-ONLY (rank-controlled) pairing ---")
    print(report["controlled_mid_rank"].to_string(index=False))

    ok = report["overall"][report["overall"]["n"] >= MIN_CELL_MATCHES]
    spread = (ok["self_win_rate"].max() - ok["self_win_rate"].min()) if len(ok) else float("nan")
    ctrl = report["controlled_mid_rank"][report["controlled_mid_rank"]["n"] >= MIN_CELL_MATCHES]
    ctrl_spread = (ctrl["self_win_rate"].max() - ctrl["self_win_rate"].min()) if len(ctrl) else float("nan")
    print(f"\nfull-population self_win_rate spread across cells (floor-qualified): {spread}")
    print(f"rank-controlled (mid tercile only) spread "
          f"({'floor-qualified' if len(ctrl) else 'THIN, below floor'}): {ctrl_spread}")
    print("HONEST READ: serve/return-tier pairing is scored on whether it still separates win rates\n"
          "once both players sit in the same rank tercile -- descriptive only, no edge claimed either way.")

    out = build_pairing_claims_source()
    print(f"\nwrote claims source -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
