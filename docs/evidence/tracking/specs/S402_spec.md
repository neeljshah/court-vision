GAP S402 | sport nba | worktree harness-h63 (master-based) | log opus_s402_nba_seal_package
# NBA seal package: reconcile the census, pin every denominator and identity, produce the sealable prereg text (ASTRA_ROUND14 row 10, ROUND15 row 4)

SINGLE PROBLEM: docs/evidence/ingame/S382_NBA_PREREG_DRAFT_r1_2026-09-21.md carries TO-FREEZE-FROM-CENSUS placeholders and a
do-not-seal list; the S387 census from the fixed scorer (fix 2a, run on the real corpus 2026-09-22: 1593 games, 465249 ticks,
eligible 221066 in 1593 games, excluded 244183 all post_final, eligible_d 109108, model_prob_missing_for_d 348757,
non_integral_state 0, 0 duplicate or conflicting keys) gives the denominators; S392 fixes the exposure disposition (no untouched
population; arm D descriptive); S395 AMENDMENT 1(c) fixes the line formats the NBA auditor reads (ELIGIBLE_GAMES_SHA256,
ELIGIBLE_GAMES, S86_EXPOSED_GAMES, S58_SCORED_GAMES). Nothing assembles these into a sealable text mechanically, so the seal would be
hand-edited -- the way a digest was once hunted by hand on the MLB seal (landing lesson 26).

BINDING BEFORE-CONDITION: quote from master (a) the S382 draft's section order, every TO-FREEZE placeholder and the do-not-seal list
(its lines 225-251); (b) baseline_four_arm.py --census-only output keys (the census.json 'sports' block) and the corpus manifest shape
data/cache/ingame_grade_joined/nba_checkpoints_r1/manifest.json = {"files": {filename: sha256}} (quote the converter's manifest
convention from the S360 memo); (c) nba_corpus_readiness.py (row S377) CLI and its census keys; (d) the sealed MLB prereg's seal line
format in docs/evidence/ingame/S347_PREREG_SEALED_2026-09-21.md (the last line 'SHA256: <hex>' over the LF-normalized bytes above it;
the sealed text is a NEW file; the draft stays unsealed); (e) the S392 disposition document under docs/evidence/ingame/ (its stated
exposure counts) and the S385 finding; (f) S395 AMENDMENT 1(c).

CHANGE (owned files: NEW scripts/platformkit/ingame/nba_seal_package.py (<= 300 LOC; helper nba_seal_package_checks.py allowed),
NEW tests/platformkit/ingame/test_nba_seal_package.py, memo; the draft is NOT edited; NO seal line is written by this row):
1. nba_seal_package.py: --draft <S382 draft> --census <S387 census.json> --readiness <S377 census json> --manifest <corpus
   manifest.json> --corpus-dir <dir> --pin name=sha (repeatable: scorer, period module, trial runner, auditor commit identities)
   --out <sealable text path> --report <json> [--allow-open]. It (a) reproduces the S377 readiness counts from the readiness JSON and
   the S387 census and reconciles them (files, games, ticks, unique keys; the amended population: eligible vs post_final excluded):
   any disagreement STOPS with the differing keys listed (exit 3, no text written); (b) computes ELIGIBLE_GAMES_SHA256 as the SHA-256
   over the sorted eligible game identities joined by LF (identities read from the corpus files' game_id field; counts only; no
   probability or outcome value is read), ELIGIBLE_GAMES, the canonical per-file manifest SHA-256 (canonical compact JSON of {"files":
   mapping}, sorted keys, serialized ONCE), the byte total, S86_EXPOSED_GAMES and S58_SCORED_GAMES quoted from the S392 document (not
   recomputed), and the fold count and period support from the census; (c) fills every TO-FREEZE placeholder in a COPY of the draft
   with those values, appends the S395 AMENDMENT 1(c) lines in their exact format, marks arm D DESCRIPTIVE per S392, records the
   --pin identities, and writes the sealable text WITHOUT a seal line plus a report listing each placeholder filled and each
   do-not-seal item with its status (CLOSED with the evidence path, or OPEN), so the orchestrator seals only when every item is
   CLOSED; (d) refuses to write the text when any placeholder remains or any do-not-seal item is OPEN unless --allow-open is given
   (then the report says so and the text stays unsealed and is marked DRAFT).
2. Tests: a synthetic draft with placeholders and the do-not-seal list, synthetic census / readiness / manifest and a three-file
   corpus: a reconciliation mismatch stops with exit 3 and no text; the identity hash equals a hand computation; an unfilled
   placeholder refuses; the canonical manifest digest is byte-equal on two runs; LF / CRLF identity of the produced text; the report
   names each do-not-seal item; a corpus file whose market_prob field is malformed still hashes (no value read); --allow-open marks
   DRAFT.
