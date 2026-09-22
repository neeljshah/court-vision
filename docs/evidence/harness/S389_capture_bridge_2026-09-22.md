# S389 native capture bridge

Candidate prepared; independent acceptance remains pending.

Machine: local Windows worktree C:/Users/neelj/nba-harness-h49.
Construct and fixture checks only; no network, pod, or archive replay.
The contract resolves to docs/evidence/tracking/VERIFIER_CONTRACT.md;
the shorter path in the dispatch is absent.

## BINDING BEFORE-CONDITION

Executed `git show master:<path>` for each source below before implementation.
Master read: `c78ed957d3a3204990af8b935fd1cc68f474fb72`.
The premise holds: the existing reader accepts synthetic tape watermarks,
not native drain closures; state identity does not use game_key.
The following blocks quote command output.

`scripts/platformkit/execution/forward_replay_io.py` (master UTF-8 bytes: 6342):
```python
_KINDS = {"snapshot", "snapshot_bulk", "trade", "trade_gap", "host_gap", "state", "tape_watermark"}
def read_jsonl(paths: Iterable[Path], *, state: bool = False) -> Iterator[dict]:
    """Read one line at a time, preserving decimal JSON tokens and refusal rows."""
    for path in paths:
        with Path(path).open(encoding="ascii") as stream:
            for line in stream:
                try:
                    row = json.loads(line, parse_float=Decimal, parse_constant=Decimal)
                except (ValueError, ArithmeticError):
                    yield {"_io_refusal": "invalid_json"}
                    continue
                if not isinstance(row, dict):
                    yield {"_io_refusal": "invalid_record"}
                    continue
                if state:
                    row = dict(row, record_type="state")
                    # S352/S358 retains the provider receipt spelling.
                    if "response_end_ts" not in row:
                        row["response_end_ts"] = row.get("response_end_utc")
                yield row


def identity(row: dict) -> tuple[str, str]:
    """Use explicit capture identity; never guess a provider-to-market join."""
    game = row.get("event_ticker", row.get("game_id"))
    ticker = row.get("ticker")
    return (game if isinstance(game, str) and game else "UNMATCHED",
            ticker if isinstance(ticker, str) and ticker else "UNMATCHED")
```

`scripts/platformkit/execution/forward_replay_io.py` (master UTF-8 bytes: 6342):
```python
        if kind in ("trade_gap", "host_gap", "tape_watermark"):
            fields = (("covered_from_ts", "closed_through_ts", "pagination_complete")
                      if kind == "tape_watermark" else ("gap_start_ts", "gap_end_ts"))
            key += (kind, *(str(row.get(k)) for k in fields))
```

`scripts/platformkit/ingame/local_capture_runner_trades.py` (master UTF-8 bytes: 5209):
```python
def trade_row(market: dict, trade: dict, capture_ts: str, request_start: str,
              response_end: str, http_status: int) -> dict:
    """Keep raw trade values and the existing metadata names."""
    return {**trade, **envelope(market, "trade", request_start, response_end, http_status),
            "ticker": trade.get("ticker", market.get("ticker")), "raw_trade": deepcopy(trade)}
def capture_group(client, writer, market: dict, group: TradeGroup, tick_start: str,
                  page_budget: int = 20,
                  interruption_hook: Callable[[str], None] | None = None):
    """Validate, append and sync each page before persisting its continuation."""
    from scripts.platformkit.ingame.local_capture_backfill import capture_pages

    if group.recover:
        restored = seed_group(writer.root, market, client.metrics, client.utc_clock())
        if restored is None:
            return None
        group.__dict__.update(restored.__dict__)
    return capture_pages(client, writer, market, group, tick_start, page_budget,
                         interruption_hook=interruption_hook)
```

