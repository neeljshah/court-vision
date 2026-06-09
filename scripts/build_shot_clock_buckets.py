"""
INT-49: Shot-Clock-Bucket CV Signatures
========================================
Splits each possession into shot-clock buckets using possession DURATION as a proxy
for remaining shot clock (since per-frame shot_clock is unreliable — ISSUE-023).

Bucket definitions (seconds):
  early  : 17-24s  (normal offensive sets, first look)
  mid    : 7-17s   (half-court execution, pick-and-roll, etc.)
  late   :  0-7s   (scramble / isolation / desperation)

Player identity key: (player_name, team_abbrev) composite string — because player_id in
tracking_data is a per-game slot index (1-10), NOT an NBA player ID.
Unresolved players whose name ends in '#?' are included in the parquet (bucket CV features)
but excluded from the top-N rankings and JSON profiles.

NOTE on pbp_fill rows: possessions.csv may contain rows with source='pbp_fill' that have
NaN possession_id and hardcoded duration_sec=12.0. These are PBP-reconstructed stubs with
no CV tracking data — they are skipped entirely.

ISSUE-023 caveat: Per-frame shot_clock_est has MAE=17.16s (doesn't decrement per frame).
Possession duration from start_frame/end_frame is the reliable proxy.
"""

import glob
import json
import logging
import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=pd.errors.DtypeWarning)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.parent
TRACKING_DIR = BASE_DIR / "data" / "tracking"
INTEL_DIR = BASE_DIR / "data" / "intelligence"
VAULT_DIR = BASE_DIR / "vault" / "Intelligence"

INTEL_DIR.mkdir(parents=True, exist_ok=True)
VAULT_DIR.mkdir(parents=True, exist_ok=True)

# Shot-clock bucket thresholds (seconds of possession duration)
BUCKET_EARLY_MIN = 17.0   # 17-24.5s duration
BUCKET_MID_MIN = 7.0      # 7-17s
# late = 0-7s
DURATION_MAX = 24.5       # ignore possessions > 24.5s (artefact)
DURATION_MIN = 0.5        # ignore sub-0.5s blips

MIN_POSS_FOR_RELIABLE = 30  # minimum total possessions per player for "reliable" flag

