"""Signal: scheme_matchup_scoring — interaction of player shot-profile vs opponent defensive scheme.

**Basketball Hypothesis**
A player's scoring output is determined not just by their raw production but by how
well their *shot-creation style* exploits—or is suppressed by—the opponent's specific
*defensive scheme*.  A rim-attacking drive-heavy player facing a Paint-First / no-rim-
protection defense has a meaningful positive edge; the same player facing a
rim-protecting PAINT-FIRST scheme with a high ``paint_protection_score`` should
regress.  Conversely, a perimeter catch-and-shoot player faces a positive environment
against DROP COVERAGE (which concedes open threes on pick-and-roll) and a negative
environment against PERIMETER DENIAL (which suppresses catch-and-shoot opportunities).

**Operationalization**
For player P facing opponent OPP on decision date D, the signal scores five
interaction dimensions and combines them into a composite adjustment:

1. RIM_ATTACK: player drive_count_pg × drive_fg_pct interacted with
   opponent ``paint_protection_score`` (low score = weak rim protection = positive edge).

2. CATCH_SHOOT: player catch_shoot_fga_pg × catch_shoot_efg_pct interacted with
   opponent ``perimeter_denial_score`` (high = more pressure = negative edge) and
   opponent ``opp_catch_shoot_allowed_pct_z`` (positive z = allows more = positive edge).

3. ISO_CREATION: player iso_poss_pg (from pbp_context) interacted with
   opponent ``iso_force_score`` (high = forces iso = positive for good iso scorers).

4. PNR_HANDLER: player pnr_handler_pg interacted with opponent ``drop_score``
   (high drop_score = team plays drop coverage = open pull-up threes = positive).

5. QUALITY_PENALTY: opponent ``quality_z`` (overall defensive quality) applied as
   a uniform shrinkage on the composite.

Each dimension is normalized around 0; the composite is the sum divided by the number
of non-null dimensions, producing a dimensionless score in roughly (−2.0, +2.0).
Positive = player's style exploits the opponent scheme; negative = suppressed.

Returns ``None`` when neither the shot_profile atlas nor the defensive_scheme atlas
is available in the store for the decision context.

**Data sources (atlas reads via the store — leak-safe)**
1. Player ``shot_profile`` atlas section (ARM-B, ``intel/player_shot_profile.py``).
   Fields read: ``creation.drive_count_pg``, ``creation.drive_fg_pct``,
   ``creation.catch_shoot_fga_pg``, ``creation.catch_shoot_efg_pct``,
   ``context.pnr_handler_pg``, ``context.iso_poss_pg`` (pbp_context).
2. Opponent team ``defensive_scheme`` atlas section (ARM-B, ``intel/team_defensive_scheme.py``).
   Fields read: ``scheme_axes.paint_protection_score``, ``scheme_axes.perimeter_denial_score``,
   ``scheme_axes.iso_force_score``, ``scheme_axes.drop_score``,
   ``scheme_axes.quality_z``, ``perimeter_pressure.opp_catch_shoot_allowed_pct_z``.

Fallback (no atlas available): reads raw parquets directly (playtypes_2025-26.parquet /
player_tracking_2025-26.parquet, defensive_schemes.parquet) for the same sub-fields,
so the signal degrades gracefully even before the ARM-B build has run.

**Leak safety**
All store reads use ``as_of=ctx.decision_time`` (enforced by PointInTimeStore).
Raw parquet fallbacks are season-aggregate (pre-published summaries); no per-game data
is read directly (no game_date filter needed for season-level aggregates).

**Gate expectations**
Interaction features are well-known in sports analytics (matchup-specific scheme
exploitation is priced by sharp sportsbooks). Expected verdict: SHIP on pts with a
4/4 WF positive delta; possibly VARIANCE_ONLY if scheme label granularity is too coarse
to beat the existing ``opp_def_pts`` + ``opp_def_rtg`` features already in the model.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.loop.signal import AsOfContext, Hypothesis, Signal, SignalValue
from src.loop.store import entity_key

# ---------------------------------------------------------------------------
# Repository root (script-relative; portable to RunPod Linux)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_DATA = _ROOT / "data"
_INTEL = _DATA / "intelligence"

# ---------------------------------------------------------------------------
# Fallback parquet paths (used when the atlas is not yet in the store)
# ---------------------------------------------------------------------------
_TRACKING_PATHS = [
    _DATA / "player_tracking_2025-26.parquet",
    _DATA / "player_tracking.parquet",
]
_PLAYTYPES_PATHS = [
    _DATA / "playtypes_2025-26.parquet",
    _DATA / "playtypes.parquet",
]
_DEF_SCHEMES_PATH = _INTEL / "defensive_schemes.parquet"

# Module-level lazy cache for raw fallback parquets (avoid repeated disk I/O)
_PARQUET_CACHE: Dict[str, Optional[pd.DataFrame]] = {}


def _load_parquet(key: str, path: Path) -> Optional[pd.DataFrame]:
    """Load a parquet file once per process; cache None on missing/error."""
    if key not in _PARQUET_CACHE:
        try:
            _PARQUET_CACHE[key] = pd.read_parquet(path) if path.exists() else None
        except Exception:
            _PARQUET_CACHE[key] = None
    return _PARQUET_CACHE[key]


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


# ---------------------------------------------------------------------------
# Fallback: raw parquet reads (when store atlas is absent)
# ---------------------------------------------------------------------------

def _player_shot_profile_fallback(pid: int) -> Dict[str, Any]:
    """Extract shot-creation fields directly from tracking + playtypes parquets.

    Used when the ``shot_profile`` atlas section is not yet in the store.
    Season-aggregate parquets are pre-published summaries; no game_date filter
    needed (no per-game leak risk for season-level values).

    Returns:
        Dict with keys drive_count_pg, drive_fg_pct, catch_shoot_fga_pg,
        catch_shoot_efg_pct, pnr_handler_pg (may be partial / values None).
    """
    out: Dict[str, Any] = {}

    # Tracking: drive and catch-and-shoot stats
    for path in _TRACKING_PATHS:
        key = str(path)
        df = _load_parquet(key, path)
        if df is None or df.empty:
            continue
        rows = df[df["player_id"] == pid]
        if rows.empty:
            continue
        if "season" in rows.columns:
            rows = rows.sort_values("season", ascending=False)
        row = rows.iloc[0]
        out["drive_count_pg"] = _rd(row.get("trk_drv_count"))
        out["drive_fg_pct"] = _rd(row.get("trk_drv_fg_pct"))
        out["catch_shoot_fga_pg"] = _rd(row.get("trk_cs_fga"))
        out["catch_shoot_efg_pct"] = _rd(row.get("trk_cs_efg_pct"))
        break  # use first non-empty source

    # Playtypes: PnR handler freq as proxy for pnr_handler_pg
    for path in _PLAYTYPES_PATHS:
        key = str(path)
        df = _load_parquet(key, path)
        if df is None or df.empty:
            continue
        rows = df[(df["player_id"] == pid) & (df.get("play_type", pd.Series()) == "PRBallHandler")]
        if rows.empty:
            # Try column-based filter for DataFrames where play_type is a column
            if "play_type" in df.columns:
                rows = df[(df["player_id"] == pid) & (df["play_type"] == "PRBallHandler")]
        if not rows.empty:
            if "freq_pct" in rows.columns:
                out["pnr_handler_freq_pct"] = _rd(rows["freq_pct"].iloc[0])
        break

    return out


def _opp_scheme_fallback(opp: str) -> Dict[str, Any]:
    """Extract defensive scheme axis scores directly from defensive_schemes.parquet.

    Used when the ``defensive_scheme`` atlas section is not yet in the store.

    Returns:
        Dict with keys paint_protection_score, perimeter_denial_score,
        iso_force_score, drop_score, quality_z (may be partial / values None).
    """
    df = _load_parquet("def_schemes", _DEF_SCHEMES_PATH)
    if df is None or df.empty:
        return {}
    rows = df[df["team"] == opp]
    if rows.empty:
        return {}
    row = rows.iloc[0]
    return {
        "paint_protection_score": _rd(row.get("paint_protection_score")),
        "perimeter_denial_score": _rd(row.get("perimeter_denial_score")),
        "iso_force_score": _rd(row.get("iso_force_score")),
        "drop_score": _rd(row.get("drop_score")),
        "quality_z": _rd(row.get("quality_z")),
    }


# ---------------------------------------------------------------------------
# Interaction scoring helpers
# ---------------------------------------------------------------------------

def _safe_get(d: Optional[Dict[str, Any]], *keys: str) -> Optional[float]:
    """Walk a nested dict by dotted keys, return cleaned float or None."""
    if d is None:
        return None
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return _rd(cur)


def _score_rim_attack(
    drive_count_pg: Optional[float],
    drive_fg_pct: Optional[float],
    paint_protection_score: Optional[float],
) -> Optional[float]:
    """Rim-attack interaction: player drive volume × drive efficiency vs rim protection.

    A high drive_count_pg and strong drive_fg_pct against a weak rim-protection
    team (low paint_protection_score) produces a positive score.

    Score = drive_strength_z × (1 - paint_protection_score)

    where drive_strength_z is a crude standardization of drive_count_pg × drive_fg_pct
    anchored to typical league values (drive_count_pg ~ 4, drive_fg_pct ~ 0.55).

    Returns value in approximately (−2, +2); None if any input is None.
    """
    if drive_count_pg is None or drive_fg_pct is None or paint_protection_score is None:
        return None
    # Drive strength: normalize relative to a typical strong driver
    # Typical league mean: ~4 drives/game at ~0.55 FG%; strong driver: ~8 drives at 0.60%.
    drive_strength = (drive_count_pg * drive_fg_pct) / (4.0 * 0.55)
    # paint_protection_score is [0, 1]; 1 = elite rim protection, 0 = none.
    # Interaction: high strength × low protection = positive edge.
    interaction = (drive_strength - 1.0) * (1.0 - paint_protection_score)
    return round(interaction, 4)


def _score_catch_shoot(
    cs_fga_pg: Optional[float],
    cs_efg_pct: Optional[float],
    perimeter_denial_score: Optional[float],
    opp_cs_allowed_z: Optional[float],
) -> Optional[float]:
    """Catch-and-shoot interaction: player C&S volume × efficiency vs perimeter defense.

    High C&S volume and efficiency against a DROP COVERAGE (low perimeter_denial_score)
    and a team that allows above-average catch-and-shoot attempts (opp_cs_allowed_z > 0)
    produce a positive score.

    Score = cs_strength_z × (1 - perimeter_denial_score) + 0.3 × opp_cs_allowed_z

    Returns value in approximately (−2, +2); None when no C&S inputs are available.
    """
    if cs_fga_pg is None and opp_cs_allowed_z is None:
        return None
    score = 0.0
    n_terms = 0

    if cs_fga_pg is not None and cs_efg_pct is not None and perimeter_denial_score is not None:
        # Typical strong shooter: ~5 C&S FGA/g at ~0.55 eFG%
        cs_strength = (cs_fga_pg * cs_efg_pct) / (5.0 * 0.55)
        score += (cs_strength - 1.0) * (1.0 - perimeter_denial_score)
        n_terms += 1

    if opp_cs_allowed_z is not None:
        # opp_cs_allowed_z > 0 means the team allows MORE catch-and-shoot than league avg
        score += 0.3 * opp_cs_allowed_z
        n_terms += 1

    return round(score / max(n_terms, 1), 4) if n_terms > 0 else None


def _score_iso(
    iso_poss_pg: Optional[float],
    iso_force_score: Optional[float],
) -> Optional[float]:
    """ISO interaction: player isolation volume vs opponent ISO-force scheme.

    Teams with a high ``iso_force_score`` funnel opponents into isolation situations;
    skilled iso scorers benefit, weak iso scorers are punished.

    Score = (iso_poss_pg - 2.0) / 3.0 × iso_force_score

    Typical iso_poss_pg league mean: ~2/game; elite: ~5/game.
    Returns value in approximately (−1, +2); None if any input is None.
    """
    if iso_poss_pg is None or iso_force_score is None:
        return None
    iso_excess = (iso_poss_pg - 2.0) / 3.0  # z-score-like: 0 = average, 1 = strong
    interaction = iso_excess * iso_force_score
    return round(interaction, 4)


def _score_pnr_handler(
    pnr_handler_pg: Optional[float],
    drop_score: Optional[float],
) -> Optional[float]:
    """PnR handler interaction: player PnR volume vs opponent drop-coverage rate.

    A team with high ``drop_score`` sags on pick-and-rolls, conceding mid-range and
    pull-up three opportunities. Heavy PnR ball-handlers gain a positive edge.

    Score = (pnr_handler_pg - 3.0) / 3.0 × drop_score

    Typical pnr_handler_pg league mean: ~3/game; elite handler: ~6/game.
    Returns value in approximately (−1, +2); None if any input is None.
    """
    if pnr_handler_pg is None or drop_score is None:
        return None
    pnr_excess = (pnr_handler_pg - 3.0) / 3.0
    interaction = pnr_excess * drop_score
    return round(interaction, 4)


def _quality_shrinkage(composite: float, quality_z: Optional[float]) -> float:
    """Apply opponent overall defensive quality as a uniform shrinkage.

    A higher ``quality_z`` (better defense overall) compresses positive edges and
    expands negative ones: excellent defenses partially neutralize style advantages.

    Shrinkage factor: 1 - 0.1 × quality_z (clamped to [0.5, 1.3]).
    This means a +2 quality_z defense reduces positive edges by ~20%;
    a −2 quality_z defense (poor D) amplifies edges by ~20%.
    """
    if quality_z is None:
        return composite
    shrink = max(0.5, min(1.3, 1.0 - 0.1 * quality_z))
    return round(composite * shrink, 4)


# ---------------------------------------------------------------------------
# Main signal class
# ---------------------------------------------------------------------------

class SchemeMatchupScoringSignal(Signal):
    """Interaction score: player shot-profile style vs opponent defensive scheme.

    Reads the player's ``shot_profile`` atlas section and the opponent's
    ``defensive_scheme`` atlas section from the point-in-time store (leak-safe),
    then computes four scheme-specific interaction dimensions and combines them
    into a scalar adjustment to the PTS baseline:

      rim_attack    — drive volume/efficiency vs paint protection weakness
      catch_shoot   — C&S volume/efficiency vs perimeter denial + allowance
      iso           — isolation frequency vs opponent's iso-force tendency
      pnr_handler   — PnR handler volume vs opponent drop coverage rate

    The composite is quality-shrunk by the opponent's overall defensive quality_z.

    Falls back to raw parquet reads (playtypes_2025-26, player_tracking_2025-26,
    defensive_schemes) when the atlas sections are not yet in the store.

    Returns None when no player shot-profile information is available (all four
    interaction dimensions are None).
    """

    name: str = "scheme_matchup_scoring"
    target: str = "pts"
    scope: str = "pregame"
    reads_atlas: List[str] = ["shot_profile", "defensive_scheme"]
    emits: List[str] = []  # scalar composite signal

    def build(self, ctx: AsOfContext) -> SignalValue:
        """Compute the leak-safe scheme-matchup composite for ctx.player_id vs ctx.opp.

        Atlas reads are bounded by ctx.decision_time via the PointInTimeStore leak-safe
        contract.  Raw parquet fallbacks use season-aggregate summaries (no per-game
        read; no leak risk).

        Returns:
            float composite in approximately (−2, +2), positive = style advantage
            vs the opponent scheme; or None when all interaction dimensions are None.
        """
        if ctx.player_id is None or ctx.opp is None:
            return None

        pid = int(ctx.player_id)
        opp = str(ctx.opp)
        dt = ctx.decision_time

        # ---- 1. Read player shot_profile from store (prefer) or fallback parquet ----
        # Use store.read_atlas directly (PointInTimeStore API) for correct entity namespacing.
        player_atlas: Optional[Dict[str, Any]] = None
        if self.store is not None:
            raw = self.store.read_atlas("player", pid, "shot_profile", dt)
            if isinstance(raw, dict):
                player_atlas = raw

        if player_atlas is not None:
            creation = player_atlas.get("creation") or {}
            context_d = player_atlas.get("context") or {}
            drive_count_pg = _rd(creation.get("drive_count_pg"))
            drive_fg_pct = _rd(creation.get("drive_fg_pct"))
            cs_fga_pg = _rd(creation.get("catch_shoot_fga_pg"))
            cs_efg_pct = _rd(creation.get("catch_shoot_efg_pct"))
            pnr_handler_pg = _rd(context_d.get("pnr_handler_pg"))
            iso_poss_pg = _rd(context_d.get("iso_poss_pg"))
        else:
            # Fallback: read from raw parquets directly
            fb = _player_shot_profile_fallback(pid)
            drive_count_pg = fb.get("drive_count_pg")
            drive_fg_pct = fb.get("drive_fg_pct")
            cs_fga_pg = fb.get("catch_shoot_fga_pg")
            cs_efg_pct = fb.get("catch_shoot_efg_pct")
            pnr_handler_pg = None  # not available from fallback
            iso_poss_pg = None     # not available from fallback

        # ---- 2. Read opponent defensive_scheme from store (prefer) or fallback ----
        opp_atlas: Optional[Dict[str, Any]] = None
        if self.store is not None:
            raw_opp = self.store.read_atlas("team", opp, "defensive_scheme", dt)
            if isinstance(raw_opp, dict):
                opp_atlas = raw_opp

        if opp_atlas is not None:
            scheme_axes = opp_atlas.get("scheme_axes") or {}
            pp = opp_atlas.get("perimeter_pressure") or {}
            paint_protection_score = _rd(scheme_axes.get("paint_protection_score"))
            perimeter_denial_score = _rd(scheme_axes.get("perimeter_denial_score"))
            iso_force_score = _rd(scheme_axes.get("iso_force_score"))
            drop_score = _rd(scheme_axes.get("drop_score"))
            quality_z = _rd(scheme_axes.get("quality_z"))
            opp_cs_allowed_z = _rd(pp.get("opp_catch_shoot_allowed_pct_z"))
        else:
            # Fallback: raw defensive_schemes.parquet
            fb_opp = _opp_scheme_fallback(opp)
            paint_protection_score = fb_opp.get("paint_protection_score")
            perimeter_denial_score = fb_opp.get("perimeter_denial_score")
            iso_force_score = fb_opp.get("iso_force_score")
            drop_score = fb_opp.get("drop_score")
            quality_z = fb_opp.get("quality_z")
            opp_cs_allowed_z = None  # only available in the full atlas

        # ---- 3. Compute four interaction dimensions ----
        rim = _score_rim_attack(drive_count_pg, drive_fg_pct, paint_protection_score)
        cs = _score_catch_shoot(cs_fga_pg, cs_efg_pct, perimeter_denial_score, opp_cs_allowed_z)
        iso = _score_iso(iso_poss_pg, iso_force_score)
        pnr = _score_pnr_handler(pnr_handler_pg, drop_score)

        # If all dimensions are None, we have no signal — return None
        dims = [d for d in [rim, cs, iso, pnr] if d is not None]
        if not dims:
            return None

        # ---- 4. Composite = mean of non-null dimensions, then quality shrinkage ----
        composite = sum(dims) / len(dims)
        composite = _quality_shrinkage(composite, quality_z)

        return composite

    def hypothesis(self) -> Hypothesis:
        """Return the basketball hypothesis this signal tests."""
        return Hypothesis(
            name=self.name,
            target=self.target,
            scope=self.scope,
            statement=(
                "A player's scoring output is determined not just by their raw ability "
                "but by how well their shot-creation *style* exploits—or is suppressed "
                "by—the specific defensive scheme they face. A rim-attacking driver vs a "
                "no-rim-protection scheme, or a catch-and-shoot specialist vs a DROP "
                "COVERAGE team, produces a systematic positive edge beyond what "
                "opponent-average defensive-rating features capture. Conversely, an iso "
                "scorer facing a wall-heavy defense or a C&S shooter facing PERIMETER "
                "DENIAL should regress below the naive baseline."
            ),
            rationale=(
                "The existing model features ``opp_def_pts`` and ``opp_def_rtg`` use "
                "team-average defensive metrics aggregated across all play types.  They "
                "cannot distinguish a team whose weakness is specifically at the rim (high "
                "paint attempts allowed) from one whose weakness is on the perimeter "
                "(high catch-and-shoot allowed rate).  The ARM-B ``defensive_scheme`` "
                "atlas (intel/team_defensive_scheme.py) decomposes each team's defense "
                "into five axis scores (paint_protection, perimeter_denial, iso_force, "
                "drop_score, quality_z) from defensive_schemes.parquet + "
                "scheme_indicators.json.  The ``shot_profile`` atlas (intel/player_shot_profile.py) "
                "maps each player's drive/C&S/PnR/iso frequencies.  The interaction "
                "between these two surfaces — e.g., drive_count_pg × (1 - paint_protection_score) "
                "— should explain residuals in the pts model that neither atlas alone captures. "
                "Four interaction dimensions are computed independently and averaged, "
                "then shrunk by overall defensive quality_z to avoid overweighting "
                "schematic edges for elite defenses."
            ),
            source="seed",
            atlas_fields=["shot_profile", "defensive_scheme"],
            expected_verdict="SHIP",
            priority="P2",
        )
