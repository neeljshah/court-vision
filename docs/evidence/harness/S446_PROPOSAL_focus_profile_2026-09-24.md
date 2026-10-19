# S446 proposed focus close, not adopted

Status: PROPOSED. Local construct evidence only. No scheduler, profile, limiter,
service, flag or threshold is changed. Adoption requires a later owner-visible
relaunch row and a complete request accounting measurement.

Keep admission opening at scheduled start minus 120 seconds. Replace the close
instant at scheduled start plus 3600 seconds with the first valid, unambiguous,
as-of state receipt carrying normalized status `final`, plus 300 seconds.
Repeated final receipts must not keep extending the window. Missing terminal
evidence remains unresolved; it cannot silently produce a finite close time.
Post-final book availability is not assured: discovery currently requests only
open events. The follow-up must address that source limitation explicitly.

AMENDMENT 1(j): the proposed close carries a hard ceiling so a missing or
never-arriving final receipt cannot leave the window open indefinitely:
close = min(final_receipt + 300, scheduled_start + 21600). The 21600 s (6
hour) outer bound is a stated maximum covering any served sport's realistic
game length plus markout, not a measurement; a game still live at that ceiling
remains unresolved rather than silently closed. Before adoption, the proposal
must also check concurrent focus load against the two-games-per-hour capacity
rule (capture_scheduler.py:113): replacing the fixed 3600 s close with a
per-game final+300 close can let two admitted games' extended windows overlap
for longer than the current fixed-window admission ever allows, so the request
budget below must be re-derived under worst-case overlap, not just a hourly
mean. Nothing here is adopted; no scheduler, profile or threshold is changed.

AMENDMENT 3(b): the concurrent-focus check above is now PERFORMED, not deferred.
AMENDMENT 4(a) corrects it: capture_scheduler.py admits only complete two-market
games (:116) and focuses every market ticker of every admitted game, every tick
(:158, :195), so demand is per MARKET, not per game. Inputs: games_per_hour = 2
(profile maximum_scheduled_games_per_hour), ceiling = 21600 s / 6 hours
(AMENDMENT 1(j)), markets_per_game = 2 (:116), tick = 5 s (profile
focus_tick_s), rate_ceiling = 3.0 req/s (local_capture_limiter.py CEILING),
focus_percent = 45 (profile focus_share_percent). Concurrent games =
games_per_hour * (ceiling / 3600) = 2 * 6 = 12 (the worst case: every admitted
game's extended window still open at the ceiling). Required requests/tick =
concurrent_games * markets_per_game = 12 * 2 = 24 (every market ticker of every
admitted game, every tick); required rate = 24 / 5 = 4.8 req/s. Allocated
requests/tick = floor(floor(rate_ceiling * tick) * focus_percent / 100) =
floor(15 * 45 / 100) = 6 (capture_scheduler.py:147,:179's own integer budget
math, reused verbatim); allocated rate = 6 / 5 = 1.2 req/s. fits = required <=
allocated = 24 <= 6 = FALSE. This calculation is now the pure function
`concurrent_focus_fit()` in observation_support_census.py, with a construct
test fixing these exact inputs, so the figures cannot drift again.

Result: with this profile's numbers the proposed final+300-with-ceiling close is
INFEASIBLE / UNRESOLVED as stated -- the worst-case concurrent load needs 4.8
req/s of focus-class capacity and only 1.2 req/s is allocated. This requires a
later owner decision (raise the focus share, shorten the ceiling, or cap
admitted concurrency) before any adoption. Non-adoption is retained here: no
scheduler, profile, limiter or threshold is changed by this row.

The census reports accepted book receipts across all market tickers for each
served game as `observed_book_requests`. This is a lower bound on requests per served game.
It cannot recover requests with no receipt, retries, discovery or every request
producing multiple nonbook rows. `total_requests` is therefore null. A budget
which treats that null as zero is refused. Global heartbeat totals cannot be
allocated to individual games without a corresponding request log.

For a completed prospective census, let B be the sum of observed book requests,
G all served games, and L the proposed scheduled games per hour. Report B/G
with its integer numerator and denominator, then compute L*B/(3600*G).
The unresolved additional request rate must be added before comparing the total
with the unchanged 3.0 requests/second AIMD ceiling. Also check peak concurrent
games and each five-second tick, not just an hourly mean. Keep the profile's
45 percent focus allocation and all other request classes in that accounting.

Construct calculation from `test_09_post_final_complete`: the census produces
61 accepted UNCLASSIFIED book receipts for one game (every five seconds from
final through final+300 inclusive; these fixtures carry no request_class, so
AMENDMENT 9(a)/10(b) name them unclassified, never focus). With the profile's
two games/hour, the observed lower bound is 122/3600 = 61/1800 requests/
second. It satisfies 122 <= 3*3600. The focus-allocation comparison is
REMOVED here (AMENDMENT 10(b)): an unclassified rate cannot be checked
against a per-class allocation until the NEW GAP (AMENDMENT 9(b)) supplies
real request classes on capture rows. This rational comparison is construct
arithmetic only. The fixture has no pre-final book history or nonbook
request attempts, so it does not validate a full-game budget.

Real-run B, G, total request rate, peak request rate and residual request rate
are NOT MEASURED. The census preserves every served game and the missing
evidence needed to make those limitations visible. No real-run capacity
conclusion or adoption follows from this proposal.
