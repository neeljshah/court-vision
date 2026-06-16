"""forward_capture archive -- append-only, atomic, idempotent timestamped odds archive.

This is the REAL movement corpus that accrues forward (the existing odds_snapshots
was a live-poll format, not a movement corpus). The moment a real feed is wired,
every poll appends here and the archive grows into the timestamped open->close tape
that forward CLV is graded against.

INVARIANTS (mirrors ledger/ledger.py):
  - APPEND-ONLY: append_snapshots never mutates an existing row; the archive only
    accrues forward.
  - ATOMIC: writes go to a temp sibling then os.replace, so a crash mid-write never
    corrupts the live file.
  - IDEMPOTENT: keyed on snapshot_sha(game_id, book, market, side, captured_at); a
    re-archived snapshot collapses to the FIRST copy (drop_duplicates keep='first').

Storage: JSONL under data/forward_capture/<sport>/odds_archive.jsonl (GITIGNORED via
the data/* rule), parquet-preferred when pyarrow is available (ledger pattern). The
archive stores RAW QUOTED PRICES only -- no probability / edge / $ column exists, so a
dollar claim cannot be stored even by accident.

base_dir is overridable so hermetic tests write to a tmp dir and never touch the real
data/forward_capture/.

Self-contained except for the schema sibling. <=300 LOC. Per-file test: tests/test_archive.py.
"""
from __future__ import annotations

import json
import os
import pathlib
from typing import List, Optional

import pandas as pd

try:  # package import (`python -m scripts.platformkit.forward_capture...`)
    from scripts.platformkit.forward_capture.schema import (  # type: ignore
        OddsSnapshot, LineMoveRecord, snapshot_sha, validate_snapshot)
except ImportError:  # direct-script / per-file-test fallback
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from schema import (  # type: ignore
        OddsSnapshot, LineMoveRecord, snapshot_sha, validate_snapshot)

try:  # parquet preferred; degrade to JSONL on a clone without pyarrow
    import pyarrow  # noqa: F401
    _HAVE_PARQUET = True
except Exception:  # pragma: no cover - environment-dependent
    _HAVE_PARQUET = False

_REPO = pathlib.Path(__file__).resolve().parents[3]
_DEFAULT_DIR = _REPO / "data" / "forward_capture"

# On-disk column contract (parquet + JSONL both use this order). RAW PRICE ONLY --
# plus the sha idempotency key. No probability / edge / $ column exists here.
_COLS = ("sha", "book", "market", "sport", "game_id", "side", "price", "captured_at")


def _store_path(sport: str, base_dir: Optional[str]) -> pathlib.Path:
    d = (pathlib.Path(base_dir) if base_dir else _DEFAULT_DIR) / str(sport)
    d.mkdir(parents=True, exist_ok=True)
    ext = "parquet" if _HAVE_PARQUET else "jsonl"
    return d / f"odds_archive.{ext}"


def _read_frame(path: pathlib.Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=list(_COLS))
    if path.suffix == ".parquet":
        df = pd.read_parquet(path)
        return df if not df.empty else pd.DataFrame(columns=list(_COLS))
    rows = []
    with open(path, encoding="ascii") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    df = pd.DataFrame(rows)
    return df if not df.empty else pd.DataFrame(columns=list(_COLS))


def _atomic_write(df: pd.DataFrame, path: pathlib.Path) -> None:
    """Write to a temp sibling then os.replace -> the live file is never half-written."""
    df = df.reindex(columns=list(_COLS))
    tmp = path.with_suffix(path.suffix + ".tmp")
    if path.suffix == ".parquet":
        df.to_parquet(tmp, index=False)
    else:
        with open(tmp, "w", encoding="ascii") as f:
            for _, r in df.iterrows():
                rec = {k: (float(r[k]) if k == "price" else r[k]) for k in _COLS}
                f.write(json.dumps(rec, ensure_ascii=True) + "\n")
    os.replace(tmp, path)


def _snap_record(snap: OddsSnapshot) -> dict:
    """Snapshot -> the on-disk row dict (validated, with its sha key)."""
    d = snap.as_dict()
    validate_snapshot(d)                      # honesty rail + well-formedness, in code
    d["sha"] = snapshot_sha(snap)
    return {k: d[k] for k in _COLS}


