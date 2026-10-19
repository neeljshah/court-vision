# S455 Polymarket archived IDs

Build result: construct pass (pending verification).

Candidate HEAD: 8198e76ec0b6bf3d2758339085020981bd66faf3. Verification-base master: 8198e76ec0b6bf3d2758339085020981bd66faf3 -- EQUAL (`git rev-parse HEAD`/`master`, this worktree, this session); harness-h108 ff'd to this commit; edits sit uncommitted on top.
The test suite's own byte-identity BASELINE (never the moving ref `master`) stays pinned to
the immutable pre-edit blob at c992b203f27148c635efd54db4bfe30f4befc3ed (AMENDMENT 2d);
`local_capture_runner_trades.py` is byte-identical between that commit and this worktree's
HEAD (`git diff` empty; LF-normalised sha256
077294e24cd4d813dfe05b6bfefe480636bd6abca8beb2dc47285c0a9b6ea72c, regenerated this session
-- corrects a miscomputed figure in the FIX 1b memo text), confirming the must-not-move
file was not touched.

FIX 1b (round 1 both tiers REJECTed; every BLOCKING and CORRECTION addressed below):

1. TIER1 BLOCKING #1 / TIER2 BLOCKING (a) -- `remember_archived`'s plain FIFO evicted
   protected ids. Reproduction (quoted, run this session against the round-1 candidate's
   direct `group.remember_archived()` calls): `{archived_len: 100000, boundary_retained:
   False, recent_retained: False}`. Fix: new sibling module
   `scripts/platformkit/ingame/polymarket_archived_ids.py` (35 lines) holds
   `remember_archived_protected(group, trade_id, metrics)`, a route-local bounded insert
   that evicts only the oldest id outside `group.boundary | group.seen`; if none is
   evictable the new id is refused via `metrics.drop("trades", "archived_bound_no_evictable")`,
   never an unbounded grow. All five sites (:61, :75, :79, :100, :134 on the candidate)
   now call it. Shown passing (same probe, protected path): `{archived_len: 100000,
   boundary_retained: True, recent_retained: True, refusals: 0}`. Regression test:
   `test_protected_ids_survive_eviction_route_local_bound` (and the sibling
   `test_no_evictable_id_refuses_the_new_id_never_grows_unbounded` for the no-evictable
   refusal path).
2. TIER1 BLOCKING #2 / TIER2 BLOCKING (a) -- no cap-crossing second-drain construct;
   `_fixture_bytes` never reached `append_page` with real content. Fix: `_fixture_bytes`
   now takes a `pages` argument and redrains a real trade (exercising :100 through
   `append_page`/`_TickRows.flush`); a new construct,
   `test_cap_crossing_second_drain_rewrites_an_evicted_key`, seeds a group past
   ARCHIVED_LIMIT + SEEN_LIMIT distinct keys through `seed_group` (the real archive-tail
   path), then redrains the evicted key's own trade through `drain_trades` for both the
   candidate and the immutable before-edit blob. Measured this session: baseline (before-
   edit blob, unbounded raw `.add()`) `written_again=False, duplicate_refusals=1` -- it
   refuses the key because its `archived_ids` never evicts anything; candidate (bounded)
   `written_again=True, duplicate_refusals=0` -- it re-writes the row once. This is
   exactly the AMENDMENT 1(a)-adjudicated accepted limitation, and it is a genuine
   divergence from the baseline (not byte-identical), so this one construct is compared
   on its measured counters, not on full-file byte equality.
3. TIER1 BLOCKING #3 / TIER2 CORRECTION (pinned baseline uses the moving ref `master`) --
   fixed: `_master_tape()` now pins `MASTER_SHA = "c992b203f27148c635efd54db4bfe30f4befc3ed"`
   and reads `git show <sha>:...`, never `master`.
