"""ARM-B atlas section: ``bench_production`` — team bench scoring, depth, and minute split.

Implements :class:`AtlasSection` for the ``"bench_production"`` section of a
team's persistent profile.  Every sub-field is derived from existing parquets
cited in spec_features.md / spec_intel_memory.md — no re-derivation.

**Sub-field coverage:**

REAL (populated from parquets):
  bench_minutes.*    — bench_min_share (fraction of total team minutes played by
                       non-starters), starter_min_share (1 - bench_min_share).
                       Starters = top-5 players by season minutes_on from
                       data/cache/on_off_features.parquet (season-level, 2024-25).
  bench_net_rtg.*    — bench_net_rtg (minutes-weighted on_court_plus_minus of bench
                       players with >=300 season minutes), bench_depth (count of
                       bench players with >=300 season minutes), derived from
                       data/cache/on_off_features.parquet.
  team_context.*     — off_rtg, def_rtg, net_rtg (per-game averages <= as_of) from
                       data/team_advanced_stats.parquet; n_games used as provenance n.

DEFER (no source parquet available):
  bench_scoring.*    — DEFER: no per-game player-level points column in available
                       parquets (player_pf has minutes+fouls but not points;
                       player_adv_stats has ratings but not raw box-score PTS).
                       Populate when a per-game player boxscore parquet is added.
  bench_ts_pct.*     — DEFER: true-shooting % for bench players requires per-game
                       FGA+FTA+PTS for each bench player; not in current parquets.
  bench_fast_break.* — DEFER: player_breakdown_features.parquet has pts_fast_break
                       but is player-level with no starter/bench flag.

RESERVED CV SLOTS (value=None; CV branch fills later):
  None — bench production is derived from boxscore / on-off data; no CV slot needed.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.loop.atlas import AtlasArtifact, AtlasSection, CVSlot, confidence_from_n
from src.loop.profile_factory_bridge import register_section

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = DATA / "cache"

# ---------------------------------------------------------------------------
# Module-level lazy parquet cache (one load per process)
# ---------------------------------------------------------------------------

_SRC_CACHE: Dict[str, Optional[pd.DataFrame]] = {}

# Minimum season minutes to count a bench player as a depth contributor.
_BENCH_MIN_THRESHOLD = 300


def _load(key: str, path: Path) -> Optional[pd.DataFrame]:
    """Load a parquet once per process; cache None on missing/error."""
    if key not in _SRC_CACHE:
        try:
            _SRC_CACHE[key] = pd.read_parquet(path) if path.exists() else None
        except Exception:
            _SRC_CACHE[key] = None
    return _SRC_CACHE[key]


def _rd(v: Any) -> Optional[float]:
    """Clean scalar: NaN/inf -> None, numpy -> python float, round 4 dp."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if np.isnan(f) or np.isinf(f):
        return None
    return round(f, 4)


def _ri(v: Any) -> Optional[int]:
    """Clean integer scalar: NaN/inf -> None."""
    if v is None:
        return None
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f):
            return None
        return int(f)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Per-source aggregation helpers
# ---------------------------------------------------------------------------

def _on_off_bench(
    team_tricode: str,
) -> Dict[str, Any]:
    """Derive bench minute share, depth, and net rating from on_off_features.

    Source: data/cache/on_off_features.parquet (season-level, 2024-25).
    Starters are defined as the top-5 players by season ``minutes_on``.
    Bench = all remaining players ranked 6+ by total minutes.

    No game_date filtering is possible (season-level summary); treated as a
    pre-published season summary, acceptably safe for as_of >= season start.
    LEAK-SAFE note: this is the same pattern as player_tracking_features.parquet
    in team_offensive_scheme — season aggregate keyed to the published season.

    Returns dict with keys: bench_min_share, starter_min_share, bench_depth,
    bench_net_rtg, n_players, or empty dict on missing data.
    """
    df = _load("on_off", CACHE / "on_off_features.parquet")
    if df is None or df.empty:
        return {}

    if "team_abbreviation" not in df.columns:
        return {}

    team_rows = df[df["team_abbreviation"] == team_tricode].copy()
    if len(team_rows) < 2:
        return {}

    if "minutes_on" not in df.columns:
        return {}

    team_rows = team_rows.sort_values("minutes_on", ascending=False).reset_index(drop=True)

    # Top-5 by season minutes = starters; rest = bench
    starters = team_rows.iloc[:5]
    bench = team_rows.iloc[5:]

    total_min = team_rows["minutes_on"].sum()
    bench_min = bench["minutes_on"].sum()
    starter_min = starters["minutes_on"].sum()

    if total_min <= 0:
        return {}

    bench_min_share = float(bench_min / total_min)
    starter_min_share = float(starter_min / total_min)

    # Clamp proportions to [0, 1] (safety guard; should always be in range)
    bench_min_share = max(0.0, min(1.0, bench_min_share))
    starter_min_share = max(0.0, min(1.0, starter_min_share))

    # Bench depth: bench players with >= _BENCH_MIN_THRESHOLD season minutes
    bench_contributors = bench[bench["minutes_on"] >= _BENCH_MIN_THRESHOLD]
    bench_depth = len(bench_contributors)

    # Bench net rating: minutes-weighted on_court_plus_minus of contributors
    bench_net_rtg: Optional[float] = None
    if not bench_contributors.empty and "on_court_plus_minus" in bench_contributors.columns:
        weights = bench_contributors["minutes_on"].astype(float)
        pm = bench_contributors["on_court_plus_minus"].astype(float)
        w_sum = weights.sum()
        if w_sum > 0:
            bench_net_rtg = float((pm * weights).sum() / w_sum)
            if np.isnan(bench_net_rtg) or np.isinf(bench_net_rtg):
                bench_net_rtg = None

    return {
        "bench_min_share": _rd(bench_min_share),
        "starter_min_share": _rd(starter_min_share),
        "bench_depth": _ri(bench_depth),
        "bench_net_rtg": _rd(bench_net_rtg),
        "n_players": _ri(len(team_rows)),
    }


