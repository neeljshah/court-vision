"""
Build data/cache/bbref_advanced_extended.parquet from all bbref_advanced_*.json files.

Retains all 22 advanced columns per player-season plus player_id where resolvable.
Keyed on (player_id|player_name, season).
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ── paths ────────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parents[1]
_EXT_DIR = _ROOT / "data" / "external"
_CACHE_DIR = _ROOT / "data" / "cache"
_PLAYERINFO_DIR = _CACHE_DIR / "playerinfo"
_OUT_PATH = _CACHE_DIR / "bbref_advanced_extended.parquet"

# ── columns to keep (win_shares renamed to ws) ───────────────────────────────
_IDENTITY_COLS = ["player_name", "team", "season", "season_year"]
_ADVANCED_COLS: List[Tuple[str, str]] = [
    # (json_key, output_col)
    ("obpm",       "obpm"),
    ("dbpm",       "dbpm"),
    ("bpm",        "bpm"),
    ("vorp",       "vorp"),
    ("ws_per_48",  "ws_per_48"),
    ("win_shares", "ws"),          # rename
    ("ows",        "ows"),
    ("dws",        "dws"),
    ("orb_pct",    "orb_pct"),
    ("drb_pct",    "drb_pct"),
    ("trb_pct",    "trb_pct"),
    ("stl_pct",    "stl_pct"),
    ("blk_pct",    "blk_pct"),
    ("tov_pct",    "tov_pct"),
    ("ast_pct",    "ast_pct"),
    ("per",        "per"),
    ("ftr",        "ftr"),
    ("three_par",  "three_par"),
    ("usg_pct",    "usg_pct"),
    ("ts_pct",     "ts_pct"),
]


# ── name normalisation helpers ────────────────────────────────────────────────
def _unmangle_utf8(s: str) -> str:
    """Reverse the latin-1 / utf-8 mojibake common in cached BBRef JSON."""
    try:
        if s.isascii():
            return s
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def _normalise(s: str) -> str:
    """Lowercase, strip accents, collapse whitespace for fuzzy matching."""
    nfkd = unicodedata.normalize("NFKD", s)
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", ascii_str.lower().strip())


# ── player-id resolution ──────────────────────────────────────────────────────
def _build_name_to_id() -> Dict[str, int]:
    """Read every playerinfo/<id>.json and return {display_name: player_id}.

    Two keys per player:
      - canonical   : DISPLAY_FIRST_LAST
      - normalised  : lowered+stripped+de-accented version of the same
    """
    name_to_id: Dict[str, int] = {}
    if not _PLAYERINFO_DIR.is_dir():
        return name_to_id
    for fpath in _PLAYERINFO_DIR.iterdir():
        if not fpath.suffix == ".json":
            continue
        try:
            raw = json.loads(fpath.read_text(encoding="utf-8"))
            rows = raw.get("common_player_info", [])
            if not rows:
                continue
            info = rows[0] if isinstance(rows, list) else rows
            pid = int(info.get("PERSON_ID", fpath.stem))
            display = str(info.get("DISPLAY_FIRST_LAST", "")).strip()
            if display:
                name_to_id[display] = pid
                name_to_id[_normalise(display)] = pid
        except Exception:
            continue
    return name_to_id


def _resolve_id(name: str, name_to_id: Dict[str, int]) -> Optional[int]:
    """Try exact match then normalised fallback."""
    demangled = _unmangle_utf8(name)
    pid = name_to_id.get(demangled)
    if pid is not None:
        return pid
    return name_to_id.get(_normalise(demangled))


# ── main ──────────────────────────────────────────────────────────────────────
def build_extended() -> pd.DataFrame:
    name_to_id = _build_name_to_id()
    rows: List[dict] = []
    skipped_files: List[str] = []

    for fpath in sorted(_EXT_DIR.glob("bbref_advanced_*.json")):
        try:
            data: list = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  SKIP {fpath.name}: {exc}")
            skipped_files.append(fpath.name)
            continue

        if not isinstance(data, list):
            print(f"  SKIP {fpath.name}: top-level is not a list")
            skipped_files.append(fpath.name)
            continue

        for rec in data:
            raw_name = _unmangle_utf8(str(rec.get("player_name", "")).strip())
            if not raw_name:
                continue

            player_id = _resolve_id(raw_name, name_to_id)
            unresolved = player_id is None

            out: dict = {
                "player_name": raw_name,
                "player_id": float(player_id) if player_id is not None else np.nan,
                "unresolved_name": unresolved,
                "team": str(rec.get("team", "")),
                "season": str(rec.get("season", "")),
                "season_year": rec.get("season_year"),
            }
            for json_key, col in _ADVANCED_COLS:
                raw_val = rec.get(json_key)
                try:
                    out[col] = float(raw_val) if raw_val is not None else np.nan
                except (TypeError, ValueError):
                    out[col] = np.nan

            rows.append(out)

    df = pd.DataFrame(rows)
    return df


def main() -> None:
    df = build_extended()

    if df.empty:
        print("ERROR: no rows extracted — check that data/external/bbref_advanced_*.json exist")
        return

    # ── sort and write ────────────────────────────────────────────────────────
    df.sort_values(["player_name", "season"], inplace=True, ignore_index=True)
    _OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(str(_OUT_PATH), index=False, engine="pyarrow")

    # ── diagnostics ──────────────────────────────────────────────────────────
    total_rows = len(df)
    distinct_ps = df.groupby(["player_name", "season"]).ngroups
    unresolved_n = int(df["unresolved_name"].sum())
    unresolved_pct = 100.0 * unresolved_n / total_rows if total_rows else 0.0

    print(f"Rows written      : {total_rows}")
    print(f"Distinct (player, season): {distinct_ps}")
    print(f"Unresolved names  : {unresolved_n} / {total_rows} ({unresolved_pct:.1f}%)")
    print(f"Output            : {_OUT_PATH}")

    if unresolved_n > 0:
        unresolved_names = (
            df.loc[df["unresolved_name"], "player_name"].unique().tolist()
        )
        sample = unresolved_names[:10]
        print(f"  Sample unresolved (first 10): {sample}")


if __name__ == "__main__":
    main()