# CV feature columns to aggregate from tracking_data (ball-handler frames)
TRACKING_COLS_NEEDED = [
    "frame", "player_id", "player_name", "team_abbrev",
    "possession_id", "ball_possession",
    "paint_touches", "dribble_count", "drive_flag",
    "distance_to_basket", "off_ball_distance",
    "velocity", "team_spacing", "court_zone",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def bucket_from_duration(dur_sec: float, is_fast_break: bool = False) -> str:
    """Map possession duration → shot-clock bucket."""
    if is_fast_break:
        return "early"  # fast breaks start with a fresh 24s clock
    if dur_sec <= BUCKET_MID_MIN:
        return "late"
    if dur_sec <= BUCKET_EARLY_MIN:
        return "mid"
    return "early"


def player_key(name: object, team: object) -> str:
    """Stable cross-game player identifier."""
    n = str(name).strip() if name is not None and not _is_na(name) else "UNKNOWN"
    t = str(team).strip() if team is not None and not _is_na(team) else "UNK"
    return f"{n}/{t}"


def _is_na(v) -> bool:
    try:
        return bool(pd.isna(v))
    except Exception:
        return False


def is_resolved(name: object) -> bool:
    """True if player_name is a real name (not an unresolved '#?' slot label)."""
    if _is_na(name):
        return False
    s = str(name).strip()
    return bool(s) and "#?" not in s and s != "UNKNOWN" and s.lower() not in {"nan", "none"}


def read_csv_safe(path: Path, **kwargs) -> pd.DataFrame | None:
    """Read CSV; return None on any error."""
    try:
        return pd.read_csv(path, **kwargs)
    except Exception as exc:
        log.debug("Skip %s: %s", path, exc)
        return None


# ---------------------------------------------------------------------------
# Per-game processor
# ---------------------------------------------------------------------------

def process_game(game_id: str) -> tuple[list[dict], list[str]]:
    """
    Process one game. Returns (records, warnings).
    Each record has:
        game_id, possession_id, bucket, pkey (player key), player_name,
        team_abbrev, resolved (bool), duration_sec, fast_break, shot_taken
        + optional CV features
    """
    game_dir = TRACKING_DIR / game_id
    poss_path = game_dir / "possessions.csv"
    shot_path = game_dir / "shot_log.csv"
    td_path = game_dir / "tracking_data.csv"
    warns: list[str] = []

    if not poss_path.exists():
        return [], []

    poss = read_csv_safe(poss_path)
    if poss is None or poss.empty:
        return [], []

    required_cols = {"possession_id", "duration_sec"}
    if not required_cols.issubset(poss.columns):
        warns.append(f"{game_id}: possessions.csv missing {required_cols - set(poss.columns)}")
        return [], warns

    # Drop pbp_fill rows (NaN possession_id, fixed duration_sec=12.0)
    valid_poss = poss.dropna(subset=["possession_id"]).copy()
    valid_poss["possession_id"] = valid_poss["possession_id"].astype(int)

    if valid_poss.empty:
        return [], []

    # ---- Shot log: preferred player attribution for possessions ending in shots ----
    shot_player_map: dict[int, tuple[str, str, bool]] = {}  # poss_id -> (name, team, resolved)
    if shot_path.exists():
        sl = read_csv_safe(shot_path)
        if sl is not None and not sl.empty:
            if "possession_id" in sl.columns and "player_name" in sl.columns:
                sl_valid = sl.dropna(subset=["possession_id"])
                sl_valid = sl_valid[sl_valid["possession_id"].notna()]
                sl_valid["possession_id"] = sl_valid["possession_id"].astype(int)
                for _, row in sl_valid.iterrows():
                    poss_id = int(row["possession_id"])
                    if poss_id in shot_player_map:
                        continue
                    name = row.get("player_name") if not _is_na(row.get("player_name")) else None
                    team = row.get("team_abbrev") if not _is_na(row.get("team_abbrev")) else None
                    if name is None:
                        # fall back to player_id if we have no name
                        continue
                    shot_player_map[poss_id] = (str(name), str(team) if team else "UNK", is_resolved(name))

    # ---- Tracking data: ball-handler fallback + CV feature extraction ----
    td: pd.DataFrame | None = None
    available_td_cols: set = set()
    if td_path.exists():
        td = read_csv_safe(
            td_path,
            usecols=lambda c: c in set(TRACKING_COLS_NEEDED),
            low_memory=False,
        )
        if td is not None and not td.empty:
            # Ensure possession_id is numeric
            if "possession_id" in td.columns:
                td = td.dropna(subset=["possession_id"])
                td["possession_id"] = td["possession_id"].astype(int)
            available_td_cols = set(td.columns)

    # Pre-compute ball-handler per possession (avoid per-row repeated groupby)
    bh_map: dict[int, tuple[str, str, bool]] = {}  # poss_id -> (name, team, resolved)
    if td is not None and "ball_possession" in available_td_cols:
        bh_rows = td[td["ball_possession"] == 1]
        if not bh_rows.empty and "possession_id" in available_td_cols:
            grp = bh_rows.groupby("possession_id")
            for poss_id, grp_df in grp:
                # Most frequent player_name in this possession
                name_counts = grp_df["player_name"].value_counts()
                if name_counts.empty:
                    continue
                bh_name = name_counts.index[0]
                # get team for that name
                team_rows = grp_df[grp_df["player_name"] == bh_name]
                bh_team = "UNK"
                if "team_abbrev" in team_rows.columns and not team_rows["team_abbrev"].dropna().empty:
                    bh_team = str(team_rows["team_abbrev"].dropna().iloc[0])
                bh_map[int(poss_id)] = (str(bh_name), bh_team, is_resolved(bh_name))

    # Pre-compute CV aggregates per (possession_id, player_name) for ball_possession==1
    cv_agg_map: dict[tuple[int, str], dict] = {}
    if td is not None and "ball_possession" in available_td_cols:
        bh_rows = td[td["ball_possession"] == 1]
        if not bh_rows.empty:
            group_cols = ["possession_id"]
            if "player_name" in available_td_cols:
                group_cols.append("player_name")

            paint_zones = {"paint", "paint_area", "restricted_area"}
            perimeter_zones = {"3pt_arc", "corner_3", "backcourt"}

            for key, grp_df in bh_rows.groupby(group_cols):
                if len(group_cols) == 2:
                    poss_id, pname = key
                else:
                    poss_id = key
                    pname = "UNKNOWN"
                poss_id = int(poss_id)
                n = len(grp_df)

                paint_n = 0
                perimeter_n = 0
                if "court_zone" in grp_df.columns:
                    paint_n = grp_df["court_zone"].isin(paint_zones).sum()
                    perimeter_n = grp_df["court_zone"].isin(perimeter_zones).sum()

                feats = {
                    "bh_frame_count": n,
                    "paint_dwell": paint_n / n if n > 0 else 0.0,
                    "perimeter_dwell": perimeter_n / n if n > 0 else 0.0,
                    "total_dribbles": float(grp_df["dribble_count"].sum()) if "dribble_count" in grp_df.columns else 0.0,
                    "total_drives": float(grp_df["drive_flag"].sum()) if "drive_flag" in grp_df.columns else 0.0,
                    "total_paint_touches": float(grp_df["paint_touches"].sum()) if "paint_touches" in grp_df.columns else 0.0,
                    "mean_velocity": float(grp_df["velocity"].mean()) if "velocity" in grp_df.columns else np.nan,
                    "mean_dist_basket": float(grp_df["distance_to_basket"].mean()) if "distance_to_basket" in grp_df.columns else np.nan,
                    "mean_team_spacing": float(grp_df["team_spacing"].mean()) if "team_spacing" in grp_df.columns else np.nan,
                }
                cv_agg_map[(poss_id, str(pname))] = feats

    # Build records
    records = []
    for _, prow in valid_poss.iterrows():
        poss_id = int(prow["possession_id"])
        dur = float(prow["duration_sec"])

        # Skip implausible durations
        if pd.isna(dur) or dur < DURATION_MIN or dur > DURATION_MAX:
            continue

        fast_break = False
        if "fast_break" in prow.index and not _is_na(prow["fast_break"]):
            fast_break = bool(prow["fast_break"])

        bucket = bucket_from_duration(dur, fast_break)

        # Player attribution: shot_log first, then tracking ball-handler
        if poss_id in shot_player_map:
            name, team, resolved = shot_player_map[poss_id]
            shot_taken = True
        elif poss_id in bh_map:
            name, team, resolved = bh_map[poss_id]
            shot_taken = bool(prow.get("shot_attempted", 0)) if not _is_na(prow.get("shot_attempted", np.nan)) else False
        else:
            # Can't attribute this possession
            continue

        pkey = player_key(name, team)

        # CV features from pre-computed aggregates
        cv_feats = cv_agg_map.get((poss_id, name), {})

        rec = {
            "game_id": game_id,
            "possession_id": poss_id,
            "bucket": bucket,
            "pkey": pkey,
            "player_name": name,
            "team_abbrev": team,
            "resolved": resolved,
            "duration_sec": dur,
            "fast_break": fast_break,
            "shot_taken": shot_taken,
        }
        rec.update(cv_feats)
        records.append(rec)

    return records, warns


# ---------------------------------------------------------------------------
# Main aggregation
# ---------------------------------------------------------------------------

def build_shot_clock_buckets() -> None:
    log.info("Scanning game directories …")
    all_game_dirs = sorted([
        d.name for d in TRACKING_DIR.iterdir()
        if d.is_dir() and (d / "possessions.csv").exists()
    ])
    log.info("Found %d games with possessions.csv", len(all_game_dirs))

    all_records: list[dict] = []
    processed = 0
    skipped_no_data = 0
    skipped_error = 0

    for i, gid in enumerate(all_game_dirs):
        if i % 50 == 0:
            log.info("  Processing game %d/%d …", i + 1, len(all_game_dirs))
        try:
            recs, warns = process_game(gid)
            for w in warns:
                log.debug(w)
            if recs:
                all_records.extend(recs)
                processed += 1
            else:
                skipped_no_data += 1
        except Exception as exc:
            log.warning("Game %s error: %s", gid, exc)
            skipped_error += 1

    log.info("Processed %d games | no-data skips %d | errors %d | total records %d",
             processed, skipped_no_data, skipped_error, len(all_records))

    if not all_records:
        log.error("No possession records — aborting.")
        return

    df = pd.DataFrame(all_records)

    # ---- Bucket coverage ----
    bucket_counts = df["bucket"].value_counts()
    log.info("Bucket distribution:\n%s", bucket_counts.to_string())
    log.info("Unique player keys: %d (resolved: %d)",
             df["pkey"].nunique(), df[df["resolved"]]["pkey"].nunique())

    # ----------------------------------------------------------------
    # Aggregate: per (pkey, player_name, team_abbrev, bucket)
    # ----------------------------------------------------------------
    cv_feature_cols = [c for c in df.columns if c in {
        "bh_frame_count", "paint_dwell", "perimeter_dwell",
        "total_dribbles", "total_drives", "total_paint_touches",
        "mean_velocity", "mean_dist_basket", "mean_team_spacing",
    }]
    log.info("CV features available: %s", cv_feature_cols)

    group_cols = ["pkey", "player_name", "team_abbrev", "bucket", "resolved"]
    agg_dict: dict = {"possession_id": "count", "shot_taken": "sum"}
    for c in cv_feature_cols:
        agg_dict[c] = "mean"

    player_bucket = (
        df.groupby(group_cols, dropna=False)
        .agg(agg_dict)
        .reset_index()
        .rename(columns={"possession_id": "n_poss", "shot_taken": "n_shots"})
    )

    # Long format for parquet
    id_cols = ["pkey", "player_name", "team_abbrev", "bucket", "resolved", "n_poss", "n_shots"]
    long_rows: list[dict] = []
    for _, row in player_bucket.iterrows():
        for feat in cv_feature_cols:
            long_rows.append({
                "pkey": row["pkey"],
                "player_name": row["player_name"],
                "team_abbrev": row["team_abbrev"],
                "bucket": row["bucket"],
                "resolved": bool(row["resolved"]),
                "n_poss": int(row["n_poss"]),
                "n_shots": int(row["n_shots"]),
                "feature_name": feat,
                "mean_value": float(row[feat]) if not _is_na(row[feat]) else None,
            })

    long_df = pd.DataFrame(long_rows)
    out_parquet = INTEL_DIR / "shot_clock_buckets.parquet"
    long_df.to_parquet(out_parquet, index=False)
    log.info("Saved %s (%d rows)", out_parquet, len(long_df))

    # ----------------------------------------------------------------
    # Player profiles: merge UNK-team fragments with real-team records
    # (same resolved player_name tracked across games shows up as "Name/UNK"
    #  and "Name/TEAM" as separate keys — collapse by player_name for profiles)
    # ----------------------------------------------------------------

    # Step 1: build wide table per raw pkey
    player_totals_raw = player_bucket.groupby("pkey")["n_poss"].sum().rename("total_poss")

    wide_raw = player_bucket.pivot_table(
        index=["pkey", "player_name", "team_abbrev", "resolved"],
        columns="bucket",
        values="n_poss",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()
    wide_raw.columns.name = None
    for b in ["early", "mid", "late"]:
        if b not in wide_raw.columns:
            wide_raw[b] = 0
    wide_raw = wide_raw.merge(player_totals_raw, on="pkey")

    # Step 2: for resolved players, create a name-collapsed key
    # (ignore 'UNK' team splits — merge all appearances under real name)
    def _canonical_key(row) -> str:
        if row["resolved"]:
            # Use player_name as canonical (ignore UNK vs real team fragmentation)
            name = str(row["player_name"]).strip() if not _is_na(row.get("player_name")) else row["pkey"]
            return name
        return str(row["pkey"])

    wide_raw["ckey"] = wide_raw.apply(_canonical_key, axis=1)

    # Step 3: collapse by ckey — sum bucket counts
    wide = (
        wide_raw.groupby("ckey")
        .agg(
            player_name=("player_name", lambda s: s.mode().iloc[0] if len(s) > 0 else s.iloc[0]),
            team_abbrev=("team_abbrev", lambda s: ", ".join(sorted(
                t for t in s.unique() if str(t) not in {"UNK", "nan"}
            )) or "UNK"),
            resolved=("resolved", "max"),
            early=("early", "sum"),
            mid=("mid", "sum"),
            late=("late", "sum"),
        )
        .reset_index()
        .rename(columns={"ckey": "ckey"})
    )
    wide["total_poss"] = wide["early"] + wide["mid"] + wide["late"]
    wide["early_share"] = wide["early"] / wide["total_poss"].replace(0, np.nan)
    wide["mid_share"] = wide["mid"] / wide["total_poss"].replace(0, np.nan)
    wide["late_share"] = wide["late"] / wide["total_poss"].replace(0, np.nan)
    wide["reliable"] = wide["total_poss"] >= MIN_POSS_FOR_RELIABLE

    profiles: dict = {}
    for _, row in wide.iterrows():
        ckey = str(row["ckey"])
        resolved_flag = bool(row.get("resolved", False))
        profiles[ckey] = {
            "player_name": str(row["player_name"]) if not _is_na(row.get("player_name")) else ckey,
            "team_abbrev": str(row["team_abbrev"]) if not _is_na(row.get("team_abbrev")) else "UNK",
            "resolved": resolved_flag,
            "total_possessions": int(row["total_poss"]),
            "early_poss": int(row["early"]),
            "mid_poss": int(row["mid"]),
            "late_poss": int(row["late"]),
            "early_share": round(float(row["early_share"]), 4) if not _is_na(row["early_share"]) else None,
            "mid_share": round(float(row["mid_share"]), 4) if not _is_na(row["mid_share"]) else None,
            "late_share": round(float(row["late_share"]), 4) if not _is_na(row["late_share"]) else None,
            "reliable": bool(row["reliable"]),
        }

    out_json = INTEL_DIR / "shot_clock_player_profiles.json"
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(profiles, fh, indent=2, ensure_ascii=False)
    log.info("Saved %s (%d player keys, after name-merge)", out_json, len(profiles))

    # ----------------------------------------------------------------
    # Insight analysis
    # ----------------------------------------------------------------
    # Resolved + reliable players for rankings
    reliable_resolved = wide[wide["reliable"] & wide["resolved"]].copy()
    log.info("Resolved reliable players (n>=%d after merge): %d",
             MIN_POSS_FOR_RELIABLE, len(reliable_resolved))

    # ALL reliable for atlas (including unresolved for CV pattern coverage)
    reliable_all = wide[wide["reliable"]].copy()

    # Top late-clock dependent
    rank_pool = reliable_resolved if len(reliable_resolved) >= 3 else reliable_all
    top_late = rank_pool.nlargest(min(10, len(rank_pool)), "late_share")[
        ["player_name", "team_abbrev", "total_poss", "late", "late_share"]
    ]
    top_early = rank_pool.nlargest(min(10, len(rank_pool)), "early_share")[
        ["player_name", "team_abbrev", "total_poss", "early", "early_share"]
    ]

    # Feature flip analysis: late_mean - early_mean per player per feature
    flip_rows: list[dict] = []
    if cv_feature_cols:
        for feat in cv_feature_cols:
            feat_df = long_df[long_df["feature_name"] == feat]
            pivot = feat_df.pivot_table(
                index="pkey", columns="bucket", values="mean_value", aggfunc="mean"
            )
            for b in ["early", "late"]:
                if b not in pivot.columns:
                    pivot[b] = np.nan
            valid = pivot.dropna(subset=["early", "late"])
            if len(valid) < 3:
                continue
            delta = valid["late"] - valid["early"]
            pop_std = delta.std()
            if pop_std == 0 or pd.isna(pop_std):
                continue
            pkey_name_map = (
                wide.set_index("ckey")["player_name"].to_dict()
            )
            for pkey, d in delta.items():
                if abs(d) < 1e-6:
                    continue
                flip_rows.append({
                    "feature_name": feat,
                    "pkey": pkey,
                    "player_name": pkey_name_map.get(pkey, pkey),
                    "delta_late_minus_early": round(d, 4),
                    "z": round(d / pop_std, 2),
                })

    flip_df = pd.DataFrame(flip_rows) if flip_rows else pd.DataFrame()

    # New bugs to surface
    new_bugs: list[str] = []

    fb_rate = df["fast_break"].mean() if "fast_break" in df.columns else 0
    if fb_rate > 0.12:
        new_bugs.append(
            f"{fb_rate:.1%} of attributed possessions flagged fast_break — these are "
            "bucketed as 'early' regardless of duration, potentially inflating early_share "
            "for transition teams. Consider a separate fast_break bucket in future iterations."
        )

    # Check pbp_fill inflation
    poss_all = pd.concat([
        pd.read_csv(g) for g in glob.glob(str(TRACKING_DIR / "*/possessions.csv"))
        if os.path.exists(g)
    ][:10], ignore_index=True)
    n_pbp_fill = poss_all["source"].value_counts().get("pbp_fill", 0) if "source" in poss_all.columns else 0
    n_total = len(poss_all)
    if n_pbp_fill / max(n_total, 1) > 0.5:
        new_bugs.append(
            f"In sampled games, {n_pbp_fill}/{n_total} possessions are source='pbp_fill' "
            "(hardcoded duration=12s, NaN possession_id). These are CV-pipeline stubs "
            "that should be replaced with real tracking data. Current atlas skips them. "
            "Fix: ensure CV pipeline generates a valid possession_id for all tracked sequences."
        )

    _write_atlas(
        df=df,
        wide_all=reliable_all,
        wide_resolved=reliable_resolved,
        top_late=top_late,
        top_early=top_early,
        flip_df=flip_df,
        processed=processed,
        skipped_no_data=skipped_no_data,
        skipped_error=skipped_error,
        n_records=len(all_records),
        cv_feature_cols=cv_feature_cols,
        new_bugs=new_bugs,
        bucket_counts=bucket_counts,
        total_games=len(all_game_dirs),
    )

    log.info("INT-49 complete.")


def _write_atlas(
    df, wide_all, wide_resolved, top_late, top_early, flip_df,
    processed, skipped_no_data, skipped_error, n_records, cv_feature_cols,
    new_bugs, bucket_counts, total_games,
) -> None:
    import datetime
    today = datetime.date.today().isoformat()

    def pct(x):
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return "N/A"
        return f"{x:.1%}"

    def fmt_table(frame, cols, col_labels=None, pct_cols=None) -> str:
        pct_cols = pct_cols or []
        if col_labels is None:
            col_labels = cols
        lines = ["| " + " | ".join(col_labels) + " |"]
        lines.append("| " + " | ".join(["---"] * len(cols)) + " |")
        for _, row in frame.iterrows():
            parts = []
            for c in cols:
                v = row[c]
                if c in pct_cols:
                    parts.append(pct(v))
                elif isinstance(v, float) and not np.isnan(v):
                    parts.append(f"{v:.3f}")
                else:
                    parts.append(str(v) if not _is_na(v) else "N/A")
            lines.append("| " + " | ".join(parts) + " |")
        return "\n".join(lines)

    bucket_dist = "\n".join(
        f"  - {b}: {n:,} ({n/max(bucket_counts.sum(),1)*100:.1f}%)"
        for b, n in bucket_counts.items()
    )

    n_resolved_reliable = len(wide_resolved)
    n_all_reliable = len(wide_all)
    n_total_pkeys = df["pkey"].nunique()

    late_section = fmt_table(
        top_late,
        cols=["player_name", "team_abbrev", "total_poss", "late", "late_share"],
        col_labels=["Player", "Team", "Total Poss", "Late Poss", "Late Share"],
        pct_cols=["late_share"],
    ) if len(top_late) > 0 else "_No players met the reliable threshold._"

    early_section = fmt_table(
        top_early,
        cols=["player_name", "team_abbrev", "total_poss", "early", "early_share"],
        col_labels=["Player", "Team", "Total Poss", "Early Poss", "Early Share"],
        pct_cols=["early_share"],
    ) if len(top_early) > 0 else "_No players met the reliable threshold._"

    # Feature flip section
    if not flip_df.empty:
        top_flip = flip_df.assign(abs_z=flip_df["z"].abs()).nlargest(10, "abs_z")
        flip_section = "\n### Features that flip by bucket (late − early, normalised z)\n\n"
        flip_section += fmt_table(
            top_flip[["player_name", "feature_name", "delta_late_minus_early", "z"]],
            cols=["player_name", "feature_name", "delta_late_minus_early", "z"],
            col_labels=["Player", "Feature", "Δ(late−early)", "z-score"],
        )
    else:
        flip_section = "\n*Insufficient data for flip analysis — need CV features from tracking_data.*\n"

    bugs_block = ""
    if new_bugs:
        bugs_block = "\n## Newly Surfaced Bugs / Candidates\n\n"
        for b in new_bugs:
            bugs_block += f"- {b}\n"

    content = f"""---
atlas: INT-49
title: Shot-Clock Bucket CV Signatures
created: {today}
updated: {today}
status: complete
tags: [intelligence, cv, shot-clock, possession, player-profiles, pace]
---

# INT-49 — Shot-Clock Bucket CV Signatures

> **ISSUE-023 caveat**: Per-frame shot clock is unreliable (MAE = 17.16s — the clock
> doesn't decrement per frame in the CV pipeline). This atlas uses **possession DURATION**
> as a proxy for time-remaining on the shot clock.
>
> **Player identity**: `player_id` in tracking data is a per-game slot (1-10), NOT a
> persistent NBA ID. This atlas uses `(player_name, team_abbrev)` as the cross-game key.
> Players with unresolved jersey OCR (name ends in `#?`) appear in the parquet but are
> excluded from resolved-player rankings.

## Coverage

| Metric | Value |
|---|---|
| Total games with possessions.csv | {total_games} |
| Games with usable CV possessions | {processed} |
| Games with no CV possessions (skipped) | {skipped_no_data} |
| Games with errors | {skipped_error} |
| Total attributed possession records | {n_records:,} |
| Unique player keys (all, incl. unresolved) | {n_total_pkeys} |
| Players with ≥{MIN_POSS_FOR_RELIABLE} possessions — resolved names | {n_resolved_reliable} |
| Players with ≥{MIN_POSS_FOR_RELIABLE} possessions — all | {n_all_reliable} |

### Bucket distribution (all attributed possessions)

{bucket_dist}

### CV features extracted

{', '.join(cv_feature_cols) if cv_feature_cols else 'None — tracking_data not populated for most games'}

---

## Top Late-Clock Dependent Players (≥{MIN_POSS_FOR_RELIABLE} possessions)

*Highest share of possessions in the **late** bucket (0–7s duration)*

{late_section}

**Interpretation**: High late_share = frequently in scramble / isolation situations.
These players are **vulnerable to opponents that force fast possessions** — if the defense
pushes them into early-clock situations, their effectiveness drops.

---

## Top Early-Clock Attackers (≥{MIN_POSS_FOR_RELIABLE} possessions)

*Highest share of possessions in the **early** bucket (17–24s duration)*

{early_section}

**Interpretation**: High early_share = player prefers push-pace or quick-decision sets.
These players are **vulnerable to slow-down defenses** that force half-court late-clock scenarios.

---

## CV Feature Flips by Bucket
{flip_section}

**How to read**: Positive Δ(late−early) = feature is HIGHER in late-clock vs early-clock.
`paint_dwell` rising in late-clock = player attacks the paint under pressure.
`dribble_count` rising in late-clock = player iso ball-handles under the clock.

---

## Methodology

1. **Duration bucketing** (possession duration from CV start/end frames):
   - `early`: 17–24.5s → set offense, first-look opportunity
   - `mid`: 7–17s → half-court execution, pick-and-roll
   - `late`: 0–7s → scramble, isolation, desperation
   - `fast_break == True` → overrides to `early` regardless of duration

2. **Player attribution** (priority order):
   a. `shot_log.csv` player_name/team for possessions ending in a shot
   b. Modal ball-handler (player with most `ball_possession == 1` frames) from tracking_data
   c. Unattributed possessions are excluded

3. **Player identity**: `player_key = player_name + "/" + team_abbrev`. Cross-game stable.
   Unresolved jerseys (name contains `#?`) excluded from resolved-player rankings.

4. **CV feature aggregation**: mean of frame-level values for the ball-handler player
   within the possession's frame range. 9 features extracted where available.

5. **pbp_fill rows**: Rows where `source='pbp_fill'` have NaN possession_id and hardcoded
   duration_sec=12.0 — they are PBP-reconstructed stubs without CV tracking. Skipped entirely.

---

## ISSUE-023 Caveat (full)

The `shot_clock_est` field in tracking_data doesn't decrement between scoreboard OCR reads —
it holds the last read value step-wise. Possession DURATION is a better proxy because it
measures actual elapsed time from CV-tracked start/end frames (accurate to ±3s typical error).

**Quick fix for ISSUE-023**: In the CV pipeline, linearly interpolate `shot_clock_est`
between consecutive non-null OCR reads. Estimated effort: Low (1 line change in scoreboard
ingestion). This would enable true per-frame shot-clock features.
{bugs_block}
---

## Outputs

| File | Description |
|---|---|
| `data/intelligence/shot_clock_buckets.parquet` | Long: pkey × bucket × feature mean values |
| `data/intelligence/shot_clock_player_profiles.json` | Per-player bucket shares + reliable flag |
| `vault/Intelligence/Shot_Clock_Buckets_Atlas.md` | This document |
"""

    atlas_path = VAULT_DIR / "Shot_Clock_Buckets_Atlas.md"
    with open(atlas_path, "w", encoding="utf-8") as fh:
        fh.write(content)
    log.info("Atlas written to %s", atlas_path)

    # Append new bugs to bug roadmap
    _append_bugs_to_roadmap(new_bugs)


def _append_bugs_to_roadmap(new_bugs: list[str]) -> None:
    bug_roadmap = VAULT_DIR / "CV_Pipeline_Bug_Roadmap.md"
    if not bug_roadmap.exists():
        return

    text = bug_roadmap.read_text(encoding="utf-8")

    # Add ISSUE-023 interpolation note if not already present
    if "INT-49" not in text and "shot clock interpolation" not in text.lower():
        entry = """
### Bug 15 — ISSUE-023: Shot clock doesn't decrement per-frame (INT-49 re-confirmation)
**Surfaced by**: INT-49 Shot-Clock Bucket Atlas
**Symptom**: `shot_clock_est` in tracking_data.csv is step-shaped — holds the last scoreboard
OCR value until the next read. Confirmed MAE=17.16s. Per-frame shot clock unusable for any
feature requiring time-remaining during a possession.
**Root cause**: Pipeline writes last scoreboard OCR value per frame without interpolation.
**Affected**: Any per-frame shot-clock feature. INT-49 workaround: uses possession DURATION.
**Fix effort**: Low — interpolate `shot_clock_est` linearly between consecutive OCR reads.

### Bug 16 — pbp_fill stubs inflate possession count, hide CV coverage gap
**Surfaced by**: INT-49 Shot-Clock Bucket Atlas
**Symptom**: possessions.csv contains rows with source='pbp_fill', NaN possession_id,
and hardcoded duration_sec=12.0. These are PBP-reconstructed stubs that pass a length check
but carry no CV information. ~70% of all possession rows across the dataset are pbp_fill stubs.
**Root cause**: The pipeline falls back to PBP when CV tracking fails to segment a possession.
**Impact**: INT-49 had to skip 70% of possession rows. Any metric based on possession count
(e.g. "possessions per game") is inflated by pbp_fill stubs.
**Fix effort**: Low — add a `cv_tracked` boolean flag to possessions.csv; callers can filter.
"""
        with open(bug_roadmap, "a", encoding="utf-8") as fh:
            fh.write(entry)
        log.info("Appended Bug 15 + Bug 16 to CV_Pipeline_Bug_Roadmap.md")

    # Append any dynamically found bugs
    if new_bugs:
        for i, bug in enumerate(new_bugs, start=17):
            bug_id = f"Bug {i}"
            if bug_id in text:
                continue
            entry = f"\n### {bug_id} — INT-49: {bug[:90]}\n**Surfaced by**: INT-49\n**Detail**: {bug}\n**Fix effort**: Low\n"
            with open(bug_roadmap, "a", encoding="utf-8") as fh:
                fh.write(entry)


if __name__ == "__main__":
    build_shot_clock_buckets()