4. TIER2 BLOCKING (b) -- the mutation check passed on 4 of 5 sites vacuously, because on
   the before-edit blob `archived_order` (the deque) is never touched by raw `.add()`
   while `archived_ids` (the set) still grows -- so `before == after` held on both master
   and candidate without proving anything. Fix, exactly as specified: case 1
   (`test_seed_group_bounds_250000_replayed_archived_trade_rows`) now asserts
   `set(group.archived_order) == group.archived_ids` after `seed_group`, plus an aliased
   archived row (`trade_key="alias-000000"` whose recomputed canonical differs) so both
   the stored key (:75) and the canonical key (:79) are independently pinned; case 2
   (`test_resend_does_not_grow_or_reorder_the_bounded_archive_cache`) asserts the same
   invariant plus `len(group.archived_ids) == 2` after the first drain, pinning :100 and
   :134 together. Measured this session on the before-edit blob: case 1's invariant --
   `archived_order=[] archived_ids_len=6` (FAILS); case 2's invariant --
   `archived_order=[] archived_ids_len=2` (FAILS). Both PASS on the candidate (verified
   this session).
5. TIER2 CORRECTION (memo shas / before-results / RSS / 1(e)) -- fixed by this rewrite:
   two full shas above, before-results table below, RSS line and 1(e) statement below.
6. TIER2 CORRECTION (memo opened with a self-verdict, no FIX history) -- fixed: this memo
   opens with "Build result: construct pass (pending verification)" and carries this FIX
   1b section.
7. TIER2 NOTE (seed-time closure metric at :58 undercounts above the cap) -- accepted, no
   code change: above ARCHIVED_LIMIT a closure key evicted from `archived_ids` but still in
   `seen` is not counted as `duplicate_trade_backfill_closed` even though the write itself
   still refuses correctly (seed writes nothing); covered by the accepted divergence in
   finding 2 above.
8. TIER2 NOTE (`local_capture_runner_trades.py:69-75` used unchanged; the AMENDMENT 1(a)
   contract holds for effective refusal via `seen`, not archived_ids membership) -- now
   largely moot at the route level: none of the five sites call the raw, unprotected
   `TradeGroup.remember_archived` any more (they call `remember_archived_protected`,
   finding 1). The raw method itself is untouched (must-not-move) and
   `test_evicted_archived_identity_is_still_refused_by_seen_cache` still exercises it
   directly and unchanged, per spec case 3.

FIX 1c (round 2 both tiers REJECTed; every BLOCKING and CORRECTION addressed below):

1. TIER1 BLOCKING / TIER2 BLOCKING 1(a) -- the cap-crossing construct (test:193-220)
   crossed the cap by writing the archive directly and calling `seed_group`, then
   drained once, with no second drain, no published heartbeat, and no checkpoint/archive
   byte comparison. Fix: `_history_and_redrain` (test_polymarket_archived_ids_bound.py)
   now builds the ARCHIVED_LIMIT+SEEN_LIMIT+1 = 110001-trade history through a FIRST
   real `drain_trades`/`_TickRows.flush` call (one page, `limit` above the count so the
   short-page-below-watermark condition closes it cleanly, `candidate.backfill` goes to
   `None`), publishes a heartbeat, then calls `drain_trades` a SECOND time on the same
   group -- since `backfill` is `None` this genuinely restarts a fresh backfill at offset
   0, exactly like the venue's own always-restart drain -- redraining one already-written,
   now-evicted trade (index 1, not index 0: index 0 is the tick's single newest trade and
   lands in `group.boundary`, which would mask the archived-cache eviction this construct
   exists to prove), and publishes a second heartbeat. Measured this session (both routes,
   same fixture): the checkpoint (`_trade_state/*.drain.json`) is byte-identical; the
   archive's shared first 110002 lines are a byte-identical prefix on both routes, and the
   candidate has exactly one more line (110003 vs 110002) -- the rewritten trade row;
   `rows_written_tick`/`trades_written_tick` are 1 on the candidate vs 0 on the baseline,
   `rows_written_total`/`trades_written_total` are each exactly 1 higher on the candidate,
   and the baseline's `error_counters` carries one `duplicate_trade_key` the candidate's
   does not. `last_success_ts`/`last_write_ts` are IDENTICAL on both routes [CORRECTED by
   FIX 1d finding 3 below: a fixed-clock coincidence, not the real divergence] -- NOT "null
   vs set" -- because the shared history drain (byte-identical on both routes; archived_ids/
   archived_order are never persisted, so the write decision up to the cap is unaffected)
   already set them on both before the redrain, and the baseline's redrain writes nothing
   new, so `_prior()` simply carries the value forward. This is a genuine, measured
   divergence from the round-2 verdict's own illustrative reproduction (which used a
   direct-write history and a single publish, so it had no prior heartbeat to carry
   forward); it is reported here as actually measured against the AMENDMENT-3(a) construct
   itself, per rail (c), not assumed from that reproduction. Regression test (rewritten):
   `test_cap_crossing_second_drain_rewrites_an_evicted_key`.
