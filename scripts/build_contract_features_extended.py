"""Build extended contract features parquet from data/external/contracts_*.json."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
EXTERNAL_DIR = ROOT / "data" / "external"
PLAYERINFO_DIR = ROOT / "data" / "cache" / "playerinfo"
OUT_PATH = ROOT / "data" / "cache" / "contract_features_extended.parquet"

KNOWN_TYPES = {
    "guaranteed",
    "rookie",
    "non-guaranteed",
    "team option",
    "player option",
}

ONE_HOT_MAP = {
    "contract_type_guaranteed": "guaranteed",
    "contract_type_rookie": "rookie",
    "contract_type_non_guaranteed": "non-guaranteed",
    "contract_type_team_option": "team option",
    "contract_type_player_option": "player option",
}


def _parse_season_year(stem: str) -> int:
    """'contracts_2025-26' -> 2026 (the ending year of the season)."""
    m = re.search(r"(\d{4})-(\d{2})", stem)
    if m:
        prefix = m.group(1)[:2]
        return int(prefix + m.group(2))
    raise ValueError(f"Cannot parse season year from: {stem}")


def _build_player_lookup() -> dict[str, int]:
    """Return {normalized_display_name: player_id} from playerinfo cache."""
    lookup: dict[str, int] = {}
    for p in PLAYERINFO_DIR.glob("*.json"):
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            pid: int = raw["player_id"]
            cpi = raw.get("common_player_info", [])
            if cpi:
                row = cpi[0]
                name: Optional[str] = row.get("DISPLAY_FIRST_LAST")
                if name:
                    lookup[name.strip().lower()] = pid
        except Exception:
            continue
    return lookup


def _one_hot_contract_type(ct: str) -> dict[str, int]:
    ct_norm = ct.strip().lower()
    row: dict[str, int] = {}
    matched_any = False
    for col, val in ONE_HOT_MAP.items():
        flag = 1 if ct_norm == val else 0
        row[col] = flag
        if flag:
            matched_any = True
    row["contract_type_other"] = 0 if matched_any else 1
    return row


def _process_file(path: Path, lookup: dict[str, int]) -> pd.DataFrame:
    season_year = _parse_season_year(path.stem)
    records = json.loads(path.read_text(encoding="utf-8"))

    rows = []
    for rec in records:
        pname: str = rec.get("player_name", "")
        pname_norm = pname.strip().lower()
        player_id = lookup.get(pname_norm)

        yr = rec.get("years_remaining")
        try:
            years_remaining = int(yr) if yr is not None else None
        except (ValueError, TypeError):
            years_remaining = None

        ct_raw: str = rec.get("contract_type", "")
        ct_norm = ct_raw.strip().lower()

        oh = _one_hot_contract_type(ct_norm)

        contract_year_raw = rec.get("contract_year", False)
        contract_year_flag = 1 if contract_year_raw else 0

        expiring_flag = 1 if years_remaining == 1 else 0
        rookie_deal_flag = 1 if ct_norm == "rookie" else 0
        player_option_final_year = 1 if ct_norm == "player option" and years_remaining == 1 else 0
        team_option_final_year = 1 if ct_norm == "team option" and years_remaining == 1 else 0

        row: dict = {
            "player_id": player_id,
            "player_name": pname,
            "team": rec.get("team"),
            "season_year": season_year,
            "current_salary": rec.get("current_salary"),
            "cap_hit": rec.get("cap_hit"),
            "cap_hit_pct": rec.get("cap_hit_pct"),
            "years_remaining": years_remaining,
            "contract_year_flag": contract_year_flag,
            "contract_type": ct_raw,
            **oh,
            "rookie_deal_flag": rookie_deal_flag,
            "player_option_final_year": player_option_final_year,
            "team_option_final_year": team_option_final_year,
            "expiring_flag": expiring_flag,
        }
        rows.append(row)

    return pd.DataFrame(rows)


def main() -> None:
    contract_files = sorted(EXTERNAL_DIR.glob("contracts_*.json"))
    if not contract_files:
        raise FileNotFoundError(f"No contracts_*.json found in {EXTERNAL_DIR}")

    print(f"Found {len(contract_files)} contract file(s): {[f.name for f in contract_files]}")

    lookup = _build_player_lookup()
    print(f"Player lookup built: {len(lookup)} entries")

    frames = [_process_file(f, lookup) for f in contract_files]
    df = pd.concat(frames, ignore_index=True)

    # Deduplicate (keep latest file if same player+season appears twice)
    df = df.drop_duplicates(subset=["player_name", "season_year"], keep="last")

    # Coerce player_id to Int64 (nullable int) so NaN is preserved cleanly
    df["player_id"] = pd.array(df["player_id"], dtype="Int64")

    # ---- Stats ----
    total_rows = len(df)
    distinct_combos = df[["player_name", "season_year"]].drop_duplicates().shape[0]
    distinct_types = sorted(df["contract_type"].str.strip().str.lower().unique().tolist())
    resolved = df["player_id"].notna().sum()
    resolution_rate = resolved / total_rows if total_rows else 0.0

    print(f"Rowcount:                    {total_rows}")
    print(f"Distinct (player, season):   {distinct_combos}")
    print(f"Distinct contract_type:      {distinct_types}")
    print(f"Name-resolution rate:        {resolved}/{total_rows} ({resolution_rate:.1%})")

    unexpected = set(distinct_types) - {v.lower() for v in KNOWN_TYPES}
    if unexpected:
        print(f"WARNING — unexpected contract types (bucketed to contract_type_other): {unexpected}")

    # Write parquet
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, OUT_PATH, compression="snappy")
    print(f"Written: {OUT_PATH}")


if __name__ == "__main__":
    main()
