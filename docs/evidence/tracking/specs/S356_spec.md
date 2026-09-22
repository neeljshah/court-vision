GAP S356 | sport all (maker channel) | worktree harness-h14 (master-based) | log cx_s356_mark_freshness
# Causal markout selects marks CONDITIONAL ON A PRICE MOVE: a mark must qualify by capture age, never by price change

SINGLE PROBLEM (found by the astra round-11 pre-mortem, confirmed by the orchestrator in landed code): markout_causal.resolve_marks
calls markout_causal_windows.freshness_by_index -> scripts/platformkit/ingame/quote_freshness.freshness_mask, which defines a tick
as FRESH only when its price DIFFERS from the previous tick (quote_freshness.py:83-107). A freshly captured tick whose mid is
UNCHANGED is therefore rejected as stale_mark and the search runs forward until the price moves. The mark is selected on the
movement being measured -- a selection bias inside the estimand. Three verifier rounds did not catch it. Nothing has been scored.

BINDING BEFORE-CONDITION (re-run, quote): build three same-market ticks at t = 0, 35 and 125 s with IDENTICAL mids and a fill at
t = 0 with horizons (30, 120); show that today both horizons come back unscored with reason stale_mark.

CHANGE (EDIT the row-owned modules scripts/platformkit/execution/markout_causal.py and markout_causal_windows.py, created by row
S343 on 2026-09-21; the module change is REQUIRED; do NOT edit scripts/platformkit/ingame/quote_freshness.py):
1. A tick qualifies as a mark by TIME ONLY: it is the first same-market tick whose time (the field the module already uses for the
   window, parsed by execution/venue_time.parse_venue_time) lies inside the horizon window. Whether its price equals the previous
   tick price is IRRELEVANT and must never be consulted. Remove the freshness_by_index dependency from mark selection entirely.
2. What still disqualifies a tick is explicit and observable at capture time: a tick flagged suspended / halted / terminal, a tick
   from another market, a tick with an unusable mid, and -- NEW, optional, caller-supplied -- a tick whose own book_age_sec field
   (when present) exceeds params max_book_age_s. Existing reason codes stay (contract B2); stale_mark is now emitted ONLY for the
   book-age rule; document that new meaning in the docstring and the memo.
3. The window default becomes the bounded search from the design review: a mark must lie in [fill + h, fill + h + max_wait_s] with
   max_wait_s DEFAULT 30 s, still overridable; never an unlimited forward search.
4. summary_strict also reports, per horizon, the realized delay (mark time minus fill time minus h) as median, p90 and max, and
   the share of fills with no qualifying mark, so missingness sits beside every number.
5. tests: in tests/platformkit/execution/test_markout_causal.py, or a NEW file tests/platformkit/execution/test_markout_mark_selection.py
   when the first would exceed 300 lines -- the before-condition case now SCORES both horizons with markout equal to minus the fee
   (flat mid); an unchanged-mid tick is chosen over a later changed-mid tick; a moved-mid tick outside the window is never pulled in;
   the book-age rule; the realized-delay fields; every earlier reason-code and boundary test still passes (rewrite only tests that
   encoded price-change freshness, and say so in the memo).
6. Memo docs/evidence/harness/S356_mark_freshness_2026-09-21.md; also list every OTHER caller of quote_freshness.freshness_mask under
   scripts/platformkit (grep) with a one-line verdict on whether a price-change definition of freshness is appropriate THERE. Do
   not fix those here.

CONTROLS: construct tests only; no measured number. ACCEPTANCE: per-file tests pass; tests/platformkit/execution/test_markout.py
untouched and passing. Vocabulary follows contract Q6; automated scan required; assemble retracted-figure literals from single
digits. Memo ends with a NOT VERIFIED list. The pod is OFF.