2. TIER2 BLOCKING 1(b) -- the AMENDMENT 2(a) protection was pinned only on the helper
   module's own unit tests; reverting any one of the five route call sites to the round-1
   plain `group.remember_archived(key)`/`candidate.remember_archived(key)` passed every
   existing route construct (5 of 5 reversions passed). Fix: new sibling file
   `test_polymarket_archived_ids_bound_1c.py`, construct
   `test_boundary_and_recent_ids_survive_eviction_at_every_route_site`. `T_KEY` is seeded
   as the single OLDEST archived id (via `seed_group`'s :75 trade-replay path), one short
   of `ARCHIVED_LIMIT - 1` filler ids follow it, then a `trade_backfill_closed` row (:61)
   whose `drain_boundary_ids=[T_KEY]` sets `group.boundary={T_KEY}` -- this reaches the cap
   with zero evictions so far. Four more insertions follow, each crossing the cap by
   exactly one and each routed through a DIFFERENT one of the remaining call sites: a
   second closure row (:61 again), a new plain trade (:75), an aliased trade whose stored
   key duplicates the id the immediately preceding row just inserted (so :75 is a genuine
   no-op there) and whose recomputed canonical is fresh (:79), then one live `drain_trades`
   call carrying one new trade (:100) that closes immediately after (:134). Because T_KEY
   is the literal oldest surviving entry in `archived_order` at every one of these steps
   under correct (protected) code, an UNPROTECTED insert at any single site evicts T_KEY
   specifically at that step -- proven by manually reverting each of lines 61, 75, 79, 100
   and 134 in `polymarket_live_trades.py` to the plain `remember_archived` call, one at a
   time, and rerunning this construct alone: measured this session, all 5 of 5 reversions
   now FAIL (previously 5 of 5 passed), each restored to the protected call afterward and
   `git diff` re-confirmed unchanged (untracked, this row's own five-site diff only). The
   construct also asserts `"closure:closure1" in group.archived_ids` after the same five
   steps, covering "recent" (seen-based, not boundary-based) protection in the same run.
   The first alias-row design (stored key = T_KEY itself, intended as a same-value
   duplicate) was WRONG: if T_KEY had already been wrongly evicted by an earlier mutated
   site, the still-correct :75 call would silently re-insert (rescue) it there, masking
   the earlier site's mutation -- caught by the mutation run itself (sites 61 and 75 did
   not fail on the first attempt); fixed by duplicating a key that cannot depend on T_KEY's
   own fate ("plain-000000", inserted by the immediately preceding step).
3. TIER2 CORRECTION 1(c) -- test 6 (`test_redrained_backfill_closure_is_refused_as_a_
   duplicate`) had no before-edit-blob result, and constructs 1/2's 32/18 neighbour-count
   claim was unverifiable given the worktree already carried the edit. Fix: the FIX 1b
   per-construct table below is corrected to attribute the 32/18 counts to this session's
   own measured runs (below), and construct 6 is documented as carrying no master analog
   (see the updated per-construct table).
4. TIER2 CORRECTION 1(d) -- SHA WORDING: fixed above (Candidate HEAD / Verification-base
   both stated as the current worktree HEAD, 2233efc71, with an explicit note that the
   repo's shared `master` ref has since moved to an unrelated row in another worktree).
5. TIER2 NOTE 1(e) -- membership at the cap no longer rebuilds a `boundary | seen` union
   set on every insert past the cap: `polymarket_archived_ids.py:29-30` now checks
   `old not in group.boundary and old not in group.seen` directly inside the generator
   (identical result, no allocation). The `archived_bound_no_evictable` counter in that
   same module counts INSERTION ATTEMPTS refused, not distinct refused ids: a single id
   re-offered while nothing is evictable is counted once per offer, not once total (no
   code change; this is the existing, intended semantics, stated here per the note). The
   `_master_tape()` baseline in test_polymarket_archived_ids_bound.py now asserts
   `git rev-parse c992b203f27148c635efd54db4bfe30f4befc3ed:scripts/platformkit/ingame/
   polymarket_live_trades.py` equals the pinned blob hash `67e660b04d004d330e771cd8b2b371
   8878194631` explicitly, and calls `pytest.skip` with a named reason (git unavailable,
   or the blob hash moved) instead of failing outside a full checkout that holds that
   historical object.

FIX 1d (round 3 both tiers REJECTed; every BLOCKING and CORRECTION addressed below):

1. TIER1 BLOCKING #1 -- construct 6 called only the candidate-bound `scenario()`,
   never measured on c992b203f. Fix: `_closure_scenario(route, root)` swaps
   `test_polymarket_live_trades`'s module-global `tape` (what `scenario()`
   actually resolves -- Opus finding 3) to the given route, then restores it.
   Measured: `duplicate_closures == 1` on the candidate AND on `_master_tape()`
   (matches Opus's own c992b203f measurement).
2. TIER1 BLOCKING #2 -- comparison validated only prefix/count/type/key. sol's
   reproduction (quoted): inject `status: healthy -> CORRUPTED`,
   `existing_assertions_pass` stays True -- reproduced this session
   (probe_s455_finding2.py, real construct): True both uncorrupted and corrupted.
   Fix: `set(cand_files) == set(base_files)`; the rewritten archive line
   byte-for-byte vs the baseline's own original line for the same trade; the
   heartbeat by full-object equality against `base_hb` with ONLY the enumerated
   differences (probe_s455_diff.py, exhaustive recursive diff of the real
   construct's two heartbeats): the four counters, `last_success_ts`/
   `last_write_ts` (finding 3), `error_counters` minus `duplicate_trade_key`, and
   three `sources.trades` leaves (`rows_written`, `last_write_ts`,
   `drops_by_reason` minus `duplicate_trade_key`) -- nothing else differs.
3. TIER2 BLOCKING -- FIX 1c's "IDENTICAL on both routes" claim was a fixed-clock
   coincidence (reproduced, probe_s455_finding1.py, no skew: both routes read
   `last_write_ts=2026-09-22T22:35:00.501000Z`). The candidate's rewrite REFRESHES
   both fields (local_capture_writer.py:138-140); the baseline carries the prior
   value forward via `_prior()`; the watchdog reads `last_write_ts`
   (capture_watchdog.py:185). With a redrain clock 60s later (reproduced):
   candidate `2026-09-22T22:36:00.000000Z`, baseline still
   `2026-09-22T22:35:00.501000Z` -- candidate > baseline. Fix:
   `_history_and_redrain` sets `redrain_client.metrics.utc_clock = lambda: NOW +
   timedelta(seconds=60)`; the construct asserts the exact candidate value, that
   the baseline's two fields match each other and are not None, and
   candidate > baseline.
4. TIER2 CORRECTION -- boundary-only protection was pinned nowhere: test:102
   seeded the protected id into BOTH `group.boundary` and `group.seen`. Fix:
   `group.boundary, group.seen = {"id-000000"}, set()` (boundary-only);
   `test_no_evictable_id_refuses_the_new_id_never_grows_unbounded` already pins
   seen-only. Reproduction (probe_s455_boundary_mutation.py -- a standalone copy
   of the eviction generator with the boundary check removed, run against the
   real ARCHIVED_LIMIT=100000 loop; the module on disk was never edited): OLD
   seeding, mutated helper: protected id survives=True (the gap); NEW seeding,
   mutated helper: survives=False (fix catches it); real helper: survives=True
   under both (no regression). bound_1c.py's docstring (:82-93) corrected: T_KEY
   is protected by BOTH boundary and seen, not boundary alone.
5. TIER2 CORRECTION -- memo :184-186's "no master analog" claim is false; fixed
   by finding 1.
6. TIER2 CORRECTION -- memo :166-167's 32/18 heading mislabeled "before-edit";
   retitled below.
7. TIER2 NOTEs (site-revert 5/5; helper module correct) -- no code change.

FIX 1e (round 4 ACCEPTED WITH CORRECTIONS): SHA wording, construct 8's FAILS-on-master result, the RSS citation, and test:282's pinned last_write_ts value, all fixed below.

Regression counts on the candidate tree (this session, AMENDMENT 4c): test_polymarket_
live_trades.py 32 passed; test_polymarket_live_capture.py 18 passed; the before-edit 32/18
is carried from AMENDMENT 2's host facts, not re-measured on c992b203f. Change: the five
direct `archived_ids` mutations now call `remember_archived_protected`; no other
production file changed.

Per-construct before-results on the immutable before-edit blob (measured this session,
not assumed):
1. `test_protected_ids_survive_eviction_route_local_bound` -- no master analog; exercises
   the new sibling module directly (the module did not exist before this round).
2. `test_no_evictable_id_refuses_the_new_id_never_grows_unbounded` -- same, new construct.
3. `test_seed_group_bounds_250000_replayed_archived_trade_rows` -- FAILS: the
   `archived_order == archived_ids` invariant fails (`archived_order=[] len(archived_ids)=6`)
   and the 250000-replay bound fails (`len(archived_ids)==250000`, not 100000, i.e.
   unbounded growth -- the row's own premise).
4. `test_resend_does_not_grow_or_reorder_the_bounded_archive_cache` -- FAILS: same
   invariant (`archived_order=[] len(archived_ids)=2`).
5. `test_evicted_archived_identity_is_still_refused_by_seen_cache` -- PASSES: unchanged
   must-not-move behavior, identical on both.
6. `test_redrained_backfill_closure_is_refused_as_a_duplicate` (rewritten, FIX 1d
   finding 1) -- route-parameterised via `_closure_scenario`; measured on BOTH
   routes: `duplicate_closures == 1` on the candidate and on `_master_tape()`.
7. `test_cap_crossing_second_drain_rewrites_an_evicted_key` (rewritten, FIX 1c/1d)
   -- runs both routes INSIDE the same construct (two real drains + two publishes
   each); see FIX 1c finding 1 / FIX 1d finding 3 for the full measured divergence.
   The row's accepted, spec-adjudicated limitation, not a pass/fail vs the blob.
8. `test_boundary_and_recent_ids_survive_eviction_at_every_route_site` (1c file, FIX 1c
   finding 2) -- FAILS on c992b203f at 1c:74 (archived_ids exceeds ARCHIVED_LIMIT, measured
   100003 ids; raw `.add()` never evicts): reproduced via `_protected_ids_survive(_master_
   tape(), tmp)`, AssertionError there. Proven by 5-site manual mutation, see finding 2.

After results (FIX 1d, measured this session): test_polymarket_archived_ids_bound.py 7
passed in 110.12s; test_polymarket_archived_ids_bound_1c.py 1 passed in 4.45s standalone;
trade regression 32 passed in 2.22s; capture regression 18 passed in 1.12s. LOC: route 299
(CRLF working-tree checkout of an LF git blob, per `core.autocrlf=true` -- see A9
identities), sibling module 37, test 300, sibling test file 109.

RSS observation (unmeasured this session; carried from the spec's binding premise): the
Polymarket capture child (pid 21752) grew 277 -> 293 MB RSS 22:3xZ-23:34Z (S453 AMENDMENT 2
NEW GAP). AMENDMENT 1(e): this row bounds one group's archived-id set; it claims nothing
about process RSS, which stays retained per group with no group-retirement mechanism
(polymarket_live_capture.py:129, S454's scope); see FIX 1c finding 1 and FIX 1d finding 3
for the greater-than-ARCHIVED_LIMIT-per-overlap limitation (same shape as S453 AMENDMENT 1(c)).

A9 identities (LF-normalised; the working-tree checkout of the route carries CRLF from
`core.autocrlf=true`, so both are given; regenerated from disk this session, as the last
edit, and re-asserted by re-reading this memo before reporting): route SHA-256
BD3B96301DD04C51C6D145609D2B9D92BBB002E6E4DAB8228B5127F4EADAB03A (UNCHANGED since FIX 1b --
not touched this round; `git status` clean on this path); sibling module SHA-256 (UNCHANGED
since FIX 1c, confirmed by `git status` clean this round -- no code change per finding 7)
248102364100675FD22C2382BB722524BE5CC746E70D06F513DBA6B54EFA491B; test SHA-256 (CHANGED,
FIX 1e test:282 hardening) CA60D01BC31066BE69538C4CDAA8870107EC4EC8CFB50D3609F354F17D18B4A1;
sibling test file SHA-256 (CHANGED, FIX 1d finding 4 docstring correction)
F8C62B011B2FE1EF6440CFC68609D9A8BB6F9A35139E07EFD759770403A8F1A9. Inputs opened (unchanged
from round 1, JSON, no resolution): `s397_data_trades.json` 1249 bytes SHA-256
E5E592B660357A3CBBAB79208B22B9CA385C76E18000D508A5D7E253983258A0; `s397_gamma_events.json`
3241 bytes SHA-256 B81A772FB0A59BF097737554D41ADAEE422A3353A18913829A9D76E33B7FFA09;
`s397_clob_book.json` 552 bytes SHA-256
C6952A6CFECD2E07A5D0D4226C0515889171A94871E72D403B081D1C9D83ED2A; `s397_clob_market_meta.json`
712 bytes SHA-256 7900B17FBB050C255048779921B8EA06425EBB553573943B340DCCAEB3025D0B.

Contract self-check: A9 identities above; B1-B11 applicable checks pass (enumerated
construct, additive route change, no reader/schema change, no deployment, no changed bar);
Q1-Q5/Q9 not scored-route conditions; Q6 prose checked; Q7 construct enumeration applies;
Q8 premise quoted above; S1 local; S2 remeasured this session; S4 no ledger count applies.

NEW GAPS (round 4, Opus finding, not fixed here): an id that is itself already protected
is refused from archived_ids when nothing else is evictable instead of inserted as a no-op; duplicate suppression still holds via seen; theoretical, needs ~90000 boundary ids.

## NOT VERIFIED

RSS over a full serving night after an owner-visible relaunch was not measured this
session (carried unmeasured, per AMENDMENT 1(e)). The greater-than-ARCHIVED_LIMIT-per-
overlap limitation is demonstrated only by the construct above, not observed on a real
market. No live process, lock, sentinel, output root, network, or pod was touched.
Whether a real Polymarket market's trade+alias+closure key count actually crosses
ARCHIVED_LIMIT in practice was not checked. Pytest runs were measured on this host only,
this session; no other host or load condition was tried (this host is under other
concurrent load this session -- the heavy 110001-row constructs took noticeably longer
wall-clock than FIX 1c's own prior timings; not investigated further). The FIX 1c
finding-2 five-site mutation proof was performed by manually editing and restoring one
line at a time, confirmed restored by `git diff`; not independently re-run, not wired
into CI. The FIX 1d finding-4 boundary-only mutation proof (probe_s455_boundary_
mutation.py) used a STANDALONE replica of the eviction generator with the boundary check
removed rather than editing-and-restoring the module on disk; also not independently
re-run, not wired into CI.
