"""scripts.platformkit.prop_edge_config -- per-SPORT wiring for the prop board.

build_prop_board (prop_edge.py) is sport-DISPATCHED: each supported sport supplies
its own engine fn, gamelog df / parquet path, name resolver, default providers,
calibration-cache path and canonical-stat set. This module is the single registry
of that wiring so prop_edge.py stays sport-blind.

HONESTY (binding): the join key is the player NAME -- a wrong match fabricates a
fake edge -- so each sport's resolver biases to false-negative. No $-edge claims;
calibration is the yardstick (cache absent -> all stats "unmeasured").

Public functions NEVER raise -- they degrade (None df / empty provider list).

NBA offseason honesty: the NBA board returns UNAVAILABLE (not empty-but-green)
when all providers report no lines. Call nba_board_status(sources, n_lines) after
_gather to get the honest board status string for the NBA sport key.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_prop_edge_config.py -q
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Board-level honest framing (sport-agnostic). The soccer-only levers (dispersion /
# club priors / opponent multiplier) apply ONLY on the soccer board; MLB rows carry
# null opp_mult/dispersion_phi and instead project exposure inside the MLB engine.
HONEST_NOTE = (
    "CANDIDATE edges vs soft sportsbook / DFS pick'em lines. Priced rows = EV vs that "
    "soft price (not beat-the-close); pick'em rows = gap from 0.5. Sharp mainlines are "
    "efficient; CLV judges; paper / decision-support only. soccer_intl lam is NB-widened "
    "by a leak-free per-stat dispersion index (a too-tight Poisson FABRICATES tail edges) "
    "and opponent-adjusted by a leak-free team_defense multiplier (1.0 when unmappable); "
    "club-season priors lift thin players. MLB lam = leak-free per-exposure rate x "
    "PROJECTED exposure (PA/BF), the engine modelling its own width. ev_flag "
    "'uncalibrated_thin' / 'implausible' rows rank BELOW reliable ones. TIERED by OUR "
    "OWN out-of-sample calibration: each edge carries oos_bss/oos_n + a calibration label "
    "(proven/marginal/weak/unmeasured). 'weak' stats are ones we MEASURED no / negative "
    "skill on (shown but DEMOTED); 'proven' (tier CALIBRATION_PROVEN) means OOS-calibrated "
    "on real results -- ranks first but is NOT a profit / CLV claim. Cache absent -> all "
    "'unmeasured', prior order restored."
)


@dataclass
class SportPropConfig:
    """Everything build_prop_board needs to price one sport's props.

    engine_distribution(df, player_id, stat_canonical, as_of, **kw) -> dist dict
        with status/lam/p_over (the per-sport prop engine).
    resolve_player(df, raw_name, *, team, index) / build_name_index(df) -- the
        per-sport name resolver (bias to false-negative).
    parquet_path -- gamelog parquet (read when df not injected).
    default_providers() -- live prop sources for this sport.
    calibration_path -- MEASURED OOS cache (absent -> all "unmeasured").
    canonical_stats -- set of canonical stat names the engine can price; a line
        whose canon stat is outside this set is left unresolved (never guessed).
    supports_dispersion / supports_opp_mult -- soccer-only levers (MLB engine
        projects exposure + width itself; those kwargs are NOT passed for MLB).
    """

    sport: str
    engine_distribution: Callable[..., Dict[str, Any]]
    resolve_player: Callable[..., Dict[str, Any]]
    build_name_index: Callable[[Any], Any]
    parquet_path: str
    default_providers: Callable[[], List[Any]]
    calibration_path: str
    canonical_stats: frozenset
    supports_dispersion: bool = False
    supports_opp_mult: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)


def _soccer_config() -> SportPropConfig:
    """soccer_intl wiring (unchanged behavior -- the original board path)."""
    from domains.soccer import prop_engine as _se
    from domains.soccer.player_resolver import build_name_index, resolve_player
    from scripts.platformkit.odds_provider.prop_prizepicks import PrizePicksProvider
    from scripts.platformkit.odds_provider.prop_underdog import UnderdogProvider
    from scripts.platformkit import prop_tiering

    return SportPropConfig(
        sport="soccer_intl",
        engine_distribution=_se.prop_distribution,
        resolve_player=resolve_player,
        build_name_index=build_name_index,
        parquet_path=os.path.join(
            "data", "domains", "soccer", "espn_player_stats.parquet"),
        default_providers=lambda: [UnderdogProvider(), PrizePicksProvider()],
        calibration_path=prop_tiering.CALIBRATION_PATH,
        canonical_stats=frozenset(),  # soccer accepts any canon stat (legacy)
        supports_dispersion=True,
        supports_opp_mult=True,
    )


def _mlb_config() -> SportPropConfig:
    """MLB wiring: prop_engine_mlb + player_resolver_mlb + MLB_CANON + MLB cache.

    The MLB engine PROJECTS exposure itself (exposure=None) and models its own
    width, so the soccer dispersion / opponent levers are OFF for MLB.
    """
    from domains.mlb import prop_engine_mlb as _me
    from domains.mlb.player_resolver_mlb import build_name_index, resolve_player
    from domains.mlb.player_rates_mlb import MLB_CANON
    from scripts.platformkit.odds_provider.prop_prizepicks import PrizePicksProvider
    from scripts.platformkit.odds_provider.prop_underdog import UnderdogProvider
    from scripts.platformkit.props_eval_mlb import CALIBRATION_PATH_MLB

    return SportPropConfig(
        sport="mlb",
        engine_distribution=_me.prop_distribution,
        resolve_player=resolve_player,
        build_name_index=build_name_index,
        parquet_path=os.path.join(
            "data", "domains", "mlb", "player_gamelogs.parquet"),
        default_providers=lambda: [UnderdogProvider(), PrizePicksProvider()],
        calibration_path=CALIBRATION_PATH_MLB,
        canonical_stats=frozenset(MLB_CANON.keys()),
        supports_dispersion=False,
        supports_opp_mult=False,
    )


def _nba_config() -> SportPropConfig:
    """NBA wiring: DFS-only prop board (Underdog BASKETBALL + PrizePicks NBA).

    NBA prop lines from both providers are EMPTY in the NBA off-season; they will
    auto-populate when lines post (both providers are already wired for NBA by
    sport_id). No NBA prop_engine exists (the domain engine lives in the human-
    gated src/ tree), so engine_distribution raises NotImplementedError -- callers
    (build_prop_board) must handle that honestly and degrade to UNAVAILABLE for
    the model-probability column while still surfacing the raw lines.

    This config wires the PROVIDER layer (sources + prop lines) only. No calibration
    cache exists for NBA (calibration_path points to a path that may be absent;
    get_config callers must treat a missing cache as "all unmeasured").

    canonical_stats: NBA prop stats from DFS providers (PTS/REB/AST/STL/BLK/3PM).
    supports_dispersion / supports_opp_mult: False (no NBA prop engine yet).
    """
    from scripts.platformkit.odds_provider.prop_prizepicks import PrizePicksProvider
    from scripts.platformkit.odds_provider.prop_underdog import UnderdogProvider

    # NBA canonical stat set from the DFS providers (normalized via canon_stat).
    # Kept as a lightweight frozenset -- no domain engine import needed here.
    _NBA_CANON = frozenset({
        "Points", "Rebounds", "Assists", "Steals", "Blocks",
        "3-PT Made", "Turnovers", "Fantasy Score",
        "Pts+Reb+Ast", "Pts+Reb", "Pts+Ast", "Reb+Ast",
    })

    def _nba_engine(*_args: object, **_kw: object) -> dict:
        raise NotImplementedError(
            "NBA prop_engine not available outside human-gated src/; "
            "degrade model column to UNAVAILABLE for NBA props."
        )

    def _nba_resolve(*_args: object, **_kw: object) -> dict:
        return {"status": "unavailable"}

    def _nba_name_index(_df: object) -> None:
        return None

    return SportPropConfig(
        sport="nba",
        engine_distribution=_nba_engine,
        resolve_player=_nba_resolve,
        build_name_index=_nba_name_index,
        parquet_path=os.path.join(
            "data", "domains", "basketball_nba", "player_gamelogs.parquet"),
        default_providers=lambda: [UnderdogProvider(), PrizePicksProvider()],
        calibration_path=os.path.join(
            "data", "cache", "props_eval_nba_calibration.json"),
        canonical_stats=_NBA_CANON,
        supports_dispersion=False,
        supports_opp_mult=False,
        extra={"offseason_empty": True},
    )


# sport key -> zero-arg factory (lazy so a missing domain never breaks the others).
_FACTORIES: Dict[str, Callable[[], SportPropConfig]] = {
    "soccer_intl": _soccer_config,
    "mlb": _mlb_config,
    "nba": _nba_config,
}


def supported_sports() -> List[str]:
    """Sport keys with a registered prop-board config."""
    return list(_FACTORIES.keys())


def get_config(sport: str) -> Optional[SportPropConfig]:
    """Build the SportPropConfig for *sport*, or None when unsupported / the domain
    fails to import. NEVER raises."""
    fac = _FACTORIES.get((sport or "").lower())
    if fac is None:
        return None
    try:
        return fac()
    except Exception as exc:  # noqa: BLE001 -- a broken domain must not raise
        logger.warning("prop config for %s failed to build: %s", sport, exc)
        return None


def nba_board_status(sources: Dict[str, str], n_lines: int) -> str:
    """Honest board status string for the NBA prop board.

    Called by build_prop_board after _gather to decide the top-level status key.
    Returns "unavailable_offseason" when ALL providers returned no lines (the NBA
    off-season case) so callers surface an honest UNAVAILABLE rather than an
    empty-but-green "ok" card.  Returns "ok" when at least one line came through.

    Never raises -- unexpected input falls through to "ok" (conservative: better
    to show an empty board than to hide a live slate).

    Args:
        sources: the {provider_name: status_string} map from _gather.  A provider
            that returned rows has status "ok (N rows)"; one that returned the
            UNAVAILABLE sentinel has a non-ok string (e.g. "unavailable: ...").
        n_lines: total PropLine count gathered from all providers.
    """
    try:
        if n_lines > 0:
            return "ok"
        # All providers returned empty or UNAVAILABLE -> offseason.
        return "unavailable_offseason"
    except Exception:  # noqa: BLE001 -- must never raise
        return "ok"


def providers_for_sport(sport: str) -> List[Any]:
    """Return the default provider list for *sport* ([] when unsupported). Never raises.

    Convenience so callers that want ONLY the providers (e.g. a health probe) do not
    need to build the full SportPropConfig.
    """
    cfg = get_config(sport)
    if cfg is None:
        return []
    try:
        return cfg.default_providers()
    except Exception as exc:  # noqa: BLE001
        logger.warning("providers_for_sport(%s) failed: %s", sport, exc)
        return []


__all__ = [
    "SportPropConfig",
    "get_config",
    "supported_sports",
    "nba_board_status",
    "providers_for_sport",
    "HONEST_NOTE",
]
