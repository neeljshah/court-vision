GAP G90 | sport all | worktree a2 | log cx_g90_jump_max_reader_survey
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. A READER SURVEY with a known trigger. This is contract B2.
THE DEFECT, named by the orchestrator when G88 landed at 1bccb986b: the harness gating statistic
was renamed `jump_p95` -> `jump_max`. A failure string now reads "jump_max 10.00 > 6.00" where it
read "jump_p95 10.00 > 6.00" -- SAME measured value, SAME bar, SAME verdict, DIFFERENT NAME. So:
  (a) anything PARSING failure strings for the substring "jump_p95" now silently misses the failure,
  (b) anything reading the report FIELD `jump_p95` by name may now read a stale or absent field,
  (c) anything with a stored BASELINE containing the old string will diff as changed when nothing
      behavioural changed.
Silently missing a failure is the worst of the three: it turns a FAIL into an invisible pass at the
reader, without the harness verdict itself ever moving.
PRECEDENT, and why this row exists at all: G81 was exactly this class -- a schema change with an
incomplete reader survey -- and TWO raising readers were found by an audit rather than by the
survey that was supposed to find them. So the G81 lesson applies verbatim: assume the consumer list
is LONGER than you expect until you have actually looked. Read
docs/evidence/tracking/g81_null_coverage_readers_2026-09-02.md first and reuse its survey method.
SURVEY EXACTLY THIS:
  1. Every consumer of the FIELD name `jump_p95` and `jump_p95_ft_per_s` (attribute access,
     dict/JSON key, dataframe column, SQL column, csv header, ledger key).
  2. Every consumer that PARSES failure strings at all -- not only for jump. A reader that splits a
     failure on " " and switches on token 0 is in scope even if it does not name jump today,
     because it is the mechanism that breaks.
  3. Every STORED baseline, fixture, golden file or committed json/csv under docs/evidence/ and
     data/ that contains the literal "jump_p95". State the count and whether each is a live gate
     input or a frozen historical record. A frozen historical record MUST NOT be rewritten -- it is
     what the value was when it was measured.
  4. The pod: the pod ledger and the footage cycle ledger both carry a `jump_p95` key on real rows
     (verified by the orchestrator: data/tracking/footage_cycle_ledger.jsonl rows carry
     "jump_p95": 43.81 etc). Say what happens to a ledger that now gains a differently-named key
     alongside years of rows carrying the old one, and whether any reader aggregates across both.
REPORT a per-consumer verdict: safe / needs a fix / is a frozen record. Fix only the ones that are
live and broken; for each fix, state in one clause why that reader should key off what it now keys
off. Prefer keying off a STRUCTURED field over parsing a human-readable failure string, and say so
where you find a string parser -- but do NOT rewrite every string parser in this row; name them.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = number of LIVE readers that silently change behaviour under the rename
  before        = unknown, and that is the problem; at least the ledger key is confirmed to exist
  bar           = 0 live readers silently changing behaviour, AND a complete enumerated consumer
                  list with a per-consumer verdict, AND no verdict or threshold moves
  n             = every consumer found; state the count and the grep patterns you used, so the next
                  survey can be checked against yours
  eye check     = n/a (a reader-contract survey). Reproduction = the before/after behaviour of each
                  reader you call broken, demonstrated, not asserted.
  must not move = the G88 rename itself (it is adjudicated and correct), every bar, every verdict,
                  every frozen historical record, and the coordinate contract
EVIDENCE: docs/evidence/tracking/g90_jump_max_reader_survey_2026-09-0X.md with the full consumer
table, the grep patterns, the per-reader decision, the frozen-vs-live split, and a NOT VERIFIED list.
TEST: exactly one new per-file test if you change code; run only that file. Never a full pytest.
POD: READ-ONLY. Never kill anything -- the tracking daemon and seven footage bridge lanes are live.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a2,
no push. Report the sha.
SHARED MODULE: if a fix reaches tracking_harness.py take the token in
docs/evidence/SHARED_MODULE_TOKEN.md and PUSH THE RELEASE. Prefer to change only READERS.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
