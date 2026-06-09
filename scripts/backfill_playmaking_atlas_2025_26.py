"""backfill_playmaking_atlas_2025_26.py — upsert 2025-26 rows into
atlas_player_playmaking_network.parquet from verified tracking + gamelog.

The atlas builder is orphaned (no script in the repo writes this parquet), so
rookies who debuted in 2025-26 (e.g. Dylan Harper, 1642844) never get a row,
and some existing rows carry bad values (e.g. Castle drive_tov_rate=0.001,
ast_to_tov=1.84 vs true 0.099 / 2.31). player_report._build_playmaking reads
this parquet for the dossier summary AND the high_playmaking archetype tag, so
the gap also mis-classifies creators as "Role Player".

Sources (all already local + verified):
  data/player_tracking_2025-26.parquet      passing + driving tracking
  data/cache/signals/playmaking.parquet     gamelog regular-season A:TO
  data/cache/bbref_advanced_extended.parquet usg_pct / tov_pct

Idempotent: re-running overwrites the (player_id, 2025-26) rows in place.

    python scripts/backfill_playmaking_atlas_2025_26.py
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "cache")
ATLAS = os.path.join(CACHE, "atlas_player_playmaking_network.parquet")
SEASON = "2025-26"
AS_OF = "2026-06-08"
TARGETS = [1642844, 1642264]  # Dylan Harper, Stephon Castle


def main() -> None:
    atlas = pd.read_parquet(ATLAS)
    trk = pd.read_parquet(os.path.join(ROOT, "data", "player_tracking_2025-26.parquet")).set_index("player_id")
    pm = pd.read_parquet(os.path.join(CACHE, "signals", "playmaking.parquet")).set_index("player_id")
    bb = pd.read_parquet(os.path.join(CACHE, "bbref_advanced_extended.parquet"))
    bb = bb[bb.player_id.notna()].copy()
    bb["player_id"] = bb["player_id"].astype(int)
    bb = bb[bb.season == SEASON].set_index("player_id")

    # Reuse an existing 2025-26 row only for the generic _cv_fields slot descriptor.
    cv_template = atlas[atlas.season == SEASON].iloc[0].to_dict().get("_cv_fields")
    # Null skeleton with correct per-column dtype. We rebuild each target row from
    # scratch (deterministic / idempotent) rather than carrying forward whatever is
    # on disk — a previous run of this backfill must not pollute the result.
    null_row = {c: (None if atlas[c].dtype == object else np.nan) for c in atlas.columns}
    null_row["_cv_fields"] = cv_template

    # PBP-derived fields we cannot recompute from tracking. Preserve the genuine
    # values for players who had a real atlas build; leave NULL for true rookies
    # (Harper never had a row). Castle's values captured from the original build.
    PRESERVE = {
        1642264: {  # Stephon Castle — genuine 2026-05-31 PBP fields
            "ast_ratio": 19.1038, "tov_ratio": 11.3671,
            "teammate_feed_proxy": 0.1004, "pnr_bh_poss_fraction": 0.0,
            "iso_poss_per_game": 0.5, "transition_poss_per_game": 1.25,
        },
        1642844: {},  # Dylan Harper — no genuine PBP history; leave NULL
    }

    new_rows = []
    for pid in TARGETS:
        t = trk.loc[pid]
        row = dict(null_row)
        n_games = int(pm.loc[pid, "n_games_gl"]) if pid in pm.index and pd.notna(pm.loc[pid].get("n_games_gl")) else 0
        row.update(PRESERVE.get(pid, {}))
        row.update({
            "player_id": int(pid),
            "season": SEASON,
            # --- passing tracking (ground truth) ---
            "passes_made": float(t.trk_pas_passes_made),
            "passes_received": float(t.trk_pas_passes_received),
            "potential_ast": float(t.trk_pas_potential_ast),
            "ast_pts_created": float(t.trk_pas_ast_points_created),
            "secondary_ast": float(t.trk_pas_secondary_ast),
            "ft_ast": float(t.trk_pas_ft_ast),
            # --- driving tracking (ground truth) ---
            "drive_passes": float(t.trk_drv_passes),
            "drive_ast": float(t.trk_drv_ast),
            "drive_tov_rate": float(t.trk_drv_tov_pct),
            # --- regular-season A:TO from gamelog (corrects stale atlas value) ---
            "ast_to_tov": round(float(pm.loc[pid, "ato_season"]), 4) if pid in pm.index else row.get("ast_to_tov"),
            "value": float(t.trk_pas_potential_ast),
            "n_games": n_games,
            "n": n_games,
            "confidence": "high",
            "as_of": AS_OF,
        })
        # usage from bbref (fraction) where available
        if pid in bb.index and "usg_pct" in bb.columns:
            row["usage_pct"] = round(float(bb.loc[pid, "usg_pct"]) / 100.0, 4)
        new_rows.append(row)

    # Drop the rows we're replacing, append the rebuilt ones, restore col order.
    mask = ~((atlas.player_id.isin(TARGETS)) & (atlas.season == SEASON))
    out = pd.concat([atlas[mask], pd.DataFrame(new_rows)], ignore_index=True)
    out = out[atlas.columns]
    # preserve original dtypes where possible
    for c in atlas.columns:
        try:
            out[c] = out[c].astype(atlas[c].dtype)
        except (TypeError, ValueError):
            pass
    out.to_parquet(ATLAS, index=False)

    print(f"DONE: upserted {len(new_rows)} rows into {os.path.basename(ATLAS)} (season {SEASON})")
    chk = out[(out.player_id.isin(TARGETS)) & (out.season == SEASON)]
    print(chk[["player_id", "passes_made", "potential_ast", "ast_pts_created",
               "ast_to_tov", "drive_tov_rate", "usage_pct", "n_games"]].to_string(index=False))


if __name__ == "__main__":
    main()
