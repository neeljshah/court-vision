"""
Fusion layer: stat reconciler.

Merges multiple SourceValue observations for the same stat:
  - Higher-tier source wins (SOURCE_PRIORITY order).
  - Within same tier, higher confidence wins.
  - Disagreements (same tier, value diff > threshold) are logged to
    data/fusion/cv_errors.csv for auditing.

Public API
----------
    reconciler = StatReconciler()
    best: SourceValue = reconciler.reconcile("pts", [sv1, sv2, sv3])
    reconciler.flush_errors()   # write pending rows to CSV
"""
from __future__ import annotations

import csv
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from src.fusion.source_registry import SourceValue, SOURCE_PRIORITY

log = logging.getLogger(__name__)

_DEFAULT_ERROR_PATH = Path("data/fusion/cv_errors.csv")
_CSV_HEADER = ["ts", "game_id", "player_game_id", "stat", "winner_source",
               "winner_value", "loser_source", "loser_value", "tier_delta", "conf_delta"]


class StatReconciler:
    """
    Merges SourceValue observations for one stat across sources.

    Args:
        error_path:  Path to disagreement log CSV.
        diff_thresh: Relative difference to flag as disagreement (default 0.10 = 10 %).
    """

    def __init__(
        self,
        error_path: Path = _DEFAULT_ERROR_PATH,
        diff_thresh: float = 0.10,
    ) -> None:
        self.error_path  = Path(error_path)
        self.diff_thresh = diff_thresh
        self._pending:   List[dict] = []
        self.error_path.parent.mkdir(parents=True, exist_ok=True)

    # ── core ──────────────────────────────────────────────────────────────

    def reconcile(
        self,
        stat: str,
        sources: Sequence[SourceValue],
        game_id: str = "",
        player_game_id: str = "",
    ) -> Optional[SourceValue]:
        """
        Return the winning SourceValue for `stat`.

        Checks for disagreements between same-tier sources and logs them.
        Returns None if `sources` is empty.
        """
        if not sources:
            return None

        # Sort: (tier DESC, confidence DESC)
        ranked = sorted(
            sources,
            key=lambda sv: (sv.tier, sv.confidence),
            reverse=True,
        )

        winner = ranked[0]

        # Check top-tier disagreements (same tier as winner)
        top_tier_vals = [sv for sv in ranked if sv.tier == winner.tier]
        if len(top_tier_vals) > 1:
            self._check_disagreements(
                stat, winner, top_tier_vals[1:], game_id, player_game_id
            )

        return winner

    def reconcile_many(
        self,
        stat_sources: Dict[str, Sequence[SourceValue]],
        game_id: str = "",
        player_game_id: str = "",
    ) -> Dict[str, SourceValue]:
        """Reconcile multiple stats at once. Returns dict of stat -> best SourceValue."""
        return {
            stat: self.reconcile(stat, vals, game_id, player_game_id)
            for stat, vals in stat_sources.items()
            if vals
        }

    # ── error logging ─────────────────────────────────────────────────────

    def flush_errors(self) -> int:
        """Write pending disagreement rows to CSV. Returns count written."""
        if not self._pending:
            return 0
        write_header = not self.error_path.exists() or self.error_path.stat().st_size == 0
        with open(self.error_path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=_CSV_HEADER)
            if write_header:
                writer.writeheader()
            writer.writerows(self._pending)
        n = len(self._pending)
        self._pending.clear()
        log.debug("Flushed %d disagreement rows to %s", n, self.error_path)
        return n

    # ── private ───────────────────────────────────────────────────────────

    def _check_disagreements(
        self,
        stat: str,
        winner: SourceValue,
        others: List[SourceValue],
        game_id: str,
        player_game_id: str,
    ) -> None:
        for other in others:
            try:
                w_val = float(winner.value)
                o_val = float(other.value)
            except (TypeError, ValueError):
                # non-numeric stat — compare as strings
                if str(winner.value) != str(other.value):
                    self._log_disagreement(stat, winner, other, game_id, player_game_id)
                continue

            denom = max(abs(w_val), abs(o_val), 1e-6)
            rel_diff = abs(w_val - o_val) / denom
            if rel_diff > self.diff_thresh:
                self._log_disagreement(stat, winner, other, game_id, player_game_id)

    def _log_disagreement(
        self,
        stat: str,
        winner: SourceValue,
        loser: SourceValue,
        game_id: str,
        player_game_id: str,
    ) -> None:
        row = {
            "ts":               datetime.utcnow().isoformat(),
            "game_id":          game_id,
            "player_game_id":   player_game_id,
            "stat":             stat,
            "winner_source":    winner.source,
            "winner_value":     winner.value,
            "loser_source":     loser.source,
            "loser_value":      loser.value,
            "tier_delta":       int(winner.tier) - int(loser.tier),
            "conf_delta":       round(winner.confidence - loser.confidence, 4),
        }
        self._pending.append(row)
        log.info(
            "Stat disagreement [%s] %s=%s(%s) vs %s=%s(%s)",
            stat, winner.source, winner.value, game_id,
            loser.source, loser.value, player_game_id,
        )