def _team_adv_stats(
    team_tricode: str, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Aggregate team_advanced_stats for games <= as_of.

    LEAK-SAFE: filters game_date <= as_of before aggregating.
    Returns off_rtg, def_rtg, n_games.
    """
    df = _load("team_adv", DATA / "team_advanced_stats.parquet")
    if df is None or df.empty:
        return {}

    rows = df[df["team_tricode"] == team_tricode].copy()
    if rows.empty:
        return {}

    rows["game_date"] = pd.to_datetime(rows["game_date"])
    rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return {}

    n = len(rows)
    means = rows[
        [c for c in ["off_rtg", "def_rtg", "net_rtg"] if c in rows.columns]
    ].mean()

    return {
        "off_rtg": _rd(means.get("off_rtg")),
        "def_rtg": _rd(means.get("def_rtg")),
        "net_rtg": _rd(means.get("net_rtg")),
        "n_games": n,
    }


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class TeamBenchProduction(AtlasSection):
    """Deep team bench-production atlas section (entity='team', section='bench_production').

    Builds a provenance-stamped, leak-safe artifact covering bench minute share,
    bench depth (contributors with >= 300 season minutes), bench net rating
    (minutes-weighted on-court +/- for bench players), and team-level efficiency
    context.  No CV slots are reserved (bench production is boxscore-derived).

    Sources used:
      - data/cache/on_off_features.parquet  (bench_min_share, bench_depth,
                                             bench_net_rtg — season-level 2024-25)
      - data/team_advanced_stats.parquet    (off_rtg, def_rtg, n_games per game_date)

    DEFER sections (no per-game player boxscore in current parquets):
      - bench_scoring  — per-game bench PTS requires a player boxscore parquet
      - bench_ts_pct   — true-shooting % for bench split; no FGA/FTA/PTS per bench
      - bench_fast_break — player_breakdown_features has this but lacks bench flag
    """

    name: str = "bench_production"
    entity: str = "team"
    source_name: str = (
        "on_off_features.parquet (bench_min_share/depth/net_rtg) + "
        "team_advanced_stats.parquet (team efficiency + n_games)"
    )
    conf_cap: Optional[str] = None

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the bench_production artifact for team ``entity_id`` as-of ``as_of``.

        Args:
            entity_id: team tricode (str, e.g. "OKC").
            as_of:     leak boundary — only data with game_date <= as_of is used.
                       on_off_features is season-level (no game_date) and is
                       treated as a pre-published season summary.

        Returns:
            AtlasArtifact or None when both sources are missing for this team.
        """
        tricode = str(entity_id).upper()
        as_of_str = as_of.date().isoformat()

        # --- Gather sub-components ---
        oo = _on_off_bench(tricode)
        adv = _team_adv_stats(tricode, as_of)

        # Bail when primary source (on_off_features) is unavailable
        if not oo:
            return None

        # --- bench_minutes sub-dict ---
        bench_minutes: Dict[str, Any] = {
            "bench_min_share": oo.get("bench_min_share"),
            "starter_min_share": oo.get("starter_min_share"),
            "_note": (
                "Starters = top-5 players by season minutes_on; bench = players "
                "ranked 6+ by total minutes. Source: on_off_features.parquet "
                "(season-level 2024-25; no per-game date filtering)."
            ),
        }

        # --- bench_net_rtg sub-dict ---
        bench_net_rtg_sub: Dict[str, Any] = {
            "bench_net_rtg": oo.get("bench_net_rtg"),
            "bench_depth": oo.get("bench_depth"),
            "_source": (
                "Minutes-weighted on_court_plus_minus of bench players "
                "(>= 300 season minutes). bench_depth = count of such contributors."
            ),
        }

        # --- team_context sub-dict ---
        team_context: Dict[str, Any] = {}
        if adv:
            team_context = {
                "off_rtg": adv.get("off_rtg"),
                "def_rtg": adv.get("def_rtg"),
                "net_rtg": adv.get("net_rtg"),
                "_source": "team_advanced_stats.parquet per-game mean <= as_of",
            }

        # --- DEFER placeholders ---
        bench_scoring: Dict[str, Any] = {
            "_note": (
                "DEFER: no per-game player-level PTS column in available parquets. "
                "player_pf has minutes+fouls but not points; player_adv_stats has "
                "ratings but not raw box-score PTS. Populate when a per-game player "
                "boxscore parquet (PTS, FGA, FTA) is added (e.g. scripts/"
                "fetch_player_boxscores.py)."
            ),
        }
        bench_ts_pct: Dict[str, Any] = {
            "_note": (
                "DEFER: true-shooting % for bench players requires per-game FGA, "
                "FTA, and PTS for each bench player. Not available in current "
                "parquets. Populate alongside bench_scoring when boxscore parquet lands."
            ),
        }

        # --- Assemble sub_fields ---
        sub_fields: Dict[str, Any] = {
            "bench_minutes": bench_minutes,
            "bench_net_rtg_section": bench_net_rtg_sub,
            "team_context": team_context,
            "bench_scoring": bench_scoring,
            "bench_ts_pct": bench_ts_pct,
        }

        # Headline scalar: bench net rating (best single bench quality proxy)
        value = oo.get("bench_net_rtg")

        # --- Sample size and confidence ---
        # Primary n: from team_advanced_stats (per-game rows = real game count)
        # Fall back to on_off n_players if team_adv is empty
        n = adv.get("n_games") if adv else None
        if not n:
            n = 1  # will be low confidence
        confidence = confidence_from_n(n, cap=self.conf_cap)

        provenance: Dict[str, Any] = {
            "source": self.source_name,
            "n": n,
            "confidence": confidence,
            "as_of": as_of_str,
        }

        return AtlasArtifact(
            section=self.name,
            entity=self.entity,
            entity_id=tricode,
            value=value,
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    # ------------------------------------------------------------------
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity: required sub-field keys present + sane ranges.

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name or artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields
        required_keys = {
            "bench_minutes", "bench_net_rtg_section",
            "team_context", "bench_scoring", "bench_ts_pct",
        }
        if not required_keys.issubset(sf.keys()):
            return False

        # bench_min_share and starter_min_share must be in [0, 1]
        bm = sf.get("bench_minutes", {})
        bms = bm.get("bench_min_share")
        sms = bm.get("starter_min_share")
        if bms is not None and not (0.0 <= bms <= 1.0):
            return False
        if sms is not None and not (0.0 <= sms <= 1.0):
            return False
        # They should approximately sum to 1 when both present
        if bms is not None and sms is not None:
            if abs((bms + sms) - 1.0) > 0.01:
                return False

        # bench_depth must be non-negative
        bd = sf.get("bench_net_rtg_section", {}).get("bench_depth")
        if bd is not None and bd < 0:
            return False

        # CV slots must all have value=None
        for slot in artifact.cv_fields.values():
            if slot.value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for bench_production (empty — no CV slots needed).

        Bench production is derived from boxscore / on-off data.  No CV-derived
        bench signal is planned at this time.  Returns an empty dict to satisfy
        the AtlasSection contract.
        """
        return {}


# ---------------------------------------------------------------------------
# Module-level registration helper (called by orchestrator / batch build)
# ---------------------------------------------------------------------------

def build_and_register(
    team_tricodes: Optional[List[str]] = None,
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Build bench_production for a list of team tricodes and register via the bridge.

    Args:
        team_tricodes: list of NBA team tricodes (str, e.g. ["OKC", "BOS"]).
                       If None, discovers from on_off_features.parquet.
        as_of:         leak boundary date (defaults to today UTC midnight).
        store:         PointInTimeStore; when provided, artifacts are written to the store.
        dry_run:       skip all disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    if team_tricodes is None:
        df = _load("on_off_disc", CACHE / "on_off_features.parquet")
        if df is not None and "team_abbreviation" in df.columns:
            team_tricodes = sorted(df["team_abbreviation"].dropna().unique().tolist())
        else:
            team_tricodes = []

    section = TeamBenchProduction()
    artifacts: List[AtlasArtifact] = []
    for tri in team_tricodes:
        try:
            art = section.build(tri, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