def append_snapshots(snaps: List[OddsSnapshot],
                     base_dir: Optional[str] = None) -> List[str]:
    """Append OddsSnapshots atomically + idempotently. Returns the shas written/kept.

    APPEND-ONLY: existing rows are never mutated. IDEMPOTENT: a re-appended snapshot
    (same sha) collapses to the first copy. Snapshots are grouped by sport so each
    sport's archive is a single forward-accruing tape. Returns the sha of every input
    snapshot (whether newly written or already present), preserving input order.
    """
    if not snaps:
        return []
    by_sport = {}
    for s in snaps:
        by_sport.setdefault(s.sport, []).append(s)
    for sport, group in by_sport.items():
        store = _store_path(sport, base_dir)
        existing = _read_frame(store)
        new = pd.DataFrame([_snap_record(s) for s in group])
        merged = new if existing.empty else pd.concat([existing, new], ignore_index=True)
        # idempotent: a re-appended sha collapses to the FIRST (immutable) copy.
        merged = merged.drop_duplicates("sha", keep="first").reset_index(drop=True)
        _atomic_write(merged, store)
    return [snapshot_sha(s) for s in snaps]


def read_archive(sport: str, base_dir: Optional[str] = None) -> List[OddsSnapshot]:
    """Load one sport's full forward archive as OddsSnapshots (on-disk order)."""
    df = _read_frame(_store_path(sport, base_dir))
    out: List[OddsSnapshot] = []
    for _, r in df.iterrows():
        out.append(OddsSnapshot.from_dict({k: r[k] for k in OddsSnapshot.__annotations__}))
    return out


def build_line_moves(sport: str, game_id: str, book: str, market: str,
                     base_dir: Optional[str] = None) -> Optional[LineMoveRecord]:
    """Open->close movement for one (game, book, market) from the archive.

    open = the EARLIEST captured_at snapshot; close = the LATEST. Returns None when no
    snapshot exists for the key yet (the clock has not accrued a quote). Built from the
    immutable archive -- it reads, never writes. devig_close_prob stays None here; clv.py
    fills it via shin.

    When a market has multiple sides (e.g. home/away), the open/close are chosen per the
    overall earliest/latest captured_at across all matching rows; clv.py selects the
    relevant side from the returned record's snapshots when it needs a specific leg.
    """
    snaps = [s for s in read_archive(sport, base_dir)
             if s.game_id == str(game_id) and s.book == book and s.market == market]
    if not snaps:
        return None
    ordered = sorted(snaps, key=lambda s: s.captured_at)
    return LineMoveRecord(
        sport=sport, game_id=str(game_id), book=book, market=market,
        open_snapshot=ordered[0], close_snapshot=ordered[-1],
    )


def _flat_move(snaps: List[OddsSnapshot]) -> dict:
    """One (game,book,market) snapshot bundle -> the FLAT move dict clv.py reads.

    clv.py is decoupled from LineMoveRecord's nested shape: it reads close_captured_at,
    close_home_price / close_away_price (the two-way close legs it Shin-devigs), plus
    game_id / market / book. The recorder NEVER authors a probability -> devig_close_prob
    stays None; clv.py fills it downstream via the verified shin reference. Two-way legs are
    matched per side, taking each side's LATEST captured price as its close.
    """
    ordered = sorted(snaps, key=lambda s: s.captured_at)
    close_at = ordered[-1].captured_at
    open_at = ordered[0].captured_at
    latest_by_side: dict = {}
    for s in ordered:                      # ordered ascending -> last write per side is its close
        latest_by_side[s.side] = s.price
    home = latest_by_side.get("home", latest_by_side.get("p1", latest_by_side.get("over")))
    away = latest_by_side.get("away", latest_by_side.get("p2", latest_by_side.get("under")))
    return {
        "sport": ordered[0].sport, "game_id": ordered[0].game_id,
        "book": ordered[0].book, "market": ordered[0].market,
        "open_captured_at": open_at, "close_captured_at": close_at,
        "close_home_price": (None if home is None else float(home)),
        "close_away_price": (None if away is None else float(away)),
        "devig_close_prob": None,          # filled downstream by clv.py via shin; never here
        "n_snapshots": len(ordered),
    }


def build_all_line_moves(sport: Optional[str] = None,
                         base_dir: Optional[str] = None,
                         snaps: Optional[List[OddsSnapshot]] = None) -> List[dict]:
    """All open->close moves as the FLAT dicts clv.grade_forward_clv consumes.

    Reduces the snapshot corpus to one move per (sport, game_id, book, market), each carrying
    the close legs clv.py Shin-devigs. Reads from disk by default; pass `snaps` to reduce an
    in-memory list (tests). `sport` filters the disk read when given. This is the list clv.py
    expects -- the per-key build_line_moves above returns the nested LineMoveRecord instead.
    """
    if snaps is None:
        if sport is not None:
            snaps = read_archive(sport, base_dir)
        else:
            snaps = []
            for d in sorted((pathlib.Path(base_dir) if base_dir else _DEFAULT_DIR).glob("*")):
                if d.is_dir():
                    snaps.extend(read_archive(d.name, base_dir))
    groups: dict = {}
    for s in snaps:
        groups.setdefault((s.sport, s.game_id, s.book, s.market), []).append(s)
    return [_flat_move(g) for g in groups.values()]