3. Memo docs/evidence/harness/S402_nba_seal_package_2026-09-22.md.

CONTROLS: construct tests only; no real corpus run by the builder; the orchestrator runs it from the repo root after S387 lands and
the census is re-run from master, reviews the report, and commits the seal (the SHA256 line) as a NEW file. ACCEPTANCE: per-file
tests pass; --help works; <= 300 LOC; ASCII; contract Q6 vocabulary; memo ends with NOT VERIFIED.

AMENDMENT 1 (2026-09-22 16:4xZ; binding; the Opus build's two conflicts, accepted). (a) The CLI gains a REQUIRED --disposition <path>
(the S392 document, docs/evidence/ingame/S392_NBA_EXPOSURE_DISPOSITION_2026-09-22.md) from which S86_EXPOSED_GAMES and
S58_SCORED_GAMES are quoted by patterns that must match exactly once (its identity bullets: 'historically 797 games / 232,951 ticks'
and the S58 '1,593 checkpoints' line); (b) the CLI gains a repeatable --closed <index>=<evidence-path> for the do-not-seal items;
CLOSED requires the evidence path to exist on disk (contract A7), a non-existent path is a refusal, an item without an entry is OPEN;
(c) the draft's placeholder 5 (its line 185, 'Launch values not yet available ... record at authorized launch') is not
census-derivable: it stays OPEN, and the text is written only with --pin launch_values=<text> supplied by the orchestrator at seal
time or with --allow-open (DRAFT-marked); this is the spec's own --allow-open path, never a silent fill. (d) The real inputs for the
orchestrator's run: --census data/cache/ingame_grade_joined/_census/nba_checkpoints_r1_S387_master/census.json (from master,
2026-09-22 16:1xZ, byte-identical to the h55 candidate's census: sha256 2a6bf94fd1b3df9b...), --readiness
data/cache/ingame_grade_joined/_census/nba_readiness_S377_master.json (re-run from master 2026-09-22), --manifest
data/cache/ingame_grade_joined/nba_checkpoints_r1/manifest.json, --corpus-dir data/cache/ingame_grade_joined/nba_checkpoints_r1.

AMENDMENT 2 (2026-09-22 17:0xZ; binding; after the Opus verifier round 1 ACCEPT WITH CORRECTIONS and S395 AMENDMENT 2). (a) The
seal package also pins the POST-WARM-UP PRIMARY population: PRIMARY_GAMES_SHA256 (SHA-256 over the sorted identities of the eligible
games whose fold date is NOT one of the census warm-up folds, joined by LF) and PRIMARY_GAMES; the fold assignment rule is quoted from
baseline_four_arm.py (a game's fold = its game date; the census folds list carries warmup true/false per date), and the game date is
read from the corpus rows' date field beside game_id (no probability or outcome value is read); the report states the warm-up game
count (ELIGIBLE_GAMES minus PRIMARY_GAMES) and the draft's stated 1,570 must be reproduced or the tool STOPs with both numbers.
(b) CORRECTION 1: a --pin value must be ASCII AND printable with no newline (nba_seal_package.py:88); a value carrying a line break
is refused (it could inject a second pinned line). (c) CORRECTION 2: --closed evidence must be an existing FILE (Path.is_file), never a
directory (:109). (d) The census echo line is named CENSUS.eligible_games (never ELIGIBLE_GAMES) so an unanchored consumer pattern
cannot match twice; every emitted pinned line is unique by name. (e) NOTE 4 accepted: a missing input file is a counted Stop with the
report written (OSError caught into Stop), and a Stop after a successful reconciliation keeps the reconciliation table in the report.

AMENDMENT 3 (2026-09-22 21:2xZ; binding for the next S402 follow-up; from the Opus closure assembly). MEASURED on the landed
package (5bab58a3e): the only check a --closed <index>=<path> evidence argument receives is Path(path).is_file() -- the file's
contents are never inspected, so any existing file closes any item. RULING (additive, a follow-up row before the seal): a
closure evidence file must be a TRACKED path (git ls-files) and must contain the item's index token 'do-not-seal <index>' or
the item's first eight words verbatim; a path failing either refuses closure_evidence_unrelated (counted); the report records
per item the evidence path, its blob sha and which rule matched. Until that lands, the orchestrator closes items only with the
artifacts named in .planning/direction/nba_seal_closures_2026-09-22.md (copied under docs/direction/), each of which names its
item, and records the mapping in the seal memo. Also recorded: the real reconciliation run on the amended draft (2026-09-22,
--allow-open) is transcribed as docs/evidence/harness/S402_reconciliation_real_2026-09-22.md -- differing_keys [], every key
equal, do_not_seal 11 open, missing pin auditor.
