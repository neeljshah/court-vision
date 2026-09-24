GAP S425 | sport nba | worktree harness-h82 (master-based) | log cx_s425_trial_line_producer

# The runner requires a launch line that nothing produces

SINGLE PROBLEM: the landed NBA charged-trial runner (S394) refuses to start unless the sealed prereg carries exactly one
`NBA_TRIAL_JSON: {...}` line, and no landed tool writes that line (seal runbook .planning/direction/nba_seal_runbook_2026-09-23.md
E3 and step B2(e)). The S402 seal package emits FROZEN pins, CENSUS.* lines and NBA_CENSUS only. Assembling 1,593 ids by hand
repeats landing lesson 26. A wrong id set breaks the S395 exposure check without any message: the 1,570 primary ids instead of the
1,593 eligible ids make the runner recompute folds on the subset and drop scored games.
BINDING BEFORE-CONDITION (measured by the Opus spec writer on 2026-09-23 against master c6424cce1, read-only):
(a) scripts/platformkit/ingame/nba_four_arm_trial_guards.py VERBATIM --
    :96 `declarations = re.findall(rb"^NBA_TRIAL_JSON: (.+)$", normalized, re.MULTILINE)`
    :97-98 `if len(declarations) != 1:` / `raise ValueError("refused=1 missing or duplicate NBA_TRIAL_JSON declaration")`;
    :99 `config = json.loads(declarations[0], object_pairs_hook=unique_object)` (a duplicate key is refused);
    :100-102 family == "ingame_four_arm_nba_r1", tier in ("T2", "T3"), corpus == "nba_checkpoints_r1" == corpus dir name
    :103 manifest_sha256 must fullmatch [0-9a-f]{64}; :105-108 primary_game_ids is a non-empty list of unique non-empty str
    :109-110 `config["census"] = denominators(config["census"])` and the same for primary_census; denominators (:65-85) requires
    every COUNTS key (:16-19, 14 strict ints), every HISTOGRAMS key (:20-21, 3 dicts) and folds records (date, warmup, train_games, train_ticks)
    :115-123 manifest_pin: sha256 of json.dumps(parsed manifest, sort_keys=True, separators=(",",":")) must equal manifest_sha256.
(b) nba_four_arm_trial.py VERBATIM -- :138 `ids = set(config["primary_game_ids"])`; :139 `primary_rows = [r for r in rows if
    r["game_id"] in ids]`; :140-141 refuses `missing primary games`; :142-143 `_, primary_counts = select_rows(primary_rows,
    corpus.name)` then `guards.check_census(census, config, primary_counts)` (:131-132 compares the RECOMPUTED census to
    config["census"] and primary_counts to config["primary_census"]); :153 `dates = sorted(config["census"]
    ["games_per_first_tick_utc_date"])` gives the ledger range; :180-181 re-predicts on primary_rows when fewer than all rows.
(c) nba_seal_package.py:188-199 (_block) emits FROZEN_ORDER pins, `CENSUS.<key>` and `NBA_CENSUS:` over
    nba_seal_package_checks.py:13-15 CENSUS_KEYS only (10 keys, one histogram). It has NO duplicate_identical,
    conflicting_duplicate_key, state_transition_ticks, games_without_parseable_tick, warmup_folds, the two date histograms or
    folds. So the S402 output cannot supply the census blocks. The tracked record
    docs/evidence/harness/S402_reconciliation_real_2026-09-22.md carries no census lines at all (its JSON was scratch).
(d) The census source is the file the package reads through --census (S402 AMENDMENT 1(d)):
    data/cache/ingame_grade_joined/_census/nba_checkpoints_r1_S387_master/census.json. Measured: scored false, sports {nba}, and
    sports.nba carries all 14 COUNTS, all 3 HISTOGRAMS and folds (311 records). files = games = eligible_games = 1593; per_game has
    1593 keys, equal to the sorted corpus ids.
(e) Frozen pins, quoted from the tracked record: `ELIGIBLE_GAMES: 1593`, `ELIGIBLE_GAMES_SHA256:
    "04c182de96f7433ee1e65d355102e82dcd58693f960bac266d62ef7c66453805"`, `PRIMARY_GAMES: 1570`, `PRIMARY_GAMES_SHA256:
    "3d1344bf1cc123da915d911c84c1a911ed88df922902a65fb18570f6abe838c9"`, `MANIFEST_SHA256:
    "5c4c1d109278c9262fbba1157d0d49afd6af16d2e9ead447b38baeb3526fd9a5"`, `WARMUP_GAMES: 23`, `FOLDS: 311`, `WARMUP_FOLDS: 5`.
    Re-measured 2026-09-23: nba_seal_package_checks.identities over the corpus gives 1593 sorted ids. eligible_digest(ids) =
    04c182de... and the canonical manifest digest (runner rule a:115-123) = 5c4c1d10... (the manifest has only "files").
