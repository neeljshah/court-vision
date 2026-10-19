# S469 -- scoreboard policy seal no longer embeds the live FEATURES dict (PARKED candidate, rebased)

Spec: docs/evidence/tracking/specs/S469_spec.md REVISION 2 + AMENDMENT 1 (a)-(j) + AMENDMENT 2 (2026-10-02,
chain slipped one day; AMENDMENT 2 governs dates, AMENDMENT 1 governs everything else) + AMENDMENT 3
(fix round 1; (b)-(f) implemented in the FIX ROUND 1 section below, (g) is row S524) + AMENDMENT 4 (round two
outcome, B1 adjudication, corrections 1b in the Verification history section, landing gates).
Worktree: C:/Users/neelj/nba-harness-h163, branch harness-h163-rebased (commit A' = the seal alone, commit B' =
everything else). Pre-rebase backup of the parked build: branch harness-h163 at 1f9e6379fd0884d447ff9bcca3f565863c62d04c.
Verification base master: 6f7243c2484226566cf7a74891b5df324f61f3d1 (S492 commit B landed as 0d2d5a196 + 543b134df, S502 landed, then the
AMENDMENT 2 spec commit). Candidate HEAD vs base: NOT EQUAL (A' and B' sit on top, nothing else).
Scope: construct tests only, local, fresh child processes; no archive read, no network, no real night.
This is calibration-infrastructure work (seal identity); it makes no accuracy or market claim.

## Verification history (corrections 1b, spec AMENDMENT 4(c); memo only, no code, test or pin change)

