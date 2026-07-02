"""scripts.platformkit.ingame.ingame_sp_shadow -- SHADOW-ONLY SP-adjusted in-game prob.

Logs (never trades) an SP-adjusted variant of the served in-game model_prob so a later
offline pass can compare the two against the devigged live price / outcome, honestly,
before anyone considers execution. Reuses domains/mlb/sp_adjust_current.py's leak-free
current-era SP form (build_current_sp_form) and the historical-fit adjust_win_prob()
params recorded in data/domains/mlb/sp_adjust_verdict.json
(forward_eval_2026.variant_a_historical_fit: w, sp_mean, sp_std -- fully OOS on 2026).

HONESTY NOTE (binding): sp_adjust_current's offset was fit as a PREGAME adjustment to a
pregame Elo prior. Applying it here to an IN-GAME repriced probability is an
APPROXIMATION -- the prior's SP-quality weight should really decay as the game
progresses (a starter's expected edge matters less once he's been pulled, or once
several innings of in-game evidence have accumulated), and this module does no such
decay. That mismatch is exactly why this is SHADOW-ONLY: the logged (model_prob,
model_prob_sp_shadow, devigged_price) triples let a later offline pass see whether the
SP offset helps EARLY in a game (closer to its pregame-fit regime) and hurts LATE
(where in-game evidence should have already dominated it) -- BEFORE anyone touches the
live decision path. No claim is made here that it helps; it is a measurement only.

SAFETY CONTRACT (binding):
  1. NEVER changes model_prob, the edge signal, or any bet/decision -- shadow_prob() is
     a pure side-computation; its only consumer is one ADDITIONAL logged field.
  2. Every path is wrapped so ANY exception yields None (+ one-time debug log), never a
     raised error into the capture path.
  3. Missing inputs (no probables for the game, no SP form for either side, sport !=
     mlb) -> None. Honest absence, never a guess.

INVARIANTS: scripts/platformkit/ingame/ only; <=300 LOC; ASCII only; no writes; reads
data/domains/mlb/*.parquet + sp_adjust_verdict.json (read-only, best-effort). Never
imports src/kernel/api. Calibration measurement only -- no $ / edge claim.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_sp_shadow.py -q
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_VERDICT_PATH = _REPO_ROOT / "data" / "domains" / "mlb" / "sp_adjust_verdict.json"
_PROBABLES_PATH = _REPO_ROOT / "data" / "domains" / "mlb" / "probables.parquet"
_GAMELOGS_PATH = _REPO_ROOT / "data" / "domains" / "mlb" / "player_gamelogs.parquet"

STALE_AFTER_SEC = 6.0 * 3600.0  # rebuild the cached slate/form after 6h


def _resolve_team(name: str) -> Optional[str]:
    """Best-effort team-name resolution via domains.mlb.team_name_resolver. None on any miss
    (including if the resolver itself cannot be imported)."""
    try:
        from domains.mlb.team_name_resolver import resolve
        return resolve(name)
    except Exception as exc:  # noqa: BLE001 -- resolution failure is an honest miss
        logger.debug("ingame_sp_shadow team resolve failed for %r: %s", name, exc)
        return None


class SpShadow:
    """Lazy, once-per-process SP-shadow prober. Caches the current slate's per-game
    sp_diff_ew keyed by (home_key, away_key) AND by game_pk; rebuilds if stale (>6h) or
    if never successfully built. A broken build leaves the instance permanently
    None-returning for shadow_prob (logged once), never raising into the capture loop.

    Optional constructor args exist ONLY to make the class hermetically testable
    (fake frames / params / clock) -- production code should use module-level
    get_shadow(), which always uses the real files and wall clock.
    """

    def __init__(self, *, verdict_path: Optional[Path] = None,
                probables_path: Optional[Path] = None,
                gamelogs_path: Optional[Path] = None,
                gamelogs_df: Any = None, probables_df: Any = None,
                params: Optional[Tuple[float, float, float]] = None,
                clock: Optional[Any] = None) -> None:
        self._verdict_path = verdict_path or _VERDICT_PATH
        self._probables_path = probables_path or _PROBABLES_PATH
        self._gamelogs_path = gamelogs_path or _GAMELOGS_PATH
        self._inject_gamelogs = gamelogs_df
        self._inject_probables = probables_df
        self._inject_params = params
        self._clock = clock or (lambda: time.time())
        self._by_teams: Dict[Tuple[str, str], float] = {}
        self._by_pk: Dict[int, float] = {}
        self._params: Optional[Tuple[float, float, float]] = None
        self._built_at: Optional[float] = None
        self._broken = False
        self._warned = False

    def _now(self) -> float:
        try:
            return float(self._clock())
        except Exception:  # noqa: BLE001
            return time.time()

    def _is_stale(self) -> bool:
        if self._built_at is None:
            return True
        return (self._now() - self._built_at) > STALE_AFTER_SEC

    def _ensure_built(self) -> None:
        if self._broken:
            return
        if self._by_teams or self._by_pk:
            if not self._is_stale():
                return
        self._build()

    def _build(self) -> None:
        try:
            params = self._inject_params or self._load_params()
            probables = self._inject_probables if self._inject_probables is not None \
                else self._load_probables()
            gamelogs = self._inject_gamelogs if self._inject_gamelogs is not None \
                else self._load_gamelogs()
            if params is None or probables is None or gamelogs is None or len(probables) == 0:
                raise ValueError("missing params/probables/gamelogs for SP shadow build")
            from domains.mlb.sp_adjust_current import build_current_sp_form
            sp_form = build_current_sp_form(gamelogs, probables)
            by_teams, by_pk = self._index(sp_form, probables)
            self._params = params
            self._by_teams = by_teams
            self._by_pk = by_pk
            self._built_at = self._now()
            self._broken = False
        except Exception as exc:  # noqa: BLE001 -- a broken build -> permanent None, once
            if not self._warned:
                logger.debug("ingame_sp_shadow build failed (permanent None this process): %s", exc)
                self._warned = True
            self._broken = True
            self._by_teams = {}
            self._by_pk = {}

    def _load_params(self) -> Optional[Tuple[float, float, float]]:
        with open(self._verdict_path, "r", encoding="utf-8") as fh:
            verdict = json.load(fh)
        variant = ((verdict.get("forward_eval_2026") or {}).get("variant_a_historical_fit") or {})
        w, sp_mean, sp_std = variant.get("w"), variant.get("sp_mean"), variant.get("sp_std")
        if w is None or sp_mean is None or sp_std is None:
            return None
        return float(w), float(sp_mean), float(sp_std)

    def _load_probables(self) -> Any:
        import pandas as pd
        return pd.read_parquet(self._probables_path)

    def _load_gamelogs(self) -> Any:
        import pandas as pd
        return pd.read_parquet(self._gamelogs_path)

    def _index(self, sp_form: Any, probables: Any) -> Tuple[Dict[Tuple[str, str], float], Dict[int, float]]:
        """Index sp_diff_ew by (home_key, away_key) team-resolved pair AND by game_pk.
        NaN sp_diff rows are skipped (an honest miss beats a guessed 0.0)."""
        import numpy as np
        merged = sp_form.merge(
            probables[["game_pk", "home_team", "away_team"]].drop_duplicates("game_pk"),
            on="game_pk", how="inner")
        by_teams: Dict[Tuple[str, str], float] = {}
        by_pk: Dict[int, float] = {}
        for row in merged.itertuples(index=False):
            sp_diff = getattr(row, "sp_diff_ew", None)
            if sp_diff is None or (isinstance(sp_diff, float) and np.isnan(sp_diff)):
                continue
            game_pk = int(getattr(row, "game_pk"))
            by_pk[game_pk] = float(sp_diff)
            hk = _resolve_team(str(getattr(row, "home_team", "")))
            ak = _resolve_team(str(getattr(row, "away_team", "")))
            if hk and ak:
                by_teams[(hk, ak)] = float(sp_diff)
        return by_teams, by_pk

    def _lookup_sp_diff(self, home: str, away: str,
                        game_pk: Optional[int]) -> Optional[float]:
        if game_pk is not None and game_pk in self._by_pk:
            return self._by_pk[game_pk]
        hk, ak = _resolve_team(home), _resolve_team(away)
        if hk and ak and (hk, ak) in self._by_teams:
            return self._by_teams[(hk, ak)]
        return None

    def shadow_prob(self, sport: str, home: str, away: str, p_model: float,
                    game_pk: Optional[int] = None) -> Optional[float]:
        """SP-adjusted variant of *p_model* (P(home win)) for logging only. mlb-only;
        None on ANY miss (non-mlb, unresolved matchup, no SP form, bad p_model, or a
        broken/failed build) -- never raises."""
        try:
            if str(sport or "").lower() != "mlb":
                return None
            try:
                p = float(p_model)
            except (TypeError, ValueError):
                return None
            if not (0.0 <= p <= 1.0):
                return None
            self._ensure_built()
            if self._broken or self._params is None:
                return None
            sp_diff = self._lookup_sp_diff(str(home or ""), str(away or ""), game_pk)
            if sp_diff is None:
                return None
            import math
            if isinstance(sp_diff, float) and math.isnan(sp_diff):
                return None
            from domains.mlb.sp_adjust_current import adjust_win_prob
            w, sp_mean, sp_std = self._params
            out = adjust_win_prob(p, sp_diff, w, sp_mean, sp_std)
            if out is None:
                return None
            out_f = float(out)
            return out_f if 0.0 <= out_f <= 1.0 else None
        except Exception as exc:  # noqa: BLE001 -- shadow measurement never raises
            logger.debug("ingame_sp_shadow shadow_prob failed: %s", exc)
            return None


_SINGLETON: Optional[SpShadow] = None


def get_shadow() -> SpShadow:
    """Module-level singleton so the capture loop reuses one cached build per process."""
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = SpShadow()
    return _SINGLETON


__all__ = ["SpShadow", "get_shadow", "STALE_AFTER_SEC"]