(f) With ids = all 1593 games, primary_rows == rows, so primary_counts == census and primary_census == census (runbook B2(e)).
CHANGE (owned NEW files only: scripts/platformkit/ingame/nba_trial_line.py <= 300 LOC,
tests/platformkit/ingame/test_nba_trial_line.py, docs/evidence/harness/S425_nba_trial_line_2026-09-23.md. The runner, its
guards, the S402 package and the S382 draft are NOT edited):
1. Emit mode. Required inputs: --census, --manifest, --corpus-dir, --pins-record (the tracked S402 record or a later tracked
   successor), --draft and --tier (T2|T3, no default; the orchestrator confirms). It prints ONE line to stdout:
   `NBA_TRIAL_JSON: ` + json.dumps(obj, separators=(",",":"), ensure_ascii=True, allow_nan=False). Top-level key order is family,
   tier, corpus, manifest_sha256, primary_game_ids, census, primary_census. family is imported from the runner module and corpus
   is the corpus dir name, never retyped. primary_game_ids = ALL ELIGIBLE ids, sorted, from the LANDED nba_seal_package_checks.identities (imported, not reimplemented).
   census = sports.nba of --census projected onto guards.COUNTS + guards.HISTOGRAMS + ("folds",) and nothing more (no per_game).
   Values are copied as parsed, in the source order, and never recomputed. primary_census is the same object.
   It REFUSES by name (nonzero exit, empty stdout):    pin_missing:<NAME> (any of the eight pins in (e) absent or duplicated in --pins-record);
   eligible_count_mismatch (len(ids) != ELIGIBLE_GAMES or != 1593 or != census eligible_games);
   eligible_sha_mismatch (eligible_digest(ids) != pin); census_ids_differ (sorted per_game keys != ids);
   manifest_sha_mismatch (the runner-rule digest != MANIFEST_SHA256); census_scored / census_sport_block;
   census_key_missing:<key>; census_not_counts (guards.denominators refuses the projected block);
   warmup_folds_mismatch (census warmup_folds != WARMUP_FOLDS or len(folds) != FOLDS);
   draft_already_has_line (the (a):96 regex on the LF-normalized --draft finds one or more lines).
   Before printing, it self-checks the exact string: guards regex count 1, json.loads with guards.unique_object, and fields
   (a):100-110 through guards.denominators. stderr gets one ASCII summary: ids 1593, ids_sha, line_bytes, line_sha256.
2. --check mode (with --draft plus the emit inputs): finds lines with the (a):96 regex and reports ABSENT (0 lines),
   DUPLICATE (2 or more, nonzero exit), MATCH (byte-equal to what emit would print) or DIFFERS (nonzero exit, naming the first
   differing top-level key). It never writes any file. Pasting the line into the draft stays the orchestrator's B2(e) step.
3. The memo records the REAL emission over the files in (d)/(e) with --tier T2: the ids count, ids_sha, line bytes and
   line_sha256, and the --check result on the current draft (expected ABSENT). It does not include the line itself.
   It records NOT VERIFIED: whether the S387 census still equals the runner's recomputed census after S417/S395 land (B_lag adds
   eligibility counting such as no_prior_tick_for_b_lag). If that census is re-run, the line is re-emitted from the new file and
   the pins from the post-S417 S402 transcription (runbook B3) before the seal.
TESTS (per-file only; construct fixtures: a tiny corpus, manifest, census, pins record and draft):
- Primary set used instead of eligible: the line's ids equal ALL eligible fixture ids and include a warm-up game's id.
- Unordered ids: unsorted input is re-sorted, two runs are byte-identical, a shuffled per_game gives the same line.
- A recomputed census is refused: mutate one census count and the line must carry the mutated value, which shows it is copied
  from the source. A census missing state_transition_ticks refuses census_key_missing. A bool or float count refuses census_not_counts.
- A stale MANIFEST_SHA256 pin or an edited manifest refuses manifest_sha_mismatch. A wrong ELIGIBLE sha refuses eligible_sha_mismatch.
- Two lines: a draft with one line refuses emit; two lines give --check DUPLICATE; CRLF is normalized first; --check never
  changes the draft bytes. Each missing pin refuses by name; output is ASCII with one newline; a refusal's stdout is empty.
CONTROLS: PREPARE only. Touches no sealed file, seals nothing, charges nothing, reads the FWER ledger never, writes nothing under
data/, and does not run the runner. Reads corpus game_id/ts fields only through the landed identities helper.
DO NOT: edit the runner, guards, S402 package or draft; recompute or "correct" a census value; fall back to PRIMARY ids; write the
line into any file; claim a market advantage or a currency amount; stage or commit anything under data/ or vault/.

AMENDMENT 1 (2026-09-23 17:4xZ; binding; from round 1 -- BOTH Opus 5.5 tiers ACCEPT WITH CORRECTIONS; tier 2 reproduced the real
emission read-only: ids 1593, ids_sha 04c182de..., line_bytes 86171, line_sha256 a3d96813..., check ABSENT, and fed the line to
the landed guards' authority in-process: ACCEPTED with 1,593 ids, 311 folds, census equal to primary_census; one-byte mutations
refused). CORRECTIONS RULED: (1) --check compares each key as its canonical json.dumps text (never Python equality, where
6 == 6.0 and True == 1), and parses the draft's line with guards.unique_object so a duplicate JSON key is named as such; DIFFERS
names the first key whose canonical text differs, deterministically; (2) the memo's NOT VERIFIED bullet that denies any real
counts is replaced by "the real emission was run by the orchestrator, not the build lane; recorded above" and every hex digest
in the memo sits on ONE line (a wrapped digest cannot be grepped); (3) a manifest that is valid JSON but not an object raises
an uncounted AttributeError (:73) when its canonical digest equals the pin -- refused by name manifest_not_object; (4) a
non-finite value nested inside a fold record escapes as an unnamed ValueError from json.dumps (:134) -- caught and refused
census_not_counts. NOTES recorded: PRIMARY_GAMES_SHA256 and WARMUP_GAMES are checked for shape and arithmetic only (the spec
asks no more); extra inner fold keys are carried (the runner re-normalizes through denominators on both sides); the census may
go STALE once S417 / S395 land if B_lag eligibility changes the counts -- the seal runbook re-emits the line from a re-run
census and the post-S417 S402 pins before the seal, and the memo says so.
