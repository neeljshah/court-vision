GAP S436 | sport all captured | worktree none (no build; orchestrator run in the main tree) | log none (no codex dispatch)
# Polymarket read-only capture during games: RUN the landed S397 capture beside Kalshi, supervised; count the first paired instants
CONTRACT: VERIFIER_CONTRACT.md B1-B10, Q1-Q9, A9, S1, S2 -- self-check before reporting. WHERE (S1): every step is LOCAL, main tree,
under the landed supervisor; network = the Polymarket public read-only endpoints, by the orchestrator's owner-supervised launch only.
Pod OFF. No credential, no wallet, no order, no STOP file on the Kalshi capture.
PREMISE (S2 / Q8, measured on master 7300afdb5, 2026-09-24): FALSIFIED -- a Polymarket CAPTURE already exists; the row does not build.
(a) polymarket_live_capture.py (S397, commit 54ba4c5eb) is a poller that WRITES book / trade / meta rows: :141 capture_once polls
 src.fetch_book per outcome token (:162) and src.drain_trades (:165); :217-239 run_capture loops until the STOP sentinel; :244-251 CLI
 --output-root / --max-ticks / --sports / --schedule / --state-root. Root :20 = the cache root under data + ingame_books_local (the SAME
 parent as Kalshi), but :41-45 PolymarketWriter writes the disjoint venue dir <root>/polymarket with its own lock
 <root>/polymarket/_capture.lock (local_capture_writer.py:33); STOP :21 `STOP_POLYMARKET`, distinct from Kalshi's `<root>/STOP`
 (local_capture_runner.py:255); Kalshi recovery globs only `<root>/kalshi` (local_capture_writer.py:66). Budget: GovernedClient AIMD
 (:1, :47-51), MAX_DUE_PER_TICK 40 (polymarket_scope.py:61); cadence live 10 s / pregame 120 s / idle 600 s (polymarket_scope.py:57-59),
 tick sleep 5 s (:25). Kalshi focus tick 5 s (forward_capture_profile.json:2); SERIES_BY_SPORT Kalshi-only (local_capture_runner.py:19-20).
(b) S398 is replay-time linkage + counting over archives someone else writes: cross_venue_pairs.py:195 build_pairs,
 cross_venue_scan.py:281-287 main(--kalshi --polymarket --state --pairs --certification --out). Pair window = the landed S368 skew limit
 5 s, read from coherence_scanner.py:50 by cross_venue_pairs.py:32-36 -- NOT 2 s. Before: S398 memo :101-105 paired_instants 0 on real
 rows; root cause, Kalshi polled the five paired books only before its focus window, so a pre-game Polymarket smoke paired nothing.
(c) Never run on the live root: `<root>/polymarket` absent today; supervisor children are books / state / state2 only (heartbeats in the
 capture_supervisor log dir); live Kalshi child = local_capture_runner --output-root <main tree root> --schedule 2026-09-24_maker_forward.json.
(d) Fees stay refused: S399 memo :118-121 "55 PASS, 37 MISMATCH ... status handed onward is `uncertified`"; polymarket_certification.py:7
 "A MISMATCH refuses certification"; cross_venue_scan.py:89 / :105 count fee_certification_absent / _invalid. The tape carries side and
 outcomeIndex, never taker_side (S411_spec.md:22; S412 names that the unready side for fill realism); rows keep them verbatim (polymarket_live_rows.py:29).
CHANGE: NONE to code. Orchestrator steps, recorded in memo docs/evidence/harness/S436_polymarket_run_<date>.md (A9 paths + bytes):
1. Owner-supervised launch, S391 checklist :68 form: capture_supervisor --name polymarket --log-dir <capture_supervisor dir> --min-free-mb
 2000 --max-backoff-sec 300 --gap-sec 90 --keep-awake -- python -m scripts.platformkit.ingame.polymarket_live_capture --output-root <the
 Kalshi child's root> --state-root <ingame_state_local_v2> --schedule <the day's committed served schedule> --sports <served sports>.
 Started before the first served focus window; Kalshi's supervisor, lock and STOP untouched. Stop = touch <root>/STOP_POLYMARKET only.
2. After the window: cross_venue_pairs then cross_venue_scan over that day's kalshi + polymarket + state shards, NO --certification.
3. Memo: per served game, Kalshi receipts, Polymarket receipts, paired_instants at the landed 5 s limit, unpaired counts, 429 count,
 requests total; no price comparison. Ends NOT VERIFIED (a count on one day, one route).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = paired_instants (cross_venue_scan counts JSON) per served game over the first in-game window with both captures running
  before        = 0 on every real archive (S398 memo :105) | bar = reported per game, any value; a zero keeps the S398 root-cause census
  n             = count of served games in that window (a count, not a sampled or scored metric; Q7)
  eye check     = n/a (S-row); reproduction = re-run step 2 on the committed shard paths and match the counts JSON byte for byte
  must not move = every module named in (a)-(d), forward_capture_profile.json, the Kalshi child command, root, lock and STOP, byte-identical
NON-TAUTOLOGY: every served game is listed, including unmatched pairs with their refusal reasons. Q6: calibration language only.
NEW GAP: a 2 s paired count (the requested window) needs a window argument through cross_venue_pairs.nearest (:49); not built here.
