# S360 NBA joined corpus -- PREPARE ONLY

Verdict: prepared and fixture-tested; real conversion NOT VERIFIED.
Machine: local CPU in C:/Users/neelj/nba-harness-h18, synthetic inputs only.
Vocabulary follows contract Q6; automated scan required.

Binding before-condition, rerun before creating the converter:

```text
ls scripts/platformkit/ingame/nba_checkpoints_to_joined.py
ls : Cannot find path 'C:\Users\neelj\nba-harness-h18\scripts\platformkit\ingame\nba_checkpoints_to_joined.py' because
it does not exist.
```

The command exited 1. The S86 row in
`docs/evidence/RESULTS_LEDGER_SYSTEM.md` names
`docs/evidence/harness/S86_nba_every_tick_2026-09-03.md`.
That tracked memo identifies
`data/cache/eval_gate/s86_nba_every_tick_2026-09-03.csv` and its companion
`data/cache/eval_gate/s86_nba_every_tick_2026-09-03.json`.
The tracked writer `scripts/platformkit/eval_gate/s86_nba_every_tick.py`,
function `run`, declares these CSV columns verbatim:

```text
game_id, game_date, unit, ts, period, game_clock_s, score_home, score_away,
margin, elapsed, rem, period_bucket, margin_bucket, rem_bucket, informative,
p0_asof, elo_until_date, model, market, y, loss_model, loss_market, d
```

This identifies the archive and schema from tracked code; neither archive was
opened. The memo documents a screen-side archive, not complete model coverage.
The converter accepts its CSV `model` column. Caller-supplied parquet/JSONL
requires `game_id`, `ts`, and `model_prob`; it never constructs a model.

Only the three spec-listed files are added. ISO grammar uses the landed
`parse_venue_time` after precision validation; join keys use exact UTC text.
NBA clock conversion imports the landed S86 `rem_minutes`:
regulation seconds remaining = (4 - period) * 720 + game_clock_s; overtime
seconds remaining = game_clock_s in the current overtime period. Future
overtime periods are unknown and never inferred from later rows. Calling the
existing rule with zero clock supplies the offset without rounding away the
original clock's fractional seconds.

Exact (game_id, parsed timestamp) matches supply model values. Missing/null
models remain null and count in the census. All checkpoint rows are retained.
Identical model duplicates have one meaning; conflicting values for a joined
key raise. Rows sort by timestamp, then known trade first, then canonical row
bytes, so ties and input permutations are deterministic. The last observed
tick supplies close_ts metadata only. Current-state features use no outcome
or future tick. Game outcomes must be binary and consistent.

Trade age is zero on a known trade and elapsed timestamp seconds after the
last known trade. Before a known trade it is null. Unknown traded values reset
that knowledge unless a trade is known at that same timestamp. Traded and
market_ticker are carried unchanged; no population is filtered.

Parquet reads use one row group at a time with batches capped at 2048 rows.
Normal conversion uses a disk SQLite index and sort with a bounded page cache;
JSONL files are streamed and hashed incrementally. Check mode creates no
scratch files and rescans the model source for each checkpoint batch, trading
runtime for bounded memory. No whole table or whole game row list is loaded.
Timestamps carrying nonzero precision beyond six fractional digits raise.
Missing required fields and nonfinite consumed numbers raise rather than become
zero. No sizes or quantities are parsed. There are no except clauses.

The corpus directory contains one SHA-256-named JSONL file per game,
manifest.json with canonical compact `{"files": {name: sha256}}`, and census.json.
An existing corpus directory is refused. Scratch output is renamed into place
only after validation and writing finish.

Reproduction performed locally:

```text
python -m pytest tests/platformkit/ingame/test_nba_checkpoints_to_joined.py -q -p no:cacheprovider
43 passed
python -m scripts.platformkit.ingame.nba_checkpoints_to_joined --help
exit 0
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/ingame/nba_checkpoints_to_joined.py tests/platformkit/ingame/test_nba_checkpoints_to_joined.py docs/evidence/harness/S360_nba_joined_corpus_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S360_spec.md
9 PASS, 0 FAIL (including automated vocabulary scan)
```

The tests enumerate n = 43 (CONSTRUCT) cases, using temporary synthetic files.
They cover exact joins and missing values, regulation and overtime, canonical
ordering and hashes, close timestamps, outcome flips and future truncation,
unknown trade age, invalid inputs, fractional timestamps, bounded batches,
check-mode parity/no writes, duplicate keys, and existing-output refusal.
The landed `select_rows(rows, "nba_checkpoints")` accepts one eligible tick out
of four in the join fixture and counts three missing-model exclusions.
No tracked test depends on a gitignored fixture.

Finisher command, after landing, from C:/Users/neelj/nba-ai-system (NOT RUN):

```text
python -m scripts.platformkit.ingame.nba_checkpoints_to_joined --checkpoints C:/Users/neelj/nba-ai-system/data/cache/inplay_odds/nba_checkpoints_full.parquet --model-side C:/Users/neelj/nba-ai-system/data/cache/eval_gate/s86_nba_every_tick_2026-09-03.csv --out-dir C:/Users/neelj/nba-ai-system/data/cache/ingame_grade_joined
```

Appending `--check` prints the census without writing. Real model coverage
must be read from that census; this preparation does not establish a second
powered corpus. The spec-required directory name `nba_checkpoints_r1` is not
in the landed scorer's corpus-name mapping, although the required direct
`select_rows` call with `nba_checkpoints` accepts the fixture shape.

Contract B/Q self-check: additive files only, no row exclusions or sampled
results, no fit or scored comparison, no threshold changes, no deployment,
no ledger charge or prereg action. B4/B6 are inapplicable to this new converter.
Q1-Q5/Q9 have no scored claim here. Q7 uses enumerated constructs; Q8's premise
was rerun. No real archive, network, or pod operation occurred; the pod is OFF.

## FIX 1b

The original parser truncated ISO fractions before checking the join key.
Both checkpoint and model timestamps now reject nonzero digits beyond six
fractional places before parsing. The converter stops on the first such row
with REJECT and rejected_by_reason={"timestamp_precision":1}; it publishes no
corpus. This count names the encountered rejection, not a full-input census.
Trailing zero precision remains valid. Numeric inputs use Decimal from the
original JSON/CSV spelling or the integer/float string, never Decimal(float).
Canonical UTC text keys preserve exact microseconds in memory and SQLite.
Regressions cover the two distinct seven-digit ISO fractions, each input side,
integer and whole-second float equivalence with ISO, fractional float binary
representation, trailing zero fractions, and long numeric source precision.
FIX 1b local reproduction: the same per-file pytest command above passed all
65 tests (CONSTRUCT); the CLI --help command exited 0. The initial run had
5 failures and 60 passes because Python 3.10 requires normalized ISO fractions;
normalization now follows precision validation. Contract preflight uses the
same three paths, master base, and S360 spec listed above.
Contract preflight: 9 PASS, 0 FAIL, including vocabulary and the 300-line cap.

NOT VERIFIED:
- Real archive existence, byte sizes, contents, model provenance, or full-corpus coverage.
- Real conversion and scorer loading through the required r1 directory name.
- Peak RSS below 600 MB, full-corpus runtime, and real stale-price coverage.
- Any measured calibration, execution, or markout result; no such run occurred.
- Independent verifier acceptance, landing, or commit creation.
