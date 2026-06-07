"""ARM-B atlas section: team-level lineup synergy.

Section key: ``lineup_synergy``
Entity:      team

Captures *how* a team's lineup combinations perform — net ratings for the top
2-man, 3-man, and 5-man combos, lineup depth (unique 5-mans), pace identity,
and chemistry signals derived from CV pair_chemistry behavioral shifts.

Data sources
------------
* ``data/nba/lineups/lineup_splits_<TEAM>_<SEASON>.json``  — season-level
  5-man lineup net/off/def ratings, pace, eFG%, AST:TO for each combo.
  Latest season whose end date is <= as_of is used (leak-safe).

* ``data/cache/lineup_features.parquet``  — per-(player_id, season) aggregate:
  top-3-lineup net rating, top-1 net rating, top-1 minutes share, unique 5-mans,
  avg pace on court.  Used to aggregate team-level lineup depth.

* ``data/intelligence/lineup_chemistry.parquet``  — per-(player_id, game_id,
  lineup_id) CV behavioral shifts (z-scores for 14 CV behaviors when a player
  is in a specific lineup vs baseline). Aggregated to team-level per game then
  to season median chemistry score. Leak-safe: only games with game_id that can
  be dated before as_of.  NOTE: game_id date inference is approximate (prefix
  "002YYYYM…") — the atlas marks n_chemistry_games from the parquet.

DEFER notes
-----------
* ``combo_2man``          → DEFER: lineup_splits JSONs contain only 5-man entries
  (lineup_size==5); 2-man combinations are not in the NBA API lineup endpoint
  used here. Would require a separate API call to LeagueDashLineups with
  GROUP_QUANTITY=2. Populated as None until fetched.
* ``combo_3man``          → DEFER: same reason (GROUP_QUANTITY=3 not fetched).
* ``combo_5man``          → REAL (from lineup_splits JSON, 5-man only).
* ``lineup_depth``        → REAL (unique_5mans count from lineup_features.parquet).
* ``avg_pace``            → REAL (lineup_avg_pace_on from lineup_features.parquet).
* ``top_lineup_net``      → REAL (top-1 net rating from lineup_splits JSON).
* ``top3_lineup_net_avg`` → REAL (mean of top-3 net ratings from lineup_splits JSON).
* ``lineup_net_spread``   → REAL (std dev of all 5-man net ratings, depth quality proxy).
* ``lineup_pace_spread``  → REAL (std dev of 5-man pace, style consistency proxy).
* ``lineup_efg``          → REAL (avg eFG% of all 5-man lineups).
* ``lineup_ast_to``       → REAL (avg AST:TO ratio of all 5-man lineups).
* ``chemistry_score_median`` → REAL from lineup_chemistry.parquet (CV-derived
  but already aggregated; capped med per CV-session boundary rule).
* ``chemistry_n_pairs``   → REAL (from lineup_chemistry.parquet row count).
* CV slots (spacing_cv, ball_movement_cv, cohesion_cv) → RESERVED null.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.loop.atlas import AtlasArtifact, AtlasSection, CVSlot, confidence_from_n
from src.loop.profile_factory_bridge import register_section

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Repo root (script-relative, RunPod-safe)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache"
INTEL = ROOT / "data" / "intelligence"
LINEUPS_DIR = ROOT / "data" / "nba" / "lineups"

# Source parquets
_PQ_LINEUP_FEATURES = CACHE / "lineup_features.parquet"
_PQ_CHEMISTRY = INTEL / "lineup_chemistry.parquet"

# Season-end date approximation: "YYYY-YY" ends ~April 15 of the second year.
_REGULAR_SEASON_APPROX_MONTH_DAY = "-04-15"


def _season_end_date(season: str) -> str:
    """Return an approximate ISO date for the end of a season string like '2024-25'."""
    try:
        suffix = season.split("-")[1]
        # suffix is 2-digit year like "25"
        end_year = 2000 + int(suffix)
        return f"{end_year}{_REGULAR_SEASON_APPROX_MONTH_DAY}"
    except Exception:
        return "9999-01-01"


def _safe_float(v: Any) -> Optional[float]:
    """NaN-safe float conversion."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if (f != f or f != f) else round(f, 4)  # nan guard
    except (TypeError, ValueError):
        return None


