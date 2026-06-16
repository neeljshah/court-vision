"""Track-record ledger row schema (blueprint X3 / mcp-and-ledger PART B).

The ledger is the SELLABLE trust artifact: an append-only, timestamped, hash-pinned
calibration record a skeptic can replay. By construction it logs PROBABILITIES +
OUTCOMES ONLY -- there is no units / ROI / stake / edge column anywhere in the schema,
so a $ claim cannot be stored even by accident. The LLM never authors `calibrated_prob`;
it is copied verbatim from the quant pipeline (predict_matchup.build_result()).

Self-contained (stdlib only).
"""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, asdict, field
from typing import Optional

SCHEMA_VERSION = 1

# Column order is the on-disk contract (parquet + JSONL + CSV mirror all use this).
# NOTE: no units/roi/stake/edge column exists -- probabilities + outcomes ONLY.
SCHEMA_COLS = (
    "pred_id",           # sha1 idempotency key (see make_pred_id)
    "pred_ts",           # ISO8601 UTC: when the prediction was MADE (the vintage clock)
    "sport",             # nba / mlb / soccer / tennis
    "layer",             # "pregame" or "ingame"
    "market",            # "ml" / "total" / "spread" / "over_2.5" / "p1_match_win" ...
    "home",              # home team / player 1
    "away",              # away team / player 2
    "inputs_hash",      # sha1 of the FULL kwargs dict (reproducibility + dedup)
    "model_version",    # git short-sha of HEAD at prediction time (provenance)
    "calibrated_prob",  # THE number, copied verbatim from build_result(); LLM never writes this
    "point_proj",        # float|None: total_mean / proj_margin for non-binary markets
    "game_date",         # str|None: scheduled game date (vintage check: pred_ts < game_date)
    "devig_close_prob",  # float|None: Shin-devigged market close, filled at grading
    "outcome",           # int|None: realized binary outcome (1/0); None until graded
    "graded_at",         # str|None: ISO8601 when outcome was filled
    "game_id",           # str|None: cluster key for clustered SEs + DM blocking
)


@dataclass
class LedgerRow:
    pred_id: str
    pred_ts: str
    sport: str
    layer: str
    market: str
    home: str
    away: str
    inputs_hash: str
    model_version: str
    calibrated_prob: float
    point_proj: Optional[float] = None
    game_date: Optional[str] = None
    devig_close_prob: Optional[float] = None
    outcome: Optional[int] = None
    graded_at: Optional[str] = None
    game_id: Optional[str] = None

    def as_record(self) -> dict:
        """Ordered dict matching SCHEMA_COLS (the on-disk contract)."""
        d = asdict(self)
        return {k: d[k] for k in SCHEMA_COLS}


def hash_inputs(inputs: dict) -> str:
    """Stable sha1 of an inputs/kwargs dict (sorted keys -> deterministic)."""
    blob = json.dumps(inputs, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha1(blob.encode("ascii")).hexdigest()[:16]


def make_pred_id(sport: str, home: str, away: str, market: str, layer: str,
                 inputs_hash: str, pred_ts: str) -> str:
    """Idempotency key: sha1(sport+home+away+market+layer+inputs_hash+pred_ts)[:16].

    Two appends of the SAME prediction (same vintage + inputs) collapse to one row.
    """
    raw = "|".join((sport, home, away, market, layer, inputs_hash, pred_ts))
    return hashlib.sha1(raw.encode("ascii")).hexdigest()[:16]