`scripts/platformkit/ingame/local_capture_backfill.py` (master UTF-8 bytes: 14319):
```python
def gap_row(market: dict, batch, kind: str, start, end, tick_start: str) -> dict:
    """Attach the actual last page receipt to an explicit gap."""
    receipt = batch.receipt
    return {**envelope(market, "trade_gap", receipt.start, receipt.end, receipt.status),
            "gap_kind": kind, "gap_start_ts": start, "gap_end_ts": end,
            "tick_start_ts": tick_start, "request_params": batch.query,
            "response_cursor": receipt.body.get("cursor")}
        record.update(backfill_open=True, backfill_id=pending["backfill_id"])
            closing = {**envelope(market, "trade_backfill_closed", batch.receipt.start,
                                  batch.receipt.end, batch.receipt.status), "tick_start_ts": tick_start}
            if batch.limited:
                closing = gap_row(market, batch, "page_budget", previous, pending["oldest"], tick_start)
                candidate.gap_floor = max(candidate.gap_floor or 0, ceil(parse_ts(pending["oldest"]).timestamp()))
            closing.update(backfill_id=pending["backfill_id"], backfill_open=False,
                           drain_start_ts=pending["drain_start_ts"], drain_watermark=iso(candidate.watermark) if candidate.watermark else None,
                           drain_boundary_ids=sorted(candidate.boundary))
            writer.append(closing, "trade_gaps" if batch.limited else "trade_closures")
```

`scripts/platformkit/ops/capture_supervisor.py` (master UTF-8 bytes: 10850):
```python
        self.journal = self.directory / ("supervisor_" + name + ".jsonl")
    def _record(self, kind: str, stamp: float, **fields: object) -> None:
        self._recover(stamp)
        with self.journal.open("ab") as stream:
            stream.write(_json(dict(event=kind, time=_utc(stamp), **fields)))
            stream.flush()
            os.fsync(stream.fileno())
        self._beat()
                self.last_gap = dict(before=_utc(previous_wall), after=_utc(wall))
                self._record("host_gap", wall, **self.last_gap, disagreement_seconds=delta)
```

`scripts/platformkit/ingame/game_market_link.py` (master UTF-8 bytes: 9209):
```python
def link_game(sport: str, date_iso: Optional[str], home_abbr: Optional[str], away_abbr: Optional[str],
              kalshi_index: Dict[str, Dict[str, Any]], scheduled_start_utc: Optional[str] = None,
              metrics: Optional[Metrics] = None, source: str = "linker") -> LinkResult:
    """Match both directional teams; multiple events require an exact start."""
    if not date_iso:
        return LinkResult(False, reason="no_game_date")
    home, away = alias(sport, home_abbr), alias(sport, away_abbr)
    if not home or not away or home == away:
        return LinkResult(False, reason="no_team_codes")
    dated = {event: entry for event, entry in kalshi_index.items() if entry.get("date") == date_iso}
    candidates = {event: entry for event, entry in dated.items()
                  if not entry.get("metadata_conflict") and
                  alias(sport, entry.get("home_abbr")) == home and
                  alias(sport, entry.get("away_abbr")) == away}
    if not candidates:
        missing = any(not entry.get("home_abbr") or not entry.get("away_abbr") for entry in dated.values())
        reason = "missing_directional_team_evidence" if missing else "no_kalshi_event_for_date_and_team"
        return LinkResult(False, reason=reason)
    if len(candidates) > 1:
        if not scheduled_start_utc:
            return LinkResult(False, reason="ambiguous_multiple_kalshi_events")
        if any(entry.get("scheduled_start_utc") is None for entry in candidates.values()):
            return LinkResult(False, reason="missing_market_scheduled_start")
        start = _timestamp(scheduled_start_utc, metrics or LINK_METRICS, source)
        if start is None:
            return LinkResult(False, reason="invalid_scheduled_start")
        candidates = {event: entry for event, entry in candidates.items()
                      if entry.get("scheduled_start_utc") == start}
        if len(candidates) != 1:
            return LinkResult(False, reason="no_unique_scheduled_start_match")
    event, entry = next(iter(candidates.items()))
    return LinkResult(True, event_ticker=event, tickers=tuple(sorted(entry.get("tickers", ()))))
```

## Imported signatures read before implementation

The blocks above include `link_game`; the following signatures are also exact.