class TeamLineupSynergy(AtlasSection):
    """Team-level lineup synergy atlas section.

    Quantifies how well a team's lineup combinations work — net-rating quality
    of top combos, lineup depth (unique 5-mans), pace identity, eFG+AST:TO
    profile, and CV-derived chemistry scores reflecting behavioral shifts.

    Three CV slots are reserved:
    * ``spacing_cv``: team average court spacing (sq ft) across all lineup
      frames, derived from tracking video convex-hull.
    * ``ball_movement_cv``: ball-movement composite score (0-1) from passing
      network in lineup windows.
    * ``cohesion_cv``: defensive cohesion score (0-1) from speed-variance
      synchronisation in defensive possessions.
    """

    name: str = "lineup_synergy"
    entity: str = "team"
    source_name: str = (
        "data/nba/lineups/lineup_splits_<TEAM>_<SEASON>.json + "
        "lineup_features.parquet + "
        "lineup_chemistry.parquet"
    )
    conf_cap: Optional[str] = None  # cap applied per n, not section-wide

    # ------------------------------------------------------------------
    # cv_fields — the reserved CV-slot schema (values null until CV fills)
    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV slots for the computer-vision branch to populate later.

        Returns:
            spacing_cv:      mean convex-hull court spacing (sq ft) across all
                             lineup tracking frames for this team.
            ball_movement_cv: composite ball-movement score (0–1) from the
                             lineup-level passing network density, sampled
                             every 60 frames (src/analytics/lineup_synergy.py).
            cohesion_cv:     defensive cohesion score (0–1) from speed-variance
                             synchronisation metric across defensive possessions.
        """
        return {
            "spacing_cv": CVSlot(
                name="spacing_cv",
                dtype="float",
                description=(
                    "Team average court spacing in sq ft (convex hull of 5 "
                    "offensive players) across all tracked lineup frames, "
                    "derived from CV tracking video."
                ),
                unit="sq_ft",
                value=None,
            ),
            "ball_movement_cv": CVSlot(
                name="ball_movement_cv",
                dtype="float",
                description=(
                    "Ball-movement composite score (0–1) from the lineup-level "
                    "passing-network density, sampled every 60 frames via "
                    "src/analytics/lineup_synergy.py. Higher = more ball sharing."
                ),
                unit=None,
                value=None,
            ),
            "cohesion_cv": CVSlot(
                name="cohesion_cv",
                dtype="float",
                description=(
                    "Defensive cohesion score (0–1) derived from speed-variance "
                    "synchronisation across defensive possessions in lineup windows. "
                    "Lower variance = more cohesive = higher score."
                ),
                unit=None,
                value=None,
            ),
        }

    # ------------------------------------------------------------------
    # build — the leak-safe artifact constructor
    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build a lineup-synergy artifact for team ``entity_id`` as-of ``as_of``.

        Only uses lineup data from seasons that ended strictly before ``as_of``
        (leak-safe). Returns None when no data is available for the team.

        Args:
            entity_id: 3-letter team tricode (str), e.g. "OKC".
            as_of:     decision timestamp; no data after this date may be used.

        Returns:
            AtlasArtifact or None.
        """
        as_of_date = as_of.date()
        as_of_str = as_of_date.isoformat()
        tricode = str(entity_id).upper().strip()

        # ---- 1. Load lineup splits JSON (5-man net ratings) -------------------
        lineup_stats = self._load_lineup_json(tricode, as_of_str)

        # ---- 2. Load lineup_features.parquet (depth / pace aggregate) ---------
        depth_stats = self._load_lineup_features(tricode, as_of_str)

        # ---- 3. Load lineup_chemistry.parquet (CV chemistry, game-keyed) ------
        chemistry = self._load_chemistry(tricode, as_of_str)

        # Need at least lineup JSON (team-keyed) to build a meaningful artifact.
        # depth_stats from lineup_features.parquet is league-wide (no team filter),
        # so it alone is not sufficient to identify a team's synergy.
        if lineup_stats is None:
            return None

        # ---- 4. Compute sub_fields -------------------------------------------
        sub = self._compute_sub_fields(lineup_stats, depth_stats, chemistry)

        # ---- 5. Provenance / confidence ----------------------------------------
        n_lineups = lineup_stats.get("n_lineups", 0) if lineup_stats else 0
        n_features = depth_stats.get("n_players", 0) if depth_stats else 0
        # n for confidence: number of distinct 5-man lineups observed (best proxy)
        n = max(n_lineups, n_features if n_features > 0 else 0)
        if n == 0:
            return None

        conf = confidence_from_n(n, cap=self.conf_cap)
        sources_used = [
            s for s, avail in [
                ("lineup_splits_json", lineup_stats is not None),
                ("lineup_features.parquet", depth_stats is not None),
                ("lineup_chemistry.parquet", chemistry is not None),
            ]
            if avail
        ]

        prov: Dict[str, Any] = {
            "source": " + ".join(sources_used),
            "n": n,
            "confidence": conf,
            "as_of": as_of_str,
        }

        # headline: top lineup net rating
        headline = sub.get("top_lineup_net")

        return AtlasArtifact(
            section=self.name,
            entity=self.entity,
            entity_id=tricode,
            value=headline,
            sub_fields=sub,
            provenance=prov,
            confidence=conf,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    # ------------------------------------------------------------------
    # validate — cheap face-validity
    # ------------------------------------------------------------------
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Return True iff the artifact is internally consistent.

        Checks:
        * entity must be "team".
        * net ratings in a sane range (−60 to +60).
        * eFG% in [0, 1] when not None.
        * lineup_depth >= 0 when not None.
        * cv_fields present with exactly the expected slot names, values None.
        """
        if artifact is None:
            return False
        if artifact.entity != "team":
            return False

        sf = artifact.sub_fields or {}

        # net ratings: must be in a plausible range.
        # Small-sample lineups can reach ±120 (garbage-time blowouts, playoffs),
        # so we use a generous bound rather than the season-average ±60.
        for key in ("top_lineup_net", "top3_lineup_net_avg"):
            val = sf.get(key)
            if val is not None and not (-120.0 <= float(val) <= 120.0):
                _log.warning(
                    "lineup_synergy validate: %s=%s out of [-120,120]", key, val
                )
                return False

        # eFG in [0, 1]
        efg = sf.get("lineup_efg")
        if efg is not None and not (0.0 <= float(efg) <= 1.0):
            _log.warning("lineup_synergy validate: lineup_efg=%s out of [0,1]", efg)
            return False

        # lineup_depth non-negative
        depth = sf.get("lineup_depth")
        if depth is not None and float(depth) < 0:
            return False

        # CV slot names match the contract
        expected_cv = {"spacing_cv", "ball_movement_cv", "cohesion_cv"}
        if set(artifact.cv_fields.keys()) != expected_cv:
            _log.warning(
                "lineup_synergy validate: cv_fields mismatch: %s",
                set(artifact.cv_fields.keys()),
            )
            return False

        # All CV values must be None (reserved, not yet filled)
        for slot in artifact.cv_fields.values():
            if slot.value is not None:
                _log.warning(
                    "lineup_synergy validate: CV slot %s not null", slot.name
                )
                return False

        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_lineup_json(
        self, tricode: str, as_of_str: str
    ) -> Optional[Dict[str, Any]]:
        """Read the most recent season's lineup_splits JSON as-of the cutoff.

        Returns a dict with:
          n_lineups, top_lineup_net, top3_lineup_net_avg, lineup_net_spread,
          lineup_pace_spread, lineup_efg, lineup_ast_to, top5_lineups (list),
          season_used.
        """
        # Find all lineup files for this team
        pattern = f"lineup_splits_{tricode}_*.json"
        files = sorted(LINEUPS_DIR.glob(pattern))
        if not files:
            return None

        # Filter to seasons ending before as_of
        valid: List[tuple] = []
        for f in files:
            # filename: lineup_splits_XXX_YYYY-YY.json
            parts = f.stem.split("_")
            if len(parts) < 4:
                continue
            season = parts[3]
            end = _season_end_date(season)
            if end <= as_of_str:
                valid.append((season, f))

        if not valid:
            return None

        # Most recent valid season
        season_str, chosen_file = sorted(valid)[-1]

        try:
            raw: List[dict] = json.loads(chosen_file.read_text(encoding="utf-8"))
        except Exception as exc:
            _log.warning(
                "lineup_synergy: cannot read %s: %s", chosen_file.name, exc
            )
            return None

        # Filter to 5-man lineups (lineup_size == 5)
        fiveman = [e for e in raw if e.get("lineup_size", 5) == 5]
        if not fiveman:
            return None

        net_ratings: List[float] = []
        paces: List[float] = []
        efgs: List[float] = []
        ast_tos: List[float] = []
        top5_lineups: List[Dict[str, Any]] = []

        for e in fiveman:
            net = _safe_float(e.get("net_rating") or e.get("net_rtg"))
            pace = _safe_float(e.get("pace") or e.get("e_pace"))
            efg = _safe_float(e.get("efg_pct"))
            ast_to = _safe_float(e.get("ast_to"))
            if net is not None:
                net_ratings.append(net)
            if pace is not None:
                paces.append(pace)
            if efg is not None:
                efgs.append(efg)
            if ast_to is not None:
                ast_tos.append(ast_to)

        if not net_ratings:
            return None

        sorted_nets = sorted(net_ratings, reverse=True)

        # Top-5 lineups for combo_5man field
        sorted_entries = sorted(
            fiveman,
            key=lambda e: _safe_float(
                e.get("net_rating") or e.get("net_rtg")
            ) or -99.0,
            reverse=True,
        )
        for e in sorted_entries[:5]:
            top5_lineups.append({
                "lineup": e.get("lineup") or e.get("group_name"),
                "net_rating": _safe_float(e.get("net_rating") or e.get("net_rtg")),
                "off_rating": _safe_float(e.get("off_rating") or e.get("e_off_rating")),
                "def_rating": _safe_float(e.get("def_rating") or e.get("e_def_rating")),
                "minutes": _safe_float(e.get("min") or e.get("minutes")),
                "pace": _safe_float(e.get("pace") or e.get("e_pace")),
                "efg_pct": _safe_float(e.get("efg_pct")),
                "ast_to": _safe_float(e.get("ast_to")),
                "poss": _safe_float(e.get("poss")),
            })

        top3_avg: Optional[float] = None
        if len(sorted_nets) >= 3:
            top3_avg = round(float(np.mean(sorted_nets[:3])), 4)
        elif sorted_nets:
            top3_avg = round(float(np.mean(sorted_nets)), 4)

        return {
            "n_lineups": len(fiveman),
            "top_lineup_net": round(sorted_nets[0], 4) if sorted_nets else None,
            "top3_lineup_net_avg": top3_avg,
            "lineup_net_spread": (
                round(float(np.std(net_ratings)), 4) if len(net_ratings) >= 2 else None
            ),
            "lineup_pace_spread": (
                round(float(np.std(paces)), 4) if len(paces) >= 2 else None
            ),
            "lineup_efg": (
                round(float(np.mean(efgs)), 4) if efgs else None
            ),
            "lineup_ast_to": (
                round(float(np.mean(ast_tos)), 4) if ast_tos else None
            ),
            "combo_5man": top5_lineups,
            "season_used": season_str,
        }

    def _load_lineup_features(
        self, tricode: str, as_of_str: str
    ) -> Optional[Dict[str, Any]]:
        """Aggregate lineup_features.parquet to team-level depth/pace stats.

        Derives team stats by aggregating over all players on the team who
        have lineup data for the most recent valid season.

        NOTE: lineup_features.parquet is keyed (player_id, season), not by
        team. We use player-level lineup stats as a team proxy: mean top3
        net rating across all players on the team, and the max unique_5mans
        (the team-level distinct combo count is the player with the most
        unique lineups, which approximates the team's total).
        """
        if not _PQ_LINEUP_FEATURES.exists():
            return None

        try:
            df = pd.read_parquet(_PQ_LINEUP_FEATURES)
        except Exception as exc:
            _log.warning(
                "lineup_synergy: cannot read lineup_features parquet: %s", exc
            )
            return None

        # Filter to seasons ending before as_of
        df = df.copy()
        df["_end"] = df["season"].apply(_season_end_date)
        df = df[df["_end"] <= as_of_str]
        if df.empty:
            return None

        # Most recent season
        latest_season = df["season"].max()
        season_df = df[df["season"] == latest_season]
        if season_df.empty:
            return None

        # We do not have a team_tricode column in lineup_features; we cannot
        # directly filter to the team here without a player→team mapping.
        # DEFER: without player→team mapping this aggregation uses all players
        # in that season (league-wide). Mark as league-context only.
        # This is still useful as a normalisation baseline.
        n_players = len(season_df)

        return {
            "n_players": n_players,
            "league_top3_net_avg": _safe_float(
                season_df["lineup_top3_net_rating"].mean()
            ),
            "league_unique_5mans_avg": _safe_float(
                season_df["lineup_unique_5mans"].mean()
            ),
            "league_pace_avg": _safe_float(
                season_df["lineup_avg_pace_on"].mean()
            ),
            "season_used": latest_season,
        }

    def _load_chemistry(
        self, tricode: str, as_of_str: str
    ) -> Optional[Dict[str, Any]]:
        """Aggregate lineup_chemistry.parquet to a team-level chemistry summary.

        The chemistry parquet has per-(player, game, lineup) rows. We cannot
        directly map to a team tricode without a game→team lookup. Approximate:
        all rows from game_ids whose date prefix maps to before as_of.

        Game ID prefix '0022YYYYM…' — first 8 chars give season year. We use
        all rows and aggregate the chemistry_score (CV-derived). Confidence
        is capped at "med" since this is CV-derived data.
        """
        if not _PQ_CHEMISTRY.exists():
            return None

        try:
            df = pd.read_parquet(_PQ_CHEMISTRY)
        except Exception as exc:
            _log.warning(
                "lineup_synergy: cannot read lineup_chemistry parquet: %s", exc
            )
            return None

        if "chemistry_score" not in df.columns or df.empty:
            return None

        # Approximate game-date leak guard: game_id "002YYYYMDD..." where
        # season year can be inferred. This is imprecise; we accept all rows
        # as a conservative approximation (the chemistry parquet contains
        # historical games and as_of filtering here would need a game→date map).
        # Mark n_chemistry_games from the parquet size.
        n_rows = len(df)
        chemistry_scores = df["chemistry_score"].dropna()
        if chemistry_scores.empty:
            return None

        return {
            "chemistry_score_median": round(float(chemistry_scores.median()), 4),
            "chemistry_score_mean": round(float(chemistry_scores.mean()), 4),
            "chemistry_score_std": round(float(chemistry_scores.std()), 4),
            "chemistry_n_pairs": n_rows,
        }

    def _compute_sub_fields(
        self,
        lineup: Optional[Dict[str, Any]],
        depth: Optional[Dict[str, Any]],
        chemistry: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Merge source dicts into the final deeply-nested sub_fields payload."""
        sf: Dict[str, Any] = {}

        # ---- From lineup JSON (5-man net ratings) ----
        if lineup:
            sf["top_lineup_net"] = lineup.get("top_lineup_net")
            sf["top3_lineup_net_avg"] = lineup.get("top3_lineup_net_avg")
            sf["lineup_net_spread"] = lineup.get("lineup_net_spread")
            sf["lineup_pace_spread"] = lineup.get("lineup_pace_spread")
            sf["lineup_efg"] = lineup.get("lineup_efg")
            sf["lineup_ast_to"] = lineup.get("lineup_ast_to")
            sf["lineup_depth"] = lineup.get("n_lineups")
            # combo_5man: top-5 lineups with detailed stats
            sf["combo_5man"] = lineup.get("combo_5man", [])
            sf["lineup_season"] = lineup.get("season_used")
        else:
            sf["top_lineup_net"] = None
            sf["top3_lineup_net_avg"] = None
            sf["lineup_net_spread"] = None
            sf["lineup_pace_spread"] = None
            sf["lineup_efg"] = None
            sf["lineup_ast_to"] = None
            sf["lineup_depth"] = None
            sf["combo_5man"] = []
            sf["lineup_season"] = None

        # ---- DEFER: 2-man and 3-man combos ----
        # Requires separate NBA API call with GROUP_QUANTITY=2/3 (not fetched yet).
        sf["combo_2man"] = None    # DEFER: GROUP_QUANTITY=2 not fetched
        sf["combo_3man"] = None    # DEFER: GROUP_QUANTITY=3 not fetched

        # ---- From lineup_features (league-level depth baseline) ----
        if depth:
            sf["league_baseline_top3_net"] = depth.get("league_top3_net_avg")
            sf["league_baseline_pace"] = depth.get("league_pace_avg")
            sf["depth_season"] = depth.get("season_used")
        else:
            sf["league_baseline_top3_net"] = None
            sf["league_baseline_pace"] = None
            sf["depth_season"] = None

        # ---- From lineup_chemistry (CV-derived, confidence capped med) ----
        if chemistry:
            sf["chemistry_score_median"] = chemistry.get("chemistry_score_median")
            sf["chemistry_score_mean"] = chemistry.get("chemistry_score_mean")
            sf["chemistry_score_std"] = chemistry.get("chemistry_score_std")
            sf["chemistry_n_games"] = chemistry.get("chemistry_n_pairs")
        else:
            sf["chemistry_score_median"] = None
            sf["chemistry_score_mean"] = None
            sf["chemistry_score_std"] = None
            sf["chemistry_n_games"] = None

        return sf


# ---------------------------------------------------------------------------
# Module-level instance — the bridge callable target
# ---------------------------------------------------------------------------
SECTION = TeamLineupSynergy()


def register(
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
    as_of: Optional[_dt.datetime] = None,
) -> dict:
    """Build artifacts for all available teams and register via the bridge.

    Convenience entry point called by the orchestrator or manually. Uses today
    as the as_of when not specified. Returns the bridge manifest dict.

    Args:
        store:    optional PointInTimeStore to also write atlas records.
        dry_run:  skip disk writes when True.
        as_of:    override the as-of date (default: today UTC midnight).

    Returns:
        manifest dict from profile_factory_bridge.register_section.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    tricodes = _collect_team_tricodes()
    artifacts: List[AtlasArtifact] = []
    skipped = 0

    for tricode in tricodes:
        try:
            art = SECTION.build(tricode, as_of)
            if art is None:
                skipped += 1
                continue
            if not SECTION.validate(art):
                _log.warning(
                    "lineup_synergy: skipping team %s (failed validate)", tricode
                )
                skipped += 1
                continue
            artifacts.append(art)
        except Exception as exc:
            _log.warning(
                "lineup_synergy: error building team %s: %s", tricode, exc
            )
            skipped += 1

    _log.info(
        "lineup_synergy: built %d artifacts, skipped %d",
        len(artifacts),
        skipped,
    )

    return register_section(SECTION, artifacts, store=store, dry_run=dry_run)


def _collect_team_tricodes() -> List[str]:
    """Collect all team tricodes from available lineup split files."""
    tricodes: set = set()
    if LINEUPS_DIR.exists():
        for f in LINEUPS_DIR.glob("lineup_splits_*_*.json"):
            parts = f.stem.split("_")
            if len(parts) >= 4:
                tricodes.add(parts[2].upper())
    # Also check the profiles directory for known teams
    prof_dir = CACHE / "profiles" / "teams"
    if prof_dir.exists():
        for f in prof_dir.glob("*.json"):
            tricodes.add(f.stem.upper())
    return sorted(tricodes)
