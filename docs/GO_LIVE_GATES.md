# Go-live gates (pre-registered 2026-09-17)

CourtVision has never placed a real order. The order-lifecycle code has no reachable live path.
This page fixes, in advance, what would have to be true before that changes. It is written before
the measurement window so that no threshold can be tuned to its own result.

Starting facts, stated plainly:

- The in-game models trail the contemporaneous market reference on paired ticks ([EVIDENCE.md](../EVIDENCE.md),
  section C). A directional in-play strategy is therefore not supported by any measurement here.
- The only thesis left standing is maker-only quoting on a legal US venue, which is a statement about
  microstructure, not forecasting, and is not yet supported by any measurement either.
- Nothing on this page is a claim of edge. A gate that is never met is an acceptable outcome.

All six gates must pass. No gate may be weakened after its own result is seen.

| Gate | Requirement | Fails when |
|---|---|---|
| G1 Corpus integrity | The in-game join checker exits 0 on every captured sport and carries a test that detects a deliberately mis-anchored file | any downstream number is computed on a corpus that fails it |
| G2 Re-measurement | Gate A-0 is re-run on the per-game segmented corpora and published either way | the result is not published |
| G3 Fill realism and markout | A paper maker fill is recorded only when the captured book trades through the quote; markout at 30 s / 120 s / 300 s with independent windows; the venue fee netted at the fill price | the paper series cannot be trusted; G6 cannot be evaluated |
| G4 Controls, tested | Per-order, per-market and per-day limits enforced outside model output; breaker on the maker channel; a kill switch that fails closed; idempotent order ids; restart-safe state; mock-exchange parity green; each control has a test that tries to breach it | any control is logged rather than enforced |
| G5 Venue and legal boundary | Per-state legality encoded in code; venue terms, limits and settlement rules documented; record-retention and tax policy written; a go-live runbook with a flatten procedure | human-only gate; an agent may never assert it passed |
| G6 Evidence | At least 8 consecutive weeks of shadow maker quoting on the G3 instrumentation, fee-netted markout positive with a game-clustered 95 percent interval excluding 0, on at least 2 independent market families, with a pre-registered single-game and single-week concentration check; a sign flip across calendar halves is a reject | anything less |

The expected year-end outcome is "G6 not met, N weeks collected". Publishing that verdict on
schedule is the deliverable. If the gates are green, going live is a human decision taken with the
evidence in hand, not a date.

## Status (updated as gates are attempted; a gate is never edited after its own result)

| Gate | Status on 2026-09-17 |
|---|---|
| G1 | open -- the join checker and the per-game segmentation exist; a revision that anchors on the scheduled game start is queued |
| G2 | open |
| G3 | started -- the paper maker now fills only on a through-trade and a fee-netted markout function exists ([paper_maker.py](../scripts/platformkit/execution/paper_maker.py), [markout.py](../scripts/platformkit/execution/markout.py)); no markout series has been collected |
| G4 | started -- the in-play breaker and the API kill switch now fail closed and are breach-tested; exposure and notional caps are not built |
| G5 | open (human-only) |
| G6 | not started -- zero weeks collected |

**Navigate:** [Evidence index](../EVIDENCE.md) - [README](../README.md) - [Doc map](INDEX.md)