- 2026-09-30: the parked build (memo S469_scoreboard_seal_features_2026-09-30.md, replaced by this file) was self-tested only.
- Round one, both tiers (contract and adversarial): ACCEPT WITH CORRECTIONS, no blocker. Verification base:
  candidate 1bd58a76e63fedcf1dbded73d1e0fa9eb5c21961 (B' on master 6f7243c2484226566cf7a74891b5df324f61f3d1 plus commit A).
- Round two, both tiers, on 0515e8fdf511980984681918055a2f4ae99d2474 (commit B ca6c1a586aef906eeae2db5fe2e80818166659ee
  plus fix round one), base master 23a2eac2d1ee14a43677c543eb9a63afca208881: contract tier ACCEPT WITH CORRECTIONS
  (memo only, this section); adversarial tier ACCEPT WITH CORRECTIONS (every guard, hatch, byte-loop and pin mutant
  killed; no false refusal on the real tree) with one blocker-class finding, B1, left to the dispatcher.
- B1: the direct scorer entry point (`python -m scripts.platformkit.execution.ingame_scoreboard`; main calls run and
  `_seal` only) has no amendment selection, as on master, and after commit B it no longer refuses a changed features
  file (an on-disk edit of baseline_four_arm_features.py yields a receipt citing PREREG_2026-09-24.json; measured in a
  scratch clone; master's refusal was read from code, not run). ADJUDICATION (dispatcher, AMENDMENT 4(b)): not a
  landing blocker; the executed night step runs the `_night` module, paper_night.py uses the direct module's step only
  to derive the history list, no scheduled-task prompt names it, and the smallest fix edits a seal-hashed file. Row S525.
- Hatch date reading: the literal's date is 2026-09-24, so PREREG_2026-10-01 satisfies the hatch today.
- An equal-content list in place of a tuple now refuses legacy_features_mismatch: stricter than master, a refusal only.
- On an amendment night an in-process FEATURES mutation is accepted while an on-disk edit of a hashed features file
  refuses amendment_mismatch: the intended design (the amendment hashes files, not live dicts).
- The amendment nights 2026-09-29 to 2026-10-02 cannot be re-scored on commit-B code (refused amendment_mismatch).
- Night 2026-10-01 has NO scoreboard receipt (every step was refused or killed on 2026-10-02). After commit B, master
  refuses it amendment_mismatch, so re-scoring it needs a checkout of the pre-B commit
  c396eeec14b91e1293a2266e077984569ad6f5f0.

## Rebase (AMENDMENT 2(e))

- `git diff 14a83fcb3 master -- <every S469-touched path>` is EMPTY: the old S492-B candidate commits
  landed byte-identically on those paths. Since a8aa28b8a, master changed nine of the S469-touched files,
  all by S492 commit B: ingame_scoreboard_night.py and the test files amendment_model_optional,
  night, night_e2e, night_replace, night_table, paper_night_e_step_e2e, s492_e2e, s492_landing.
- No identity file changed on master since the parked build (baseline_four_arm*.py, walkforward.py,
  ingame_scoreboard_rules.py, ingame_scoreboard.py all equal), so the backup diff applied cleanly (no
  conflicts; .gitattributes untouched by S469).

## Before-condition

Re-quoted on the new base (AMENDMENT 3(f)): master 23a2eac2d1ee14a43677c543eb9a63afca208881, whose
ingame_scoreboard.py (LF sha256 12492ba687ff76ad5638613427efd247973544025f2bd1cc9fe2771485a92cf6) still
imports FEATURES. Script scratchpad/s469_fix1/before_requote.py execs that file from git (no file edited);
injected value, in process: `FEATURES['mlb'] = FEATURES['mlb'] + ('x',)`.

```
before sha 81f345289874ebca07e3fe0dcf89337c19967397670399892fb18b015c7f1970
before seal 6976e78aa68124fc8ca8663f215fc59a5bf6aab42c8ce54e477bbe3bf717c08b
after sha c12ac543df4e5e51112be96e4b7f151e8ca9bfbf15b7a641c18b3bbf698dbb4e
after seal REFUSED prereg_mismatch
```

Historical record, parked build 2026-09-30 (`scratchpad/s469_before.py`, base before a8aa28b8a; injected value not
recorded, so superseded by the re-quote above): seven keys; before sha 81f34528...1970 (same); after sha
bd86432eb494ca2d5260429152504b9175e2968eb6ecbefc83ac8e94f948cfed; after seal and n_games seal REFUSED prereg_mismatch.

AMENDMENT 1(d)(i) before: MLB_LIVE_FIELDS plus one name moves the POLICY digest and `_seal` refuses
prereg_mismatch; the moved digest depends on the appended name, so the 5352b56e prefix quoted in the
amendment was not reproduced (the refusal itself reproduces).

## CHANGE (as built)

1. scripts/platformkit/execution/ingame_scoreboard.py (two hundred sixty-seven -> two hundred seventy-eight
   lines): the FEATURES import is removed; `SEALED_FIT_FEATURES` sits directly above `POLICY =` with the
   spec's comment; POLICY.fit.features iterates `SEALED_FIT_FEATURES.items()`. Every other byte unchanged.
2. Generating command (by script, run once on the verification tree): `PYTHONPATH=. python
   scratchpad/s469_gen.py` writes one line per sport in sorted order as `repr(tuple(FEATURES[s]))` (the
   mlb `base_N` generator expanded), deletes the import, swaps the comprehension source; each anchor
   asserted to occur exactly once. Per-sport equality `tuple(FEATURES[s]) == SEALED_FIT_FEATURES[s]`:
   True for all seven keys (mlb, mlb_live, nba, nba_enriched, nba_pbp, nfl, soccer); key sets equal.
   POLICY digest before and after: 81f345289874ebca07e3fe0dcf89337c19967397670399892fb18b015c7f1970, EQUAL.
3. scripts/platformkit/execution/ingame_scoreboard_night.py: ONE appended SEALS tuple
   `('amendment', 'docs/evidence/forward/scoreboard/PREREG_2026-10-03.json', None)` (commit B').
4. NEW tests/platformkit/execution/test_ingame_scoreboard_policy_snapshot.py (twenty-one cases).
5. NEW tests/platformkit/execution/s469_seal_helper.py: the PREREG_2026-10-03 seal bytes as the landed
   generator's own `_payload` output over the live identities, pinned by full sha256 (the committed
   A' file's sha, below), plus the S492-era selector text (candidate selector minus the S469 line).

## Commit A' (AMENDMENT 2(d))

Generated in the worktree on master plus ONLY the candidate ingame_scoreboard.py (the SEALS line was
absent during generation, `git diff master --stat` showed that one file), with:
`python -m scripts.platformkit.execution.ingame_scoreboard_amendment --write
docs/evidence/forward/scoreboard/PREREG_2026-10-03.json --effective-from 2026-10-03
--model-optional-sport mlb --model-optional-sport nfl --model-optional-sport soccer` (exit 0).

- file sha256 6abb1a851628a1fbf259ed5b79e7aecbdbeccf68f7542afdc665263db4ed13e4, LF only;
  payload sha256 d84f14e802836a8d01c6ac208e8a5fc4a8e58c820889e7c27b2e684fd679871d; amendment 'S492',
  implementation_version 2; supersedes.policy_sha256 81f34528...1970; sports mlb, nfl, soccer.
- Script-asserted diff vs PREREG_2026-10-01: exactly ['effective_from',
  'implementation.scripts/platformkit/execution/ingame_scoreboard.py', 'sha256'].
- (i) Every implementation hash equals the CRLF-normalised sha256 of the rebased candidate file:
  walkforward 6a59fbc9..., ingame_scoreboard.py 84c8b50aaada973623d7e2399090c0d15d9c8ce94ea65688f08743736e1763b8
  (the only S469-moved identity), ingame_scoreboard_rules 85c1a6be..., baseline_four_arm dfa121c7...,
  baseline_four_arm_eligibility d6a5fb4f..., baseline_four_arm_features 9704f9af...,
  baseline_four_arm_features_nfl 117561db... (full values: the committed A' file; all EQUAL).
- (ii) verify_amendment on a temp copy (stubbed commit time 2026-10-02T15:30:00Z): night 2026-10-03
  accepted (mlb, nfl, soccer); night 2026-10-02 refused amendment_not_effective; a same-day seal
  (effective 2026-10-02, committed 2026-10-02) refused amendment_not_prospective
  (ingame_scoreboard_amendment.py:147); the generator with effective 2026-10-02 on a 2026-10-02 clock
  refused amendment_not_prospective (:94).
- (iii) Inert on master code: ingame_scoreboard_night.select (:107-132) validates only the entries of the
  `seals` argument (`_table`, :61-104, iterates `seals`; no directory scan), and master's SEALS (:30-35)
  ends at PREREG_2026-10-01. In-process check on master's modules with a temp root holding master's
  identity files, master's four seals and PREREG_2026-10-03.json in the same scoreboard dir: select
  2026-10-02 and 2026-10-03 both return PREREG_2026-10-01 (mlb, nfl, soccer); the 10-03 file was never
  opened (git_head / git_commit_time spies).

## Per-construct results (test_ingame_scoreboard_policy_snapshot.py)

Twenty-one passed on the candidate, unchanged from the parked build: no-mutation digest and bytes
match the committed PREREG_2026-09-24; (f) placement; six fresh-child FEATURES mutations plus (d)(i)
MLB_LIVE_FIELDS keep the digest and `_seal` accepts (PREREG_2026-09-30 refuses prereg_mismatch through
the history producer's own expression); tuple/list boundary; five POLICY changes refuse exactly
ValueError('prereg_mismatch'); (c) literal text edit refuses; (d)(ii) consumed-set tripwire with an
empty DECLARED_DIVERGENCE; PREREG_E loads and refuses on its own policy; (d)(iii) team_state disclosure;
the night 2026-09-28 fresh-process run under FEATURES injection.
Cited, not duplicated (AMENDMENT 1(e)): malformed / CRLF prereg -- test_ingame_scoreboard.py and
test_ingame_scoreboard_1b.py; one byte on an identity file -> amendment_mismatch --
test_ingame_scoreboard_amendment.py::test_identity_after_landing_and_later_commit.

Red check (AMENDMENT 3(f), two setups, both measured on the twenty-one-case file of B'):
setup one, master's ingame_scoreboard.py restored temporarily in the candidate worktree, so the file
runs with the candidate night_e2e module (whose fixture needs the S469 SEALS row): ten failed, ten
passed, one error (the night-injection case errors in that fixture). Setup two, master plus commit A
with master's own test modules (master night_e2e): eleven failed, ten passed (the night case fails
instead of erroring). Candidate: twenty-one passed (twenty-two after fix round 1).

## Pin and date conversions (AMENDMENT 1(b), AMENDMENT 2(f))

"A" = forced by the ingame_scoreboard.py change, "B" = forced by the SEALS line, "D" = AMENDMENT 2 date move.

| file:line | old | new | cause |
|---|---|---|---|
| test_ingame_scoreboard_model_optional.py:100-102 | base POLICY text compared as-is | `FEATURES.items()` -> `SEALED_FIT_FEATURES.items()` substituted first; digest pin kept | A |
| test_s485_baseline_contract.py:26-31, :129-130 | ingame_scoreboard.py byte-equal to BASE; selector pinned by S492_REPIN | S469_REPIN: ingame_scoreboard.py 84c8b50a..., selector c676da4f... at B', regenerated to ea503eac... in fix round 1 (LF sha256 of landed text, same form as S492_REPIN; new in this rebase, the file gained this pin with S492 B) | A+B |
| test_s492_landing.py:21, :38-57 | 10-01/10-02 select PREREG_2026-10-01 on real ROOT | S492 table (SEALS[:4]) on real ROOT: 09-30, 10-01, 10-02 refuse amendment_mismatch; full table on a tmp root holding the helper seal: 10-03 selects PREREG_2026-10-03 (sha 6abb1a85...), 10-02 refuses | A+B+D |
| test_s492_landing.py:61-78, :124 | construct_seal(root=ROOT); stage_b selector = ROOT bytes | tmp root with ingame_scoreboard.py from PRE_S469 = a8aa28b8a (full sha), checked against the fixture seal's identity; `s492_selector(ROOT bytes)` | A+B |
| test_s492_e2e.py:22, :74, :83-91 | OWNED copied from ROOT; local `selector` | selector via `s492_selector`; helper SELECTOR constant | B |
| test_ingame_scoreboard_night.py:13, :17, :32, :79, :83 | SEALS[3:] one row | two rows; helper seal in the tmp root; S469 in the protected-output list | B |
| test_ingame_scoreboard_night_e2e.py:19, :61, :77-78 | SEALS[3:] one row | two rows; construct commit A in the tmp index (helper seal, commit time 2026-10-02T00:30:00Z) | B+D |
| test_ingame_scoreboard_night_replace.py:13, :23, :30, :159, :164 | git-ref pins for every SEALS row | S469 row -> helper bytes / construct time; ROOT byte check over SEALS[:4] at B', full SEALS since fix round 1 (AMENDMENT 3(d)); two rows | B |
| test_ingame_scoreboard_night_table.py:13, :201, :249-252 | SEALS[3:] one row | two rows; historical real-table check on SEALS[:4] | B |
| test_ingame_scoreboard_amendment_model_optional.py:19-27 | S492 construct on the live table | autouse fixture asserts SEALS[4:] == (S469 row,), runs on SEALS[:4] | B |
| test_paper_night_e_step_e2e.py:251-256, :261 | selector pinned a1df006e... | S469_PINNED c676da4f3cded36a6fd6feae3dd12fb90425a8d15a6d997e244265a922210b08 at B'; fix round 1: ea503eacf97fa33441660970312f7228bbf897b360c92fbef74c3cad363fb09b | B+D |
| s469_seal_helper.py | PREREG_2026-10-02, pin 50efa072..., commit time 2026-10-01T00:30:00Z | PREREG_2026-10-03, pin 6abb1a85..., commit time 2026-10-02T00:30:00Z, `_payload('2026-10-03', ...)` | D |

Date occurrences deliberately KEPT (they denote nights governed by PREREG_2026-10-01, not the S469 seal):
test_s492_landing.py:41 loop day 2026-10-02 on SEALS[:4] (an S492 night refusing on candidate code);
test_ingame_scoreboard_amendment_model_optional.py:21-22 docstring (the S492 construct's own 2026-10-02
seal); test_s492_e2e.py:80, :131-138, :282 (S492's own construct night); test_paper_night_e_step_e2e.py:74
(pre-existing day loop). No conversion compares against a moving ref.

## Per-file results (rebased candidate, A' committed, B' in the working tree, one file per call)

Run set: the AMENDMENT 1(b) grep over tests/ plus importers of the three scoreboard modules (fifty-one
test files after dropping three helper modules) plus five further S492-touched test files.

- all passed: tests/platform/test_ingame_scoreboard.py five; test_ingame_scoreboard.py forty-three; _1b
  sixteen; _1e four; _amendment sixty-nine; _amendment_model_optional twenty-six; _model_optional sixteen;
  _night thirty-three; _night_e2e eight; _night_replace thirteen; _night_table one hundred four;
  _policy_snapshot twenty-one; _rules_nfl eighty-two; test_microstructure_licence twenty-eight;
  test_paper_night_deferral_r1 eighteen (one skipped); _e_step_e2e forty-one; _inputs_e2e eleven;
  _scoreboard_step fourteen; _scoreboard_step_1c four; _steps fifty-six; test_paper_sizing_inputs
  twenty-two; _policy fifty-one; test_registry_scorer_e_1e thirteen; _s471 five; _s480_real eleven;
  test_s492_e2e nine; test_s492_landing four; test_scoreboard_cumulative forty-three; _e2e fifteen;
  _landed thirty-three; _order fifty-four; _parser six; test_scoreboard_history thirty-six; _e2e
  fourteen; _store eighty; test_seal_provenance sixteen; _1b nineteen; _1c four; _1d eleven;
  test_soccer_scoring_s490 twelve; test_soccer_s490_evidence nineteen; ingame/test_baseline_four_arm_model_optional
  seventy-one; test_m2_readout seven; _e2e four (one skipped); test_nba_season_type forty-five;
  test_registry_readers twelve; test_s439_integrity_audit thirteen; _e2e two (one skipped); _guards
  thirteen; test_team_labels_night one; test_baseline_four_arm_features_nfl forty-five;
  test_microstructure_features twenty; test_nfl_state_ingest twenty-four; ops/test_s485_baseline_contract
  four (after its conversion; one failed before it); test_s492_memo_facts twenty-eight.
- PRE-EXISTING error: tests/platform/test_soccer_run_proof.py one error (ModuleNotFoundError
  src.prediction.bet_grades; identical on the pre-S469 tree per the parked build).
- test_team_labels_night.py is now green in the worktree because A' is committed there (it was the
  "red until commit A" file of the parked build). test_scoreboard_cumulative_e2e.py now passes
  (fifteen); the parked build saw it fail on the old tree for an unrelated reason.

## LANDING PLAN (AMENDMENT 2(c))

- 2026-10-02: commit A' landed (PREREG_2026-10-03.json alone, master bab224398d6928e93817e46a93a8ced3e5c2e484).
- Commit B' (UTC 2026-10-03, after scoreboard/2026-10-02.json exists, before the 2026-10-03 night is scored,
  about 06:05Z on 10-04): every other file of this candidate. S625 then takes X = 2026-10-04.
- Disclosed consequence: after B', re-scoring nights dated 2026-09-29..2026-10-02 on new code refuses
  amendment_mismatch (their seals pin the old ingame_scoreboard.py bytes); receipts are immutable.
- S503: no cumulative window seal before S625 commit B (AMENDMENT 1(g)).

## Scope statement (AMENDMENT 1(h))

S469 guarantees no FEATURES change in any module moves the policy seal; it does not stop
identity-file edits from refusing the selected amendment (the two-commit discipline covers that); it
does not cover arm-E seals (PREREG_E c_fields derives from BLOCKS['team_state']; logistic is a
declared external dependency of arm E) -> register rows S505 and S506; S546/S547 touch no scoreboard
identity file.

MANDATORY DISCLOSURES: POLICY.fit.features is the 2026-09-24 documentation snapshot and can diverge
from the consumed FEATURES after a later landing -- the consumed set for a night is the one named by
that night's amendment identity; the amendment still refuses on any feature-file edit, so a feature
landing still needs its own two-commit amendment (this row removes the policy-seal half, not that).
A diverging landing lists its key in the tripwire's DECLARED_DIVERGENCE with its amendment path; since
fix round 1 that path must be a SEALS amendment effective after 2026-09-24 whose
baseline_four_arm_features.py hash equals the live file (AMENDMENT 3(c)).
Plainly: POLICY.fit.features is documentation. The scored model of an amendment night is whatever that
night's selected amendment hashes (its implementation files); a legacy-policy night (2026-09-24 to
2026-09-28 and earlier history) is held to SEALED_FIT_FEATURES by the night-level guard of AMENDMENT 3(b).
The receipts-directory glob of scoreboard_cumulative.py (`receipts_dir.glob('*.json')`, :91) counts
PREREG_2026-10-03.json under receipt_filename like every other PREREG file in that directory. Harmless:
no cumulative window is sealed before S625 commit B.

## FIX ROUND 1 (spec AMENDMENT 3; both round-1 tiers ACCEPT WITH CORRECTIONS)

B' rebased onto master 23a2eac2d (docs-only commit on top of commit A bab224398; `git diff bab224398
master --stat`: three docs files, no identity file). Fix commit sits on top of B'; B' itself unamended.
- 2026-10-02 (b) legacy guard, ingame_scoreboard_night.py main() right after select(): a night whose
  selected seal is the legacy policy (no amendment) refuses ValueError('legacy_features_mismatch') before
  run() and before any temp file unless, for every requested sport s in CORPUS,
  FEATURES[sport_for(CORPUS[s])] equals SEALED_FIT_FEATURES of that key. Amendment nights skip it.
- 2026-10-02 constructs, NEW test_ingame_scoreboard_legacy_guard.py (six cases): (i) night 2026-09-28,
  real driver in a fresh process with 'outs' dropped from FEATURES['mlb'] exits one with that reason and
  the tmp tree is byte-unchanged; in process, mlb and soccer reversed refuse with run() never called;
  (ii) unmutated, the output equals (retry counts aside, as in night_e2e) both the pre-fix B' selector
  and the S492-era selector run on the same scorer; (iii) night 2026-09-30 with the in-memory mutation
  reaches run() (guard silent, model-optional mlb and soccer); the same field dropped from the hashed
  features file refuses amendment_mismatch; (iv) AMENDMENT 3(e): a tmp root with the worktree seals and
  the seven identity files selects 2026-10-03 through main(); one changed byte (first digest hex char)
  in the PREREG_2026-10-03.json copy refuses seal_index_invalid (uncommitted), and amendment_mismatch
  once that byte is the committed one; no output written.
- 2026-10-02 (c) tripwire: a DECLARED_DIVERGENCE path must be an amendment row of night.SEALS with
  effective_from after 2026-09-24 and a baseline_four_arm_features.py hash equal to the live LF hash;
  new case shows pytest.ini, the policy seal and PREREG_2026-09-30 (older features hash) fail the hatch,
  a removed mlb field stays red with {} / {'mlb': 'pytest.ini'} / {'nba': S469}, and {'mlb': S469} opens it.
- 2026-10-02 (d) night_replace byte loop restored to the full SEALS: the committed commit-A file is
  compared with the helper bytes.
- 2026-10-02 helper: s492_selector now also strips the guard's import lines and block and asserts the
  result hashes to the landed S492 selector a1df006e... (equal to master's night file, checked).
- 2026-10-02 pins regenerated by script from the LF-normalised night file (each old value asserted to
  occur once): S469_REPIN and S469_PINNED c676da4f3cded36a6fd6feae3dd12fb90425a8d15a6d997e244265a922210b08
  -> ea503eacf97fa33441660970312f7228bbf897b360c92fbef74c3cad363fb09b.
- Seal intact: all seven implementation hashes of PREREG_2026-10-03.json equal the worktree files
  (seven of seven); the worktree file is byte-identical to bab224398's (sha 6abb1a85...13e4).

Mutation spot-check (scratch clone, never the worktree):

| mutant | result |
|---|---|
| guard block deleted | KILLED: legacy_guard four failed, two passed (all three (i) cases and (ii)) |
| hatch restored to is_file() only | KILLED: policy_snapshot one failed, twenty-one passed |
| full loop, one seal byte altered | KILLED: night_replace one failed, twelve passed |
| loop narrowed to SEALS[:4], one seal byte altered | SURVIVED (thirteen passed): the B' gap that (d) closes |

Per-file results after the fix, one file per call: legacy_guard six; policy_snapshot twenty-two;
night_replace thirteen; e_step_e2e forty-one; s485_baseline_contract four; night thirty-three;
night_table one hundred four; night_e2e eight; amendment sixty-nine; amendment_model_optional
twenty-six; model_optional sixteen; s492_landing four; s492_e2e nine; deferral_r1 eighteen (one
skipped); scoreboard_step fourteen; scoreboard_history thirty-six; cumulative_parser six;
team_labels_night one; inputs_e2e eleven; test_ingame_scoreboard forty-three; history_store eighty;
scoreboard_step_1c four. All passed. test_scoreboard_cumulative_e2e.py not run (excluded).

## A9 identities (LF-normalised sha256, recomputed as the last edit)

- docs/evidence/forward/scoreboard/PREREG_2026-10-03.json: 6abb1a851628a1fbf259ed5b79e7aecbdbeccf68f7542afdc665263db4ed13e4
- scripts/platformkit/execution/ingame_scoreboard.py: 84c8b50aaada973623d7e2399090c0d15d9c8ce94ea65688f08743736e1763b8
- scripts/platformkit/execution/ingame_scoreboard_night.py: ea503eacf97fa33441660970312f7228bbf897b360c92fbef74c3cad363fb09b
- tests/platformkit/execution/s469_seal_helper.py: bab27dc85756456507c663a9baa578a92d4fba93773702639f7a0f39b5652a03
- tests/platformkit/execution/test_ingame_scoreboard_amendment_model_optional.py: dbe1ed16e3a448ca40da50ad69cc45ac1f94f52295299bacc4157659e727bc3f
- tests/platformkit/execution/test_ingame_scoreboard_legacy_guard.py: ac6dc4a48428253dbe65c7946f0204591da7f899f4d3126c431da6cf1058b1fc
- tests/platformkit/execution/test_ingame_scoreboard_model_optional.py: 11991aeca6783b2954b6527cdc48a2071bd4a3dc442d1c3ae0153dd8b4aec58f
- tests/platformkit/execution/test_ingame_scoreboard_night.py: 3eab7bc8c311c65ebfe0ac72a990e629e0345bc1d00300446f709bfe5e90d9aa
- tests/platformkit/execution/test_ingame_scoreboard_night_e2e.py: 83c8bcce011150b59424d914762e3d921bb79a0158e0e7b154333559fc3fd774
- tests/platformkit/execution/test_ingame_scoreboard_night_replace.py: 000b2ee25b92f11e7bdfecbeaf6b71aa4e28b28a51c58b46f3b1c1a243c099f3
- tests/platformkit/execution/test_ingame_scoreboard_night_table.py: 8ed7da51018395df5eebf67aa7fd555c8d6dafecba10d3d2e3125af4c4517815
- tests/platformkit/execution/test_ingame_scoreboard_policy_snapshot.py: 5b7f599e93369540c842340154d9a064e745b7ae8ea6cc495d4dd3d48711fddc
- tests/platformkit/execution/test_paper_night_e_step_e2e.py: c1590d67f57aa43aaaeb66a39bddf9f505ee3d655a151175baf0342c95f7c9dd
- tests/platformkit/execution/test_s492_e2e.py: 3a1757ebbf0a711db8a359bc67fe9c1b7f8c88998e800ba0a477955321f1269c
- tests/platformkit/execution/test_s492_landing.py: b9be4db2dc8fcc0f3f62e31ea2ab374f83c68bdb833f533ce40e7ffdbe963796
- tests/platformkit/ops/test_s485_baseline_contract.py: 31ee4f082fd97baed462a666c3f7e2d55d4da6ee603c3dfea106e39570596507
- this memo: its own sha256 is reported in the hand-off (a file cannot contain its own hash).

## NOT VERIFIED

- Rounds one and two are quoted from the dispatcher's record (spec AMENDMENT 3 and 4); the verdict files are not here.
- Commit A is on master (bab224398, byte-identical here); commit B landing and its master-side runs.
- The red-check counts for the two setups above are the round-1 measurements quoted by AMENDMENT 3(f);
  they were not re-measured on the twenty-two-case file of the fix round.
- The legacy guard against a real archived legacy night (constructs only; no real night re-scored).
- The real night 2026-10-03 scored under PREREG_2026-10-03, and the master-side runs after A' and B'.
- A git-level rehearsal of the A' -> B' landing on master (worktree commits and tmp-root constructs only).
- The 5352b56e digest quoted in AMENDMENT 1(d)(i) (name-dependent; not reproduced).
- The pre-existing test_soccer_run_proof.py error (not investigated).
