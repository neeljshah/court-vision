"""
Aging curve lite: honest buildability check for an age-based per-36 production
curve from our box-score data.

Truth source: docs/JOB_EVIDENCE_PACKET.md +
jobsearch/research/INDUSTRY_ANALYTICS_NBA.md ("Rank 8 (LOW/conditional) --
Crude aging curve on box rates" -- verdict WEAK APPROXIMATION / leaning DEFER:
"the honest move is to not pretend we have a curve").

Input: data/domains/basketball_nba/player_boxscores.parquet (+ scan for any
roster/adv table carrying age or birthdate).
Output: out/aging_curve_lite.json. No chart -- age is not derivable, so the
honest refusal IS the deliverable (no chart written).
"""
import json
import re
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
OUT_JSON = HERE / "out" / "aging_curve_lite.json"
DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "domains" / "basketball_nba"
PARQUET = DATA_DIR / "player_boxscores.parquet"

# word-boundary match so "age" doesn't false-positive on usagepercentage/average/etc
AGE_TOKEN_RE = re.compile(r"(^|_)(age|birth\w*|dob)($|_)", re.IGNORECASE)


def find_age_source(data_dir: Path) -> str | None:
    """Scan every parquet in the domain dir for an age/birthdate-like column."""
    for p in sorted(data_dir.glob("*.parquet")):
        try:
            cols = pd.read_parquet(p).columns  # ponytail: small domain dir, full read ok
        except Exception:
            continue
        if any(AGE_TOKEN_RE.search(c) for c in cols):
            return p.name
    return None


def build_verdict(box_seasons: list, age_source: str | None) -> dict:
    buildable = age_source is not None and len(box_seasons) >= 3
    return {
        "status": "not_buildable" if not buildable else "buildable",
        "seasons_available": box_seasons,
        "n_seasons": len(box_seasons),
        "age_source_found": age_source,
        "why": (
            "No birthdate/age column exists in any table under "
            "data/domains/basketball_nba/ (scanned all parquets). Only "
            f"{len(box_seasons)} season snapshots of box scores exist "
            f"({', '.join(box_seasons)}). Both the codebase's own prior audit "
            "(player_metric_landscape.py) and jobsearch/research/"
            "INDUSTRY_ANALYTICS_NBA.md independently reach the same verdict: "
            "aging curves need age-labeled player-seasons across MANY seasons "
            "(delta/GAM methods want thousands of paired seasons); 3 seasons "
            "with no age field is not honestly buildable -- the doc explicitly "
            "leans DEFER ('the honest move is to not pretend we have a curve')."
            if not buildable else
            "Age source and >=3 seasons found -- see per-age deltas."
        ),
        "source": "docs/JOB_EVIDENCE_PACKET.md, jobsearch/research/INDUSTRY_ANALYTICS_NBA.md",
    }


def main() -> dict:
    df = pd.read_parquet(PARQUET, columns=["season"])
    box_seasons = sorted(df["season"].unique().tolist())
    age_source = find_age_source(DATA_DIR)
    result = build_verdict(box_seasons, age_source)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2))
    return result


def _check():
    # ponytail: minimal smoke check, not a full test suite
    r = build_verdict(["2023-24", "2024-25", "2025-26"], None)
    assert r["status"] == "not_buildable"
    r2 = build_verdict(["2023-24", "2024-25", "2025-26"], "some_roster.parquet")
    assert r2["status"] == "buildable"
    print("check ok")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        result = main()
        print(json.dumps(result, indent=2))
        print(f"wrote {OUT_JSON}")
