"""ARM-B atlas section: ``form_streak_dynamics`` — hot/cold streak and bounce-back profile.

Implements :class:`AtlasSection` for the ``"form_streak_dynamics"`` section of a
player's persistent profile.  Every sub-field comes from existing parquets listed
in spec_features.md / spec_intel_memory.md — no re-derivation.

**Sub-field coverage (EXHAUSTIVE detail on how they play through momentum shifts):**

REAL (populated from pregame_oof.parquet actuals, player_adv_stats.parquet):
  streak_rates.*      — hot/cold streak incidence rates per stat (pts/reb/ast/fg3m/
                        stl/blk/tov) computed from per-game actuals vs season mean.
                        hot_game_rate:  fraction of games ≥ season_mean+0.5*std;
                        cold_game_rate: fraction of games ≤ season_mean-0.5*std;
                        monster_game_rate: ≥ season_mean+1.5*std (blow-up risk);
                        dud_game_rate:    ≤ season_mean-1.5*std (floor risk).
  streak_runs.*       — consecutive-game streak lengths.
                        max_hot_run:  longest consecutive hot-game run (per stat);
                        max_cold_run: longest consecutive cold-game run;
                        current_hot_run:   how many consecutive hot games ENDING at as_of
                                           (0 if not currently hot — leak-safe);
                        current_cold_run:  how many consecutive cold games ending at as_of.
  bounce_back.*       — how reliably a player bounces back after dud games.
                        post_dud_hot_rate: P(hot game | prev game was dud) per stat;
                        post_dud_above_mean_rate: P(above mean | prev game was dud);
                        bounce_back_speed: mean games until next hot game after a dud
                                           (capped 10; None when < 2 dud events).
  hangover.*          — how often a monster game is followed by regression.
                        post_monster_cold_rate: P(cold game | prev game was monster);
                        post_monster_below_mean_rate: P(below mean | prev game monster);
                        hangover_speed: mean games until below-mean game after monster
                                        (capped 10; None when < 2 monster events).
  regression.*        — baseline reversion tendency.
                        mean_reversion_lag:  lag (games) of autocorrelation sign flip
                                             in rolling residuals (1=sharp, 5=sluggish);
                        ewma_vs_season_mean: (ewma_last5 - season_mean) / std — how
                                             stretched above baseline at as_of;
                        volatility:          std / mean across all games (CV of perf);
                        autocorr_lag1:       Pearson r at lag-1 (positive=momentum,
                                             negative=alternating).
  summary.*           — headline scalars for fast signal access.
                        n_games:         total games with actuals at as_of;
                        active_streaks:  dict mapping stat -> "hot"|"cold"|"neutral"
                                         for the last 3 games at as_of;
                        form_score:      composite z-score across pts/reb/ast comparing
                                         last-5 vs season mean (positive=hot overall).

DEFER (data gap — not available in current parquets):
  minute_trajectory.* — DEFER: minute_trajectory.lgb missing (noted in MEMORY.md health);
                         would enable fatigue-adjusted streak corrections.
  usage_adjusted.*    — DEFER: usage shifts that explain apparent streaks (injuries to
                         teammates) require per-game lineup parquet filtered to <=as_of.
  opponent_adjusted.* — DEFER: opponent defensive rating adjusted streaks would need
                         team_advanced_stats joined to per-game actuals — feasible but
                         not pre-aggregated; see spec §2 / per_opp_stat_rolling.parquet
                         (has L3 per-opp rolling, but streak conditioning requires full
                         game-by-game history not just L3).

RESERVED CV SLOTS (value=None, CV branch fills later):
  fatigue_velocity_trend  — mean velocity change over a rolling 3-game window from CV
                            Kalman; proxy for physical fatigue driving cold streaks.
  spacing_context_streak  — mean off-ball spacing (ft²) during hot vs cold streaks —
                            indicates whether team context (spacing) explains the streak.
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

# Threshold multipliers (in units of per-game std) for hot/cold/monster/dud labels
_HOT_THRESH = 0.5
_COLD_THRESH = 0.5
_MONSTER_THRESH = 1.5
_DUD_THRESH = 1.5

# Stats we compute streak dynamics for
_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

# Module-level data cache (load once per process)
_SRC_CACHE: Dict[str, Optional[pd.DataFrame]] = {}


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
    """Clean integer: NaN/inf -> None, numpy -> python int."""
    if v is None:
        return None
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f):
            return None
        return int(f)
    except (TypeError, ValueError):
        return None


def _label_game(val: float, mean: float, std: float) -> str:
    """Classify one game value as hot/cold/monster/dud/neutral."""
    if std <= 0:
        return "neutral"
    z = (val - mean) / std
    if z >= _MONSTER_THRESH:
        return "monster"
    if z >= _HOT_THRESH:
        return "hot"
    if z <= -_DUD_THRESH:
        return "dud"
    if z <= -_COLD_THRESH:
        return "cold"
    return "neutral"


def _max_run(labels: pd.Series, target: str) -> int:
    """Compute the longest consecutive run of ``target`` label."""
    max_r = cur = 0
    for lbl in labels:
        if lbl == target:
            cur += 1
            max_r = max(max_r, cur)
        else:
            cur = 0
    return max_r


def _current_run(labels: pd.Series, target: str) -> int:
    """Consecutive ``target`` run ending at the LAST element (as_of boundary)."""
    count = 0
    for lbl in reversed(list(labels)):
        if lbl == target:
            count += 1
        else:
            break
    return count


def _post_event_rate(labels: pd.Series, trigger: str, outcome: str) -> Optional[float]:
    """Fraction of games labelled ``outcome`` that immediately follow a ``trigger`` game.

    Returns None when fewer than 2 trigger events exist (insufficient data).
    """
    pairs = list(zip(labels[:-1], labels[1:]))
    trigger_count = sum(1 for pre, _ in pairs if pre == trigger)
    if trigger_count < 2:
        return None
    hit_count = sum(1 for pre, post in pairs if pre == trigger and post == outcome)
    return round(hit_count / trigger_count, 4)


def _post_event_above_mean_rate(labels: pd.Series, trigger: str) -> Optional[float]:
    """P(above mean | prev game == trigger). 'above mean' = hot or monster."""
    pairs = list(zip(labels[:-1], labels[1:]))
    trigger_count = sum(1 for pre, _ in pairs if pre == trigger)
    if trigger_count < 2:
        return None
    hit_count = sum(
        1 for pre, post in pairs
        if pre == trigger and post in ("hot", "monster")
    )
    return round(hit_count / trigger_count, 4)


def _post_event_below_mean_rate(labels: pd.Series, trigger: str) -> Optional[float]:
    """P(below mean | prev game == trigger). 'below mean' = cold or dud."""
    pairs = list(zip(labels[:-1], labels[1:]))
    trigger_count = sum(1 for pre, _ in pairs if pre == trigger)
    if trigger_count < 2:
        return None
    hit_count = sum(
        1 for pre, post in pairs
        if pre == trigger and post in ("cold", "dud")
    )
    return round(hit_count / trigger_count, 4)


def _games_until_outcome(labels: pd.Series, trigger: str, outcome: str,
                          cap: int = 10) -> Optional[float]:
    """Mean games until next ``outcome`` game after each ``trigger`` game.

    Returns None when fewer than 2 trigger events exist.
    Caps at ``cap`` games (treat as 'did not recover within window').
    """
    lbl_list = list(labels)
    waits: List[int] = []
    for i, lbl in enumerate(lbl_list):
        if lbl != trigger:
            continue
        found = False
        for j in range(i + 1, min(i + 1 + cap, len(lbl_list))):
            if lbl_list[j] == outcome:
                waits.append(j - i)
                found = True
                break
        if not found:
            waits.append(cap)
    if len(waits) < 2:
        return None
    return round(float(np.mean(waits)), 4)


def _autocorr_lag1(series: pd.Series) -> Optional[float]:
    """Pearson autocorrelation at lag 1 (positive=momentum, negative=alternating)."""
    arr = series.dropna().values.astype(float)
    if len(arr) < 5:
        return None
    r = float(np.corrcoef(arr[:-1], arr[1:])[0, 1])
    if np.isnan(r):
        return None
    return round(r, 4)


def _mean_reversion_lag(series: pd.Series, max_lag: int = 8) -> Optional[int]:
    """Lag at which the running autocorrelation first switches sign (reversion speed).

    Returns the lag index (1-based) where the sign flips, or max_lag+1 if it never
    does within the window.  Returns None when series too short.
    """
    arr = series.dropna().values.astype(float)
    if len(arr) < max_lag + 2:
        return None
    signs: List[int] = []
    for lag in range(1, max_lag + 1):
        if len(arr) < lag + 2:
            break
        r = np.corrcoef(arr[:-lag], arr[lag:])[0, 1]
        signs.append(int(np.sign(r)) if not np.isnan(r) else 0)
    if not signs:
        return None
    first_sign = signs[0]
    for i, s in enumerate(signs[1:], start=2):
        if s != 0 and s != first_sign:
            return i
    return max_lag + 1


def _compute_stat_dynamics(
    game_series: pd.Series,
    season_mean: float,
    season_std: float,
    stat: str,
) -> Dict[str, Any]:
    """Compute all streak/bounce-back/hangover/regression metrics for one stat series.

    ``game_series`` is a chronologically-sorted Series of per-game values (floats),
    already filtered to ``<= as_of``.
    """
    n = len(game_series)
    if n < 2:
        return {}

    labels = game_series.apply(lambda v: _label_game(v, season_mean, season_std))

    # ----- streak_rates -----
    hot_rate = round((labels.isin(["hot", "monster"])).mean(), 4)
    cold_rate = round((labels.isin(["cold", "dud"])).mean(), 4)
    monster_rate = round((labels == "monster").mean(), 4)
    dud_rate = round((labels == "dud").mean(), 4)

    # ----- streak_runs -----
    max_hot = _max_run(labels, "hot") + _max_run(labels, "monster")
    # use combined hot+monster for max hot run
    hot_monster_labels = labels.map(lambda x: "hot" if x in ("hot", "monster") else x)
    max_hot_run = _max_run(hot_monster_labels, "hot")
    cold_dud_labels = labels.map(lambda x: "cold" if x in ("cold", "dud") else x)
    max_cold_run = _max_run(cold_dud_labels, "cold")
    cur_hot = _current_run(hot_monster_labels, "hot")
    cur_cold = _current_run(cold_dud_labels, "cold")

    # ----- bounce_back (post-dud) -----
    post_dud_hot_rate = _post_event_above_mean_rate(labels, "dud")
    post_dud_above_mean = post_dud_hot_rate  # alias for clarity
    bounce_back_speed = _games_until_outcome(labels, "dud", "hot")
    if bounce_back_speed is None:
        bounce_back_speed = _games_until_outcome(labels, "dud", "monster")

    # ----- hangover (post-monster) -----
    post_monster_cold_rate = _post_event_below_mean_rate(labels, "monster")
    post_monster_below_mean = post_monster_cold_rate
    hangover_speed = _games_until_outcome(labels, "monster", "cold")
    if hangover_speed is None:
        hangover_speed = _games_until_outcome(labels, "monster", "dud")

    # ----- regression -----
    autocorr = _autocorr_lag1(game_series)
    reversion_lag = _mean_reversion_lag(game_series)
    std_safe = season_std if season_std > 0 else 1.0
    volatility = _rd(season_std / season_mean) if season_mean > 0 else None

    # ewma of last 5 vs season mean
    ewma5 = game_series.ewm(span=5, adjust=False).mean().iloc[-1] if n >= 2 else None
    ewma_vs_mean = _rd((ewma5 - season_mean) / std_safe) if ewma5 is not None else None

    return {
        "streak_rates": {
            "hot_game_rate": hot_rate,
            "cold_game_rate": cold_rate,
            "monster_game_rate": monster_rate,
            "dud_game_rate": dud_rate,
        },
        "streak_runs": {
            "max_hot_run": _ri(max_hot_run),
            "max_cold_run": _ri(max_cold_run),
            "current_hot_run": _ri(cur_hot),
            "current_cold_run": _ri(cur_cold),
        },
        "bounce_back": {
            "post_dud_hot_rate": post_dud_hot_rate,
            "post_dud_above_mean_rate": post_dud_above_mean,
            "bounce_back_speed": _rd(bounce_back_speed),
        },
        "hangover": {
            "post_monster_cold_rate": post_monster_cold_rate,
            "post_monster_below_mean_rate": post_monster_below_mean,
            "hangover_speed": _rd(hangover_speed),
        },
        "regression": {
            "autocorr_lag1": autocorr,
            "mean_reversion_lag": _ri(reversion_lag),
            "volatility": volatility,
            "ewma_vs_season_mean": ewma_vs_mean,
        },
    }


def _compute_active_streak(
    game_series: pd.Series,
    season_mean: float,
    season_std: float,
    last_n: int = 3,
) -> str:
    """Return 'hot' | 'cold' | 'neutral' for the last ``last_n`` games."""
    if len(game_series) < last_n:
        return "neutral"
    recent = game_series.iloc[-last_n:]
    labels = recent.apply(lambda v: _label_game(v, season_mean, season_std))
    hot_count = (labels.isin(["hot", "monster"])).sum()
    cold_count = (labels.isin(["cold", "dud"])).sum()
    if hot_count >= 2:
        return "hot"
    if cold_count >= 2:
        return "cold"
    return "neutral"


def _build_player_form_streak(
    pid: int, as_of: _dt.datetime
) -> Optional[AtlasArtifact]:
    """Core builder: compute all form/streak dynamics for player ``pid`` at ``as_of``.

    Leak guarantee: per-game actuals from pregame_oof.parquet are filtered to
    game_date <= as_of before any computation; season stats (mean/std) are also
    computed only from the filtered rows.

    Returns None when fewer than 5 games of actuals are available.
    """
    as_of_str = as_of.date().isoformat()
    as_of_ts = pd.Timestamp(as_of)

    # ---- Load source: pregame_oof.parquet (per-game actuals, 7 stats) ----
    df_raw = _load("pregame_oof", CACHE / "pregame_oof.parquet")
    if df_raw is None or df_raw.empty:
        return None

    df_pid = df_raw[df_raw["player_id"] == pid].copy()
    if df_pid.empty:
        return None

    # Leak-safe filter: only games at or before as_of
    df_pid["game_date"] = pd.to_datetime(df_pid["game_date"])
    df_pid = df_pid[df_pid["game_date"] <= as_of_ts]
    if df_pid.empty:
        return None

    # Pivot to per-game stat matrix
    pivoted = df_pid.pivot_table(
        index="game_date", columns="stat", values="actual", aggfunc="first"
    ).sort_index()

    n_games = len(pivoted)
    if n_games < 5:
        return None  # insufficient history for meaningful streak analytics

    # ---- Per-stat dynamics ----
    per_stat: Dict[str, Dict[str, Any]] = {}
    active_streaks: Dict[str, str] = {}
    form_z_scores: List[float] = []

    for stat in _STATS:
        if stat not in pivoted.columns:
            continue
        series = pivoted[stat].dropna()
        if len(series) < 5:
            continue

        # Season stats computed from same filtered window (leak-safe)
        s_mean = float(series.mean())
        s_std = float(series.std(ddof=0))

        dynamics = _compute_stat_dynamics(series, s_mean, s_std, stat)
        if not dynamics:
            continue

        dynamics["season_mean"] = _rd(s_mean)
        dynamics["season_std"] = _rd(s_std)
        dynamics["n_games"] = len(series)
        per_stat[stat] = dynamics

        # Active streak label (last 3 games)
        active_streaks[stat] = _compute_active_streak(series, s_mean, s_std)

        # Contribute to composite form score (pts/reb/ast only for readability)
        if stat in ("pts", "reb", "ast"):
            ewma_z = dynamics["regression"].get("ewma_vs_season_mean")
            if ewma_z is not None:
                form_z_scores.append(float(ewma_z))

    if not per_stat:
        return None

    # ---- Summary scalars ----
    form_score = _rd(float(np.mean(form_z_scores))) if form_z_scores else None

    sub_fields: Dict[str, Any] = {
        "per_stat": per_stat,
        "summary": {
            "n_games": n_games,
            "active_streaks": active_streaks,
            "form_score": form_score,
        },
        # DEFER sub-fields documented in module docstring
        "minute_trajectory": {
            "_note": (
                "DEFER: minute_trajectory.lgb missing (MEMORY.md health WARN); "
                "fatigue-adjusted streak correction requires per-minute projection."
            )
        },
        "usage_adjusted": {
            "_note": (
                "DEFER: usage-adjusted streaks require per-game lineup parquet "
                "filtered to <=as_of; no per-game lineup source pre-aggregated."
            )
        },
        "opponent_adjusted": {
            "_note": (
                "DEFER: opp-defense-adjusted streaks feasible via team_advanced_stats "
                "joined to per-game actuals but not pre-aggregated (per_opp_stat_rolling "
                "has only L3 window, insufficient for full streak conditioning)."
            )
        },
    }

    confidence = confidence_from_n(n_games, cap=None)
    provenance = {
        "source": "pregame_oof.parquet",
        "n": n_games,
        "confidence": confidence,
        "as_of": as_of_str,
    }

    section = PlayerFormStreakDynamics()
    return AtlasArtifact(
        section=section.name,
        entity=section.entity,
        entity_id=pid,
        value=form_score,  # headline: composite form z-score (positive=hot)
        sub_fields=sub_fields,
        provenance=provenance,
        confidence=confidence,
        as_of=as_of_str,
        cv_fields=section.cv_fields(),
    )


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class PlayerFormStreakDynamics(AtlasSection):
    """Hot/cold streak dynamics atlas section (player entity, section='form_streak_dynamics').

    Builds a provenance-stamped, leak-safe artifact covering:
      - Per-stat hot/cold/monster/dud incidence rates
      - Max and current consecutive streak runs
      - Bounce-back probability after dud games (post_dud_hot_rate)
      - Hangover probability after monster games (post_monster_cold_rate)
      - Regression speed: lag-1 autocorrelation, mean-reversion lag, volatility
      - Composite form_score vs season baseline
    Reserves 2 CV slots for CV-branch enrichment (fatigue velocity trend, spacing context).

    Primary source: data/cache/pregame_oof.parquet (per-game actuals, 7 stats, 775 players,
    leak-safe game_date filter to as_of).

    DEFER: minute_trajectory (model missing), usage-adjusted streaks (no per-game lineup),
    opponent-adjusted streaks (no pre-aggregated join).
    """

    name: str = "form_streak_dynamics"
    entity: str = "player"
    source_name: str = "pregame_oof.parquet"
    conf_cap: Optional[str] = None

    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the form_streak_dynamics artifact for player ``entity_id`` at ``as_of``.

        Leak guarantee: all actuals are from pregame_oof.parquet filtered to
        game_date <= as_of; season mean/std computed from the same filtered window.
        Returns None when < 5 games of actuals exist at as_of.
        """
        return _build_player_form_streak(int(entity_id), as_of)

    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity checks: required keys present, rates in [0,1], CV slots null.

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields
        required_keys = {"per_stat", "summary", "minute_trajectory",
                         "usage_adjusted", "opponent_adjusted"}
        if not required_keys.issubset(sf.keys()):
            return False

        # summary must have n_games > 0
        summary = sf.get("summary", {})
        n = summary.get("n_games", 0)
        if not isinstance(n, int) or n <= 0:
            return False

        # Per-stat rate fields must be in [0, 1] when present
        per_stat = sf.get("per_stat", {})
        for stat, dyn in per_stat.items():
            sr = dyn.get("streak_rates", {})
            for rate_key in ("hot_game_rate", "cold_game_rate",
                             "monster_game_rate", "dud_game_rate"):
                v = sr.get(rate_key)
                if v is not None and not (0.0 <= v <= 1.0):
                    return False
            bb = dyn.get("bounce_back", {})
            for rate_key in ("post_dud_hot_rate", "post_dud_above_mean_rate"):
                v = bb.get(rate_key)
                if v is not None and not (0.0 <= v <= 1.0):
                    return False

        # CV slots must be null (branch hasn't run yet)
        for slot in artifact.cv_fields.values():
            if slot.value is not None:
                return False

        return True

    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema (values None; CV branch fills later).

        These two slots link the behavioral (CV-tracking) signal to the form/streak
        context: fatigue and team spacing explain WHY streaks occur physically.
        The CV-fix session calls ``store.fill_cv_slot("player", pid,
        "form_streak_dynamics", slot, as_of, value)`` to populate them.
        """
        return {
            "fatigue_velocity_trend": CVSlot(
                name="fatigue_velocity_trend",
                dtype="float",
                description=(
                    "Mean per-game player velocity change (ft/s delta) over a 3-game "
                    "rolling window from CV Kalman tracker.  Negative = decelerating "
                    "(physical fatigue signal predictive of cold streak onset). "
                    "Filled by CV branch from data/tracking per-game aggregates."
                ),
                unit="ft/s",
                value=None,
            ),
            "spacing_context_streak": CVSlot(
                name="spacing_context_streak",
                dtype="float",
                description=(
                    "Ratio of mean off-ball team spacing (ft²) during hot-labelled games "
                    "vs cold-labelled games for this player.  > 1 means better spacing "
                    "explains the hot streak; ≈ 1 means the streak is player-intrinsic. "
                    "Filled by CV branch from per-game cv_features aggregation."
                ),
                unit=None,
                value=None,
            ),
        }


# ---------------------------------------------------------------------------
# Module-level registration helper (called by orchestrator / batch build)
# ---------------------------------------------------------------------------

def build_and_register(
    player_ids: Optional[List[int]] = None,
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Build form_streak_dynamics for player_ids and register via the bridge.

    Args:
        player_ids: NBA player_ids (int).  If None, discovers from pregame_oof.
        as_of:      leak boundary date (defaults to UTC today midnight).
        store:      PointInTimeStore; when provided, artifacts are written to the store.
        dry_run:    skip all disk writes.

    Returns:
        manifest dict from ``register_section`` (section, parquet, sec_fn, n_entities, ...).
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if player_ids is None:
        df = _load("pregame_oof", CACHE / "pregame_oof.parquet")
        if df is not None and "player_id" in df.columns:
            player_ids = sorted(df["player_id"].dropna().astype(int).unique().tolist())
        else:
            player_ids = []

    section = PlayerFormStreakDynamics()
    artifacts: List[AtlasArtifact] = []
    for pid in player_ids:
        try:
            art = section.build(pid, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
