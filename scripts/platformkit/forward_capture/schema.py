"""forward_capture schema -- typed contracts for the forward odds-movement corpus.

Two frozen dataclasses (stdlib only, ASCII):

  OddsSnapshot  -- ONE quoted price at ONE instant. captured_at is the vintage
                   floor, stamped by US at capture (ISO8601 UTC). By construction
                   there is NO win_prob / edge / ev / roi / stake / implied field
                   on a snapshot -- only a raw quoted decimal price. Devig is
                   computed LATER by clv.py via eval_gate/shin, never authored here.

  LineMoveRecord -- the open -> close movement for one (sport, game, book, market):
                   the earliest snapshot (open) and the latest (close), plus an
                   OPTIONAL devig_close_prob that clv.py fills via shin. The
                   recorder never authors devig_close_prob; it stays None here.

HONESTY RAIL (borrowed in spirit from edge_engine.schema BANNED_FIELDS): a snapshot
carries a price ONLY. validate_snapshot rejects any banned outcome/probability field
that tries to sneak onto a snapshot dict, so a $ / edge claim cannot be stored even
by accident.

snapshot_sha(snap) is the archive idempotency key over
(game_id, book, market, side, captured_at): re-archiving the identical snapshot
collapses to the first copy.

Self-contained (stdlib only). <=300 LOC. Per-file test: tests/test_archive.py /
tests/test_capture.py / tests/test_clv.py.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# Duplicated locally (a 4-tuple) to AVOID importing edge_engine -- this keeps the
# recorder decoupled from the intelligence stack. Keep in sync intentionally.
SPORTS = ("nba", "mlb", "soccer", "tennis")

# The market sides we record. Two-way money markets use home/away; over/under
# totals use over/under; head-to-head player markets (tennis) use p1/p2.
SIDES = ("home", "away", "over", "under", "p1", "p2")

# Outcome/probability/$ field names that MUST NEVER appear on a snapshot dict. A
# snapshot is a RAW QUOTED PRICE only; every probability is computed downstream by
# shin in clv.py. `price` is the one allowed numeric (the quoted decimal odds).
BANNED_FIELDS = (
    "win_prob", "probability", "prob", "edge", "ev", "roi", "stake",
    "kelly", "implied", "devig", "devig_prob", "clv", "units",
)


def _assert_iso(ts: str, label: str) -> None:
    """Raise AssertionError if ts is not parseable ISO-8601 (Py3.9 normalises Z)."""
    try:
        datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise AssertionError(f"{label} not ISO-8601: {ts!r}")


@dataclass(frozen=True)
class OddsSnapshot:
    """ONE quoted decimal price at ONE captured instant. The atomic archive row.

    captured_at is the vintage floor: the ISO8601 UTC time WE saw this quote. The
    leak guard later asserts a prediction's pred_ts < captured_at before grading
    CLV, so a hindsight quote can never flatter a prediction.

    There is NO probability / edge / $ field by construction -- `price` is the raw
    quoted decimal odds (> 1.0) and nothing more.
    """
    book: str            # sportsbook id (e.g. 'draftkings', 'fanduel') -- provenance
    market: str          # 'ml' / 'total_o2.5' / 'spread' / 'p1_match_win' ...
    sport: str           # one of SPORTS
    game_id: str         # stable id for the event the quote is about
    side: str            # one of SIDES (which leg this price is for)
    price: float         # the RAW quoted decimal odds (> 1.0); NOT a probability
    captured_at: str     # ISO8601 UTC: when WE captured this quote -- the vintage floor

    def as_dict(self) -> dict:
        return {
            "book": self.book, "market": self.market, "sport": self.sport,
            "game_id": self.game_id, "side": self.side, "price": float(self.price),
            "captured_at": self.captured_at,
        }

    @staticmethod
    def from_dict(d: dict) -> "OddsSnapshot":
        return OddsSnapshot(
            book=str(d["book"]), market=str(d["market"]), sport=str(d["sport"]),
            game_id=str(d["game_id"]), side=str(d["side"]), price=float(d["price"]),
            captured_at=str(d["captured_at"]),
        )


@dataclass(frozen=True)
class LineMoveRecord:
    """The open -> close movement for one (sport, game, book, market).

    Built from the archive by archive.build_line_moves: open_snapshot = earliest
    captured_at, close_snapshot = latest captured_at. devig_close_prob is OPTIONAL
    and stays None in the recorder; clv.py fills it via eval_gate/shin. The recorder
    NEVER authors a probability.
    """
    sport: str
    game_id: str
    book: str
    market: str
    open_snapshot: OddsSnapshot
    close_snapshot: OddsSnapshot
    devig_close_prob: Optional[float] = None  # filled LATER by clv.py via shin; never here

    def as_dict(self) -> dict:
        return {
            "sport": self.sport, "game_id": self.game_id, "book": self.book,
            "market": self.market,
            "open_snapshot": self.open_snapshot.as_dict(),
            "close_snapshot": self.close_snapshot.as_dict(),
            "devig_close_prob": (None if self.devig_close_prob is None
                                 else float(self.devig_close_prob)),
        }

    @staticmethod
    def from_dict(d: dict) -> "LineMoveRecord":
        dcp = d.get("devig_close_prob")
        return LineMoveRecord(
            sport=str(d["sport"]), game_id=str(d["game_id"]), book=str(d["book"]),
            market=str(d["market"]),
            open_snapshot=OddsSnapshot.from_dict(d["open_snapshot"]),
            close_snapshot=OddsSnapshot.from_dict(d["close_snapshot"]),
            devig_close_prob=(None if dcp is None else float(dcp)),
        )


def validate_snapshot(d: dict) -> None:
    """Raise AssertionError on a malformed / dishonest OddsSnapshot dict.

    Enforces: required non-empty fields; sport in SPORTS; side in SIDES; price a
    decimal > 1.0; captured_at parseable ISO; and -- the honesty rail -- that NO
    banned probability/edge/$ field sneaked onto the row. A snapshot is a price only.
    """
    req = ("book", "market", "sport", "game_id", "side", "price", "captured_at")
    for k in req:
        assert k in d and d[k] not in (None, ""), f"missing/empty field {k}"
    assert d["sport"] in SPORTS, f"bad sport {d['sport']}"
    assert d["side"] in SIDES, f"bad side {d['side']}"
    try:
        price = float(d["price"])
    except (TypeError, ValueError):
        raise AssertionError("price not numeric")
    assert price > 1.0, f"decimal price must be > 1.0, got {price}"
    _assert_iso(d["captured_at"], "captured_at")
    # honesty rail: a snapshot is a RAW PRICE -- no outcome/probability/$ field allowed.
    for k in d:
        assert str(k).lower() not in BANNED_FIELDS, (
            f"FORBIDDEN outcome/edge field on an odds snapshot: {k}"
        )


def snapshot_sha(snap: OddsSnapshot) -> str:
    """Idempotency key: sha1(game_id|book|market|side|captured_at)[:16].

    Two archives of the SAME quoted snapshot (same event, book, market, side and
    capture instant) collapse to one row. Includes `side` so the two legs of a
    two-way market at the same instant are distinct rows, not collisions.
    """
    raw = "|".join((snap.game_id, snap.book, snap.market, snap.side, snap.captured_at))
    return hashlib.sha1(raw.encode("ascii")).hexdigest()[:16]
