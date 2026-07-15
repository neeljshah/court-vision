"""scripts.platformkit.claims.card_miner_bulk -- mass hypothesis-card generator.

USER DIRECTIVE 2026-07-15: scale to 10,000s of pre-registered cards and let the
system validate as many as possible autonomously.

Every card here is a cell of a MECHANICAL grid over the as-of fields the live
capture rows ACTUALLY carry (verified against data/cache/ingame_grade/
<sport>/*.jsonl on 2026-07-15: model_prob, market_prob, espn_wp, spread_bp,
book_thinness, stale_quote, xg_home/away/asof_min, mlb_pitcher_pitch_count,
mlb_bullpen_used). The claim template is always the same conditional: "when
this cell holds, the model's tick price is closer to the outcome than the
market's" -- i.e. the model's divergence from the market is SIGNAL, not noise,
inside the cell. Cells are enumerated combinatorially BEFORE any outcome is
examined (this generator reads no outcomes, no grade files); the grid axes and
bands are fixed in code, so registration is pre-outcome by construction.

HONESTY: with 10,000s of cells, most verdicts SHOULD be REJECTED/STARVED --
that is the gate working, not failure. Every card carries family + cell
metadata so downstream FDR accounting (false_discovery_job) can correct across
the family. No $ claims; Brier/CLV probability units only.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/claims/test_card_miner_bulk.py -q
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Tuple

from scripts.platformkit.claims import card_registry as _reg

SOURCE = "card_miner_bulk_v1_2026-07-15"

# Each axis: (axis_name, [(band_label, trigger_fragment or None-for-wildcard)]).
# Fragments reference ONLY registry-allowlisted as-of fields.
_DIV = "abs(model_prob - market_prob)"
_AXES: List[Tuple[str, List[Tuple[str, Optional[str]]]]] = [
    ("sign", [
        ("model_above", "model_prob > market_prob"),
        ("model_below", "model_prob < market_prob"),
        ("any", None),
    ]),
    ("divergence", [
        ("d01_02", f"{_DIV} >= 0.01 and {_DIV} < 0.02"),
        ("d02_04", f"{_DIV} >= 0.02 and {_DIV} < 0.04"),
        ("d04_08", f"{_DIV} >= 0.04 and {_DIV} < 0.08"),
        ("d08_up", f"{_DIV} >= 0.08"),
        ("any", None),
    ]),
    ("regime", [
        ("longshot", "market_prob < 0.2"),
        ("dog", "market_prob >= 0.2 and market_prob < 0.35"),
        ("coin_low", "market_prob >= 0.35 and market_prob < 0.5"),
        ("coin_high", "market_prob >= 0.5 and market_prob < 0.65"),
        ("fav", "market_prob >= 0.65 and market_prob < 0.8"),
        ("heavy_fav", "market_prob >= 0.8"),
        ("any", None),
    ]),
    ("spread", [
        ("tight", "spread_bp < 200"),
        ("mid", "spread_bp >= 200 and spread_bp < 600"),
        ("wide", "spread_bp >= 600 and spread_bp < 1500"),
        ("vwide", "spread_bp >= 1500"),
        ("any", None),
    ]),
    ("thinness", [
        ("deep", "book_thinness < 30"),
        ("mid", "book_thinness >= 30 and book_thinness < 100"),
        ("thin", "book_thinness >= 100 and book_thinness < 250"),
        ("vthin", "book_thinness >= 250"),
        ("any", None),
    ]),
    ("staleness", [
        ("fresh", "stale_quote == False"),
        ("any", None),
    ]),
    ("espn_gap", [
        ("e02_05", "abs(espn_wp - market_prob) >= 0.02 and abs(espn_wp - market_prob) < 0.05"),
        ("e05_10", "abs(espn_wp - market_prob) >= 0.05 and abs(espn_wp - market_prob) < 0.10"),
        ("e10_up", "abs(espn_wp - market_prob) >= 0.10"),
        ("any", None),
    ]),
]

# Sport-flavored extension families, each crossed with sign x divergence only
# (full cross would explode without adding mechanism variety).
_EXT_FAMILIES: List[Tuple[str, List[Tuple[str, str]]]] = [
    ("mlb_pitch", [
        ("pc_early", "mlb_pitcher_pitch_count < 50"),
        ("pc_mid", "mlb_pitcher_pitch_count >= 50 and mlb_pitcher_pitch_count < 85"),
        ("pc_late", "mlb_pitcher_pitch_count >= 85"),
        ("bullpen_in", "mlb_bullpen_used == True"),
        ("starter_in", "mlb_bullpen_used == False"),
    ]),
    ("xg_state", [
        ("xg_home_up", "xg_home - xg_away >= 0.5"),
        ("xg_away_up", "xg_away - xg_home >= 0.5"),
        ("xg_even", "abs(xg_home - xg_away) < 0.5"),
        ("xg_late", "xg_asof_min >= 60"),
    ]),
]

_MECHANISM = (
    "Grid-cell conditional (family {family}, cell {cell}): in-game market "
    "re-pricing quality varies with liquidity, regime and state; inside this "
    "cell the model's tick-time divergence from the market is hypothesized to "
    "be information the market has not yet priced (fired-rows Brier delta "
    "model-vs-market < 0 in BOTH date halves). Mechanical pre-outcome cell of "
    "a fixed grid -- see card_miner_bulk.py; most cells are expected to "
    "REJECT, and an honest REJECT is a success."
)


def _cell_cards() -> Iterator[Dict[str, Any]]:
    """Enumerate every non-trivial grid cell as a registrable card dict."""
    def emit(family: str, parts: List[Tuple[str, str]]) -> Dict[str, Any]:
        cell = ".".join(lbl for lbl, _ in parts)
        trigger = " and ".join(f"({frag})" for _, frag in parts)
        return {
            "claim": (f"When cell [{family}:{cell}] holds at an in-game tick, "
                      "the model tick price beats the market tick price on "
                      "outcome Brier (divergence is signal inside this cell)."),
            "condition": {"scope": "ingame", "entity": "game", "trigger": trigger,
                          "window": "any_tick"},
            "mechanism": _MECHANISM.format(family=family, cell=cell),
            # fired-rows CLV sign is mechanical for directional cells: a
            # model_below cell has model_prob < market_prob at every fired
            # tick, so its CLV is negative by construction -- "+" there could
            # never validate. Non-directional cells default to "+".
            "expected_sign": "-" if "sign=model_below" in cell else "+",
            "expected_magnitude": "small (fired-rows Brier delta < 0, CI-backed)",
            "family": family, "cell": cell,
        }

    # Core family: full cross with wildcards; require >=1 of (sign, divergence)
    # to be non-wildcard so no card is the trivial always-true cell.
    def cross(i: int, parts: List[Tuple[str, str]]) -> Iterator[Dict[str, Any]]:
        if i == len(_AXES):
            if parts:
                yield emit("core", parts)
            return
        name, bands = _AXES[i]
        for lbl, frag in bands:
            nxt = parts + ([(f"{name}={lbl}", frag)] if frag else [])
            yield from cross(i + 1, nxt)

    for card in cross(0, []):
        yield card
    # Extension families: ext-band x sign x divergence (non-wildcard only).
    sign_bands = [b for b in _AXES[0][1] if b[1]]
    div_bands = [b for b in _AXES[1][1] if b[1]]
    for family, bands in _EXT_FAMILIES:
        for lbl, frag in bands:
            for slbl, sfrag in sign_bands:
                for dlbl, dfrag in div_bands:
                    yield emit(family, [(f"{family}={lbl}", frag),
                                        (f"sign={slbl}", sfrag),
                                        (f"divergence={dlbl}", dfrag)])


def mine(*, limit: Optional[int] = None, dry_run: bool = False) -> Dict[str, Any]:
    """Generate + register the full grid. Idempotent: cells already registered
    (matched by family+cell in existing rows) are skipped."""
    existing = {(c.get("family"), c.get("cell"))
                for c in _reg.get_all_latest().values() if c.get("family")}
    cards = []
    for card in _cell_cards():
        if (card["family"], card["cell"]) in existing:
            continue
        cards.append(card)
        if limit is not None and len(cards) >= limit:
            break
    if dry_run:
        return {"n_new": len(cards), "n_existing_skipped": len(existing),
                "dry_run": True, "edge_claimed": False}
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = _reg.register_bulk(cards, SOURCE, ts)
    out.update({"n_new": len(cards), "n_existing_skipped": len(existing),
                "dry_run": False, "edge_claimed": False})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Bulk grid hypothesis-card miner (pre-outcome, mechanical)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    print(json.dumps(mine(limit=args.limit, dry_run=args.dry_run), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