```python
# scripts/platformkit/ingame/game_market_link.py
def index_kalshi_events(rows: List[Dict[str, Any]], metrics: Optional[Metrics] = None,
                        source: str = "linker") -> Dict[str, Dict[str, Any]]:
# scripts/platformkit/ingame/local_capture_metrics.py
    def __init__(self, utc_clock=utcnow) -> None:
# scripts/platformkit/execution/forward_replay_io.py
def stamp(value: object) -> Decimal:
def iso(value: Decimal) -> str:
# scripts/platformkit/execution/forward_replay_policy.py
def count(value: object) -> int:
def number(value: object, *, positive: bool = False) -> Decimal:
def books(row: dict) -> tuple[dict, dict, dict]:
# scripts/platformkit/execution/capture_book_adapter.py
def to_quote_book(row: dict) -> dict:
def to_fill_snapshot(row: dict) -> dict:
def to_mark_tick(row: dict) -> dict:
# scripts/platformkit/execution/venue_time.py
def parse_venue_time(value: object) -> float | None:
# scripts/platformkit/execution/forward_replay_qualification.py
    def __init__(self, schedule: list, as_of: object):
    def observe(self, row: dict) -> None:
    def decision(self, row: dict, accepted: bool, reservation_end: D | None) -> None:
    def reports(self) -> dict:
```

## Implemented behavior

- Native mode is opt-in; CLI accepts explicit trade shards and supervisor journals.
- The as-of receipt filter precedes schema checks and duplicate handling. Native
  evidence pins its cutoff; replay refuses a different cutoff.
- Provider states retain game_key. The landed directional linker must prove one
  state game key for the selected event and ticker. Missing or ambiguous evidence
  is LINKAGE_INVALID, counted. A nonempty schedule game_key must match exactly.
- Entire snapshots pass through `books` to the landed capture adapter exclusively.
  The bridge never traverses raw ladders or adds duplicate-level checks. Quantities use
  Decimal; COUNT fields require strict ints within the landed domain bound.
- A closure proves completeness only through drain_start_ts. A first-contact gap
  endpoint or an earlier CLOSED watermark proves the next query's lower bound.
  A trade timestamp never establishes completeness. No known lower bound means
  no interval. Equal-receipt first-contact gaps precede closures.
- Open backfill IDs cannot borrow another drain's closure. Unreadable trade input
  fails tape completeness. Supervisor host_gap windows retain exact fractions;
  positive overlap is handled by the unchanged qualification module.
- Page-budget restart bounds use the writer's upward integral rounding; skipped
  fractional intervals remain uncovered. Terminal IDs are checked across both
  closure and page-budget records. Invalid states retain their refusal even if
  a valid sibling establishes the game link.
- Every new production reader is read-only. Existing append/atomic replay writers
  remain unchanged. Test fixture writes use flush, fsync, and atomic replacement.

## Fixture provenance

The local data/cache/ingame_books_local directory is absent in this worktree.
No external worktree was accessed. One existing committed snapshot was copied
verbatim from tests/platformkit/execution/fixtures/s341_real_snapshots_2026-09-21.jsonl.
The S380 REAL ROW was extracted verbatim, joining the spec's display line breaks.
These two rows exercise actual schemas and honest linkage refusal; they do not
purport to be a matched game. Every other scenario is an explicit construct.
The first test consumes both persisted native fixtures through load_native and replay.

- `tests/platformkit/execution/fixtures/s389_native_books.jsonl`; 5598 bytes; one JSONL row; resolution n/a.

- `tests/platformkit/execution/fixtures/s389_native_state.jsonl`; 789 bytes; one JSONL row; resolution n/a.

## Original candidate reproduction and validation

Final serialized per-file runs: native tests 47 passed, replay tests 49 passed,
qualification tests 79 passed. Native n = 47 (CONSTRUCT); total 175 tests passed.
Each pytest invocation names one test file and uses `-q -p no:cacheprovider`.
The exact test paths are:

