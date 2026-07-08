"""domains.soccer.style_interaction -- style-tier x style-tier outcome tally.

Buckets each qualifying team-season (style_fingerprints.build_fingerprints,
floor >=15 matches) into HIGH/LOW tiers on two style dimensions, then tallies
match-outcome distributions by TIER PAIRING (floor >=100 matches/cell):

  possession tier -- shot_share median-split within season (proxy for
    territorial dominance; this corpus has no true possession column, see
    style_fingerprints.py docstring).
  press tier -- (fouls_committed_pm + cards_pm) median-split within season,
    a plausible on-disk proxy for pressing/aggression intensity.

BEYOND-STRENGTH CHECK: ppg (points-per-game) tercile within season is a
STRENGTH control, independent of the style dims. Restricting to matches
where home and away sit in the SAME strength tercile ("evenly matched") and
re-tallying the possession-tier pairing answers the task's honest question --
does style pairing carry signal beyond strength, or does it just proxy for
"the stronger team also tends to have X style"? Reported with actual n per
cell; a thin cell is reported thin, never padded.

Also builds the ONE claims-ready derived parquet (possession-tier pairing,
one row per match) consumed by claims_grid.py's soccer_style_matchup_claims
family -- same derived-artifact-then-grid pattern as
domains/soccer/ingest_referee_card_profiles.py.

NETWORK: zero. DESCRIPTIVE ONLY -- no market/$ edge claimed.

CLI: python -m domains.soccer.style_interaction
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

from domains.soccer.style_fingerprints import build_fingerprints  # noqa: E402

_MATCHES = _REPO / "data/domains/soccer/matches.parquet"
_PAIRING_OUT = _REPO / "data/domains/soccer/style_matchup_pairing.parquet"

MIN_CELL_MATCHES = 100


def _tier_lookup(fp: pd.DataFrame, dim_cols: list[str]) -> pd.DataFrame:
    """Median-split each dim WITHIN season; return fp with <dim>_tier columns
    (values 'High'/'Low') plus a ppg 'strength_tier' (season tercile)."""
    fp = fp.copy()
    for col, tier_name in dim_cols:
        med = fp.groupby("season")[col].transform("median")
        fp[tier_name] = (fp[col] >= med).map({True: "High", False: "Low"})
    fp["strength_tier"] = fp.groupby("season")["ppg"].transform(
        lambda s: pd.qcut(s, 3, labels=["Bottom", "Mid", "Top"], duplicates="drop").astype(str)
        if s.nunique() >= 3 else "Mid")
    return fp


def _attach_tiers(matches: pd.DataFrame, fp: pd.DataFrame, tier_col: str) -> pd.DataFrame:
    key = fp.set_index(["team", "season"])[tier_col]
    home_tier = matches.set_index(["home_team", "season"]).index.map(key)
    away_tier = matches.set_index(["away_team", "season"]).index.map(key)
    out = matches.copy()
    out["home_tier"] = home_tier
    out["away_tier"] = away_tier
    return out.dropna(subset=["home_tier", "away_tier"])


def _tally_cells(df: pd.DataFrame) -> pd.DataFrame:
    """Group by (home_tier, away_tier); return n, home/draw/away rate, avg goals."""
    grp = df.groupby(["home_tier", "away_tier"])
    out = pd.DataFrame({
        "n": grp.size(),
        "home_win_rate": grp.apply(lambda g: (g["ftr"] == "H").mean(), include_groups=False),
        "draw_rate": grp.apply(lambda g: (g["ftr"] == "D").mean(), include_groups=False),
        "away_win_rate": grp.apply(lambda g: (g["ftr"] == "A").mean(), include_groups=False),
        "avg_total_goals": grp["total_goals"].mean(),
    }).reset_index()
    return out.sort_values("n", ascending=False)


def build_report() -> dict:
    """Compute possession-tier and press-tier pairing tables plus the
    strength-controlled subset. Returns a dict of DataFrames/metadata for
    main() to print and for callers to inspect."""
    fp = build_fingerprints()
    fp["press_proxy"] = fp["fouls_committed_pm"] + fp["cards_pm"]
    fp = _tier_lookup(fp, [("shot_share", "poss_tier"), ("press_proxy", "press_tier")])
    matches = pd.read_parquet(_MATCHES)

    poss = _attach_tiers(matches, fp, "poss_tier")
    press = _attach_tiers(matches, fp, "press_tier")

    poss_table = _tally_cells(poss)
    press_table = _tally_cells(press)

    # Beyond-strength: restrict to matches where BOTH teams share strength_tier.
    strength_lookup_home = fp.set_index(["team", "season"])["strength_tier"]
    matched = poss.copy()
    matched["home_strength"] = matched.set_index(["home_team", "season"]).index.map(strength_lookup_home)
    matched["away_strength"] = matched.set_index(["away_team", "season"]).index.map(strength_lookup_home)
    evenly_matched = matched[matched["home_strength"] == matched["away_strength"]]
    controlled_table = _tally_cells(evenly_matched)

    return {
        "fingerprints": fp, "poss_table": poss_table, "press_table": press_table,
        "controlled_table": controlled_table, "poss_matches": poss, "n_matches_total": len(matches),
    }


def build_pairing_claims_source(out_path: Path = _PAIRING_OUT) -> Path:
    """Write the ONE derived parquet the claims_grid family reads: one row
    per match with pairing_key (possession-tier pairing, e.g. 'High_vs_Low'),
    a unique row_id, and outcome flags -- mirrors the referee-profile
    derived-parquet precedent (pure count/sum aggregate dims downstream)."""
    fp = build_fingerprints()
    fp = fp.copy()
    med = fp.groupby("season")["shot_share"].transform("median")
    fp["poss_tier"] = (fp["shot_share"] >= med).map({True: "High", False: "Low"})
    matches = pd.read_parquet(_MATCHES)
    tagged = _attach_tiers(matches, fp, "poss_tier")

    out = pd.DataFrame({
        "row_id": tagged["event_id"],
        "pairing_key": tagged["home_tier"] + "_vs_" + tagged["away_tier"],
        "home_win": (tagged["ftr"] == "H").astype(int),
        "draw": (tagged["ftr"] == "D").astype(int),
        "away_win": (tagged["ftr"] == "A").astype(int),
        "total_goals": tagged["total_goals"],
    })
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(out, preserve_index=False), out_path)
    return out_path


def main() -> int:
    report = build_report()
    print(f"team-seasons: {len(report['fingerprints'])}  matches (real): {report['n_matches_total']}")
    print("\n--- POSSESSION-TIER (shot_share proxy) pairing (floor n>=100 noted) ---")
    print(report["poss_table"].to_string(index=False))
    print("\n--- PRESS-TIER (fouls+cards proxy) pairing (floor n>=100 noted) ---")
    print(report["press_table"].to_string(index=False))
    print("\n--- STRENGTH-CONTROLLED (same ppg tercile both sides) possession pairing ---")
    print(report["controlled_table"].to_string(index=False))

    poss_ok = report["poss_table"][report["poss_table"]["n"] >= MIN_CELL_MATCHES]
    spread = (poss_ok["home_win_rate"].max() - poss_ok["home_win_rate"].min()) if len(poss_ok) else float("nan")
    ctrl_ok = report["controlled_table"][report["controlled_table"]["n"] >= MIN_CELL_MATCHES]
    ctrl_spread = (ctrl_ok["home_win_rate"].max() - ctrl_ok["home_win_rate"].min()) if len(ctrl_ok) else float("nan")
    print(f"\nfull-population home_win_rate spread across cells (floor-qualified): {spread:.3f}")
    print(f"strength-controlled home_win_rate spread across cells "
          f"({'floor-qualified' if len(ctrl_ok) else 'THIN, below floor'}): {ctrl_spread}")
    print("HONEST READ: if the controlled spread collapses toward the full-population spread's\n"
          "noise floor, possession-tier pairing is not adding signal beyond team strength on this\n"
          "corpus -- descriptive only, no edge claimed either way.")

    out = build_pairing_claims_source()
    print(f"\nwrote claims source -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
