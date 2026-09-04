GAP S300 | sport nba | worktree aXX | log cx_s300_canonical_tail_panel
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
ORDER: S280 already ran without this rule; S300 output is S280's follow-up check, not a prerequisite.
CONTEXT: audit gap 1: the tail state panel is not canonical -- nba_price_series.parquet row group 0 has
  171,546/200,000 rows sharing event+venue+ts with another side; a one-home-probability row per venue/event/ts is
  required for the S280 cross-venue follow-up and tail rows. Inputs: nba_price_series.parquet (8,399,632 rows, key
  event_key, first KXNBAGAME-26APR26BOSPHI) and nba_checkpoints_full.parquet (465,249 / 1,593).
WHERE: local; pyarrow row-group reads of the two verified parquets only.
PREMISE: reproduce 1,593/1,593 Polymarket ticker overlap and all printed schemas.
LIMIT: print cross-venue game overlap; if below 30 games, report CLOSED AT LIMIT for that arm.
CHANGE: filter moneyline; Polymarket side=home is canonical; for Kalshi use side==parsed home, else complement the
  parsed away side; account every excluded source row by reason.
  Seal a prereg FIRST as its own commit (LF; seal = SHA-256 of the STAGED bytes above the seal line via git show
  :<path>, verified with git show HEAD:<path>; the seal TEST reads the FILE, normalizes CRLF to LF, hashes above
  the seal line). Print RSS before/after; a scorer above 500 MB runs via ~/bin/pod_run <aN> --fetch <outputs> --
  <command> (B5 NOTE). Never write data/ or docs/research/; never rewrite an existing artifact (new dated names).
ACCEPTANCE RULE:
  metric = duplicate canonical keys, join coverage, probability replay error, tail log-loss/ECE.
  before = row group 0 has 171,546/200,000 rows sharing event+venue+ts with another side.
  bar = 0 duplicate canonical keys; 1,593/1,593 Polymarket games; replay error <=1e-12.
  n = every row group; game clusters printed per venue and overlap.
  eye check = n/a; reproduction = rebuild panel and diff counts and scores.
  must not move = source parquets, +0.004 bar, incumbent probabilities.
NON-TAUTOLOGY: keep every source row in an accounting table; choose side before scoring.
EVIDENCE: docs/evidence/harness/S300_canonical_tail_panel_2026-09-04.md plus CSV/JSON.
REQUIRED EVIDENCE DURABILITY: archive canonical keys, exclusions, paired losses, and timestamps.
RE-EMITTED TABLES: preserve every source column and add aliases only.
TEST: one per-file test for complements, duplicate timestamps, and two venue namespaces.
REPORT: premise counts, the metric table with CIs, RSS, test line, SHA. No push. NEVER PARK.