- tests/platformkit/execution/test_forward_capture_bridge.py
- tests/platformkit/execution/test_forward_replay.py
- tests/platformkit/execution/test_forward_replay_qualification.py

Earlier native candidate run: 39 passed, one failed (watermark with an empty
boundary-ID list). That closure is now a counted refusal. An initial validation
launch overlapped two per-file processes; the final reruns are serialized.
No whole-suite invocation was used.
CLI `python -m scripts.platformkit.execution.forward_replay --help`: PASS.
Contract preflight with all seven owned files, `--base master`, and the S389
spec: nine checks PASS, including the final memo-inclusive run.
ASCII checks PASS for all seven files. Python line counts: bridge 254, reader
195, replay 300, new test 276. Fixture files contain one row each.
Qualification constants and both landed S362 test files are untouched.
Their LF-normalized bytes were compared to master and match exactly. The
legacy reader's complete source prefix also matches master exactly.
The fixture-mode regression executes the master replay source and compares
serialized report bytes with the candidate using isolated temporary ledgers.
The full-window construct feeds native evidence into frozen qualification with
explicit synthetic reservation intervals; it is not a reservation stress test.

## FIX 1b

Both BLOCKING findings reproduced locally before changing production code.
The local spec and `git show master:docs/evidence/tracking/specs/S389_spec.md`
match; neither contains an AMENDMENT block.

1. Missing scheduled game_key: `_links([book()], [state()], selected, Counter())`
   with `selected = schedule()` and its game_key removed produced:
   `{('nfl', '401872945'): 'KXNFLGAME-26SEP21INDKC'} counts {}`.
   The bridge now requires a nonempty string key and exact equality. The same
   reproduction passes with `{} counts {'LINKAGE_INVALID': 1}`. The expanded
   `test_absent_or_ambiguous_or_wrong_key` covers missing, null, empty, whitespace,
   and non-string schedule keys, plus the original absent/ambiguous/wrong states.
   It asserts a counted refusal, emitted LINKAGE_INVALID, and no linked state.
2. Direct ladder read: `_book(dict(book(), book=Bomb(x=1)))`, with `books` stubbed
   and Bomb.get raising, produced `RuntimeError: OUTSIDE_ADAPTER_READ:orderbook`.
   `_book` now only calls `books(row)`. The same reproduction passes: the entire
   snapshot reaches that adapter entry once, by identity, with no outside read.
   `test_snapshot_exclusively_through_adapter` covers Bomb mappings at snapshot,
   book, and orderbook levels. The old duplicate-level assertion was removed
   because it required the forbidden traversal; trade duplicate checks remain.
3. NOTE: confirmed behavior is unchanged. Frozen qualification code/constants,
   both landed S362 test files, and the legacy reader prefix match master.

Validation uses only constructs/committed fixtures, one pytest file at a time,
with `-q -p no:cacheprovider` and worktree-local `--basetemp` directories
`.tmp_s389_fix1b_native`, `.tmp_s389_fix1b_replay`, `.tmp_s389_fix1b_qualification`.
Native tests: 55 passed. Replay tests: 49 passed. Qualification: 79 passed.
Total: 183 passed, n = 183 (CONSTRUCT). CLI --help: PASS.
There is no separate row self-check CLI; contract preflight supplies that check.
Contract preflight: all nine checks PASS over the seven candidate files, with
`--base master --spec docs/evidence/tracking/specs/S389_spec.md`; verdict excluded.
ASCII checks PASS for all seven files; Python LOC: bridge 243, reader 195,
replay 300, tests 298. No commit created; files remain ready for lane_commit.

## NOT VERIFIED

- No live or complete archive run, network capture, pod execution, or deployment.
- No real matched game qualified; actual captured snapshots lack the directional
  metadata needed by the landed linker, so absent evidence remains a refusal.
- No fresh native closure or supervisor journal copied from a real archive;
  those cases use the exact landed writer shapes as constructs.
- No runtime writer crash or power-loss injection; this bridge only reads files.
- No independent verifier acceptance and no commit created in this sandbox.
