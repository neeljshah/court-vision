# S425 -- NBA_TRIAL_JSON line producer (PREPARE)

Owned files: `scripts/platformkit/ingame/nba_trial_line.py` (new),
`tests/platformkit/ingame/test_nba_trial_line.py` (new), this memo. The runner, its guards,
the S402 package and the S382 draft were not edited. Nothing was sealed, charged or written under data/.

## Before-condition (re-read in worktree harness-h82, master-based, 2026-09-23)

`scripts/platformkit/ingame/nba_four_arm_trial_guards.py`, quoted verbatim:

- :96 `declarations = re.findall(rb"^NBA_TRIAL_JSON: (.+)$", normalized, re.MULTILINE)`
- :97-98 `if len(declarations) != 1:` / `raise ValueError("refused=1 missing or duplicate NBA_TRIAL_JSON declaration")`
- :99 `config = json.loads(declarations[0], object_pairs_hook=unique_object)`
- :100-101 `if (config["family"] != "ingame_four_arm_nba_r1" or config["tier"] not in ("T2", "T3")` /
  `or config["corpus"] != "nba_checkpoints_r1" or corpus.name != config["corpus"]):`
- :103 `if not re.fullmatch("[0-9a-f]{64}", config["manifest_sha256"]):`
- :105-107 `ids = config["primary_game_ids"]` / `if (not isinstance(ids, list) or not ids or any(type(g) is not str or not g for g in ids)` / `or len(set(ids)) != len(ids)):`
- :109-110 `config["census"] = denominators(config["census"])` / `config["primary_census"] = denominators(config["primary_census"])`
- :16-21 COUNTS holds 14 keys (files .. warmup_folds, including duplicate_identical, conflicting_duplicate_key,
  state_transition_ticks, games_without_parseable_tick); HISTOGRAMS holds excluded_by_reason and the two date histograms.
- :118-121 `parsed = json.loads(raw, object_pairs_hook=unique_object)` /
  `canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"), allow_nan=False)` /
  `digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()` / `if digest != expected:`

`scripts/platformkit/ingame/nba_four_arm_trial.py`, quoted verbatim:

- :21 `SPEC_ID, FAMILY = "S394", "ingame_four_arm_nba_r1"` (the producer imports FAMILY from here)
- :138 `ids = set(config["primary_game_ids"])`
- :139 `primary_rows = [r for r in rows if r["game_id"] in ids]`
- :140-141 `if {r["game_id"] for r in primary_rows} != ids:` / `raise ValueError("refused=1 missing primary games")`
- :142-143 `_, primary_counts = select_rows(primary_rows, corpus.name)` / `guards.check_census(census, config, primary_counts)`
- :153 `dates = sorted(config["census"]["games_per_first_tick_utc_date"])`
- :180-181 `primary_predictions = (predictions if len(primary_rows) == len(rows) else` /
  `_checked_rows(scorer.predict_rows(primary_rows, corpus.name)))`

The line lines up with (a) and (b) as the spec says: guards :131-132 compare the recomputed census to
config["census"] and primary_counts to config["primary_census"]. With all 1,593 eligible ids,
primary_rows == rows, so both blocks are the same source block.

Shapes confirmed read-only on the main-tree files (no values copied into tests):
census.json top-level keys scored / fields_read / manifest_fields_read / sports / provenance; scored is false;
sports holds only nba; sports.nba carries all 14 COUNTS, the 3 HISTOGRAMS, folds (records with date, train_games,
train_ticks, warmup) and per_game keyed by game_id. manifest.json has only "files" ({name.jsonl: sha256}).

## What was built

Emit mode prints one line, `NBA_TRIAL_JSON: ` + compact ASCII JSON, keys in the order family, tier, corpus,
manifest_sha256, primary_game_ids, census, primary_census. ids come from the landed
`nba_seal_package_checks.identities` (sorted; every eligible game, warm-up games included; the PRIMARY set is never
used). census is sports.nba projected onto guards.COUNTS + HISTOGRAMS + folds in source order, copied as parsed;
primary_census is the same object. The manifest digest is computed by the landed `guards.manifest_pin`.
stdout is written as bytes with a single LF. stderr carries `ids= ids_sha= line_bytes= line_sha256=`
(the byte count and digest are over the line without its newline).

Named refusals (exit 2, empty stdout): pin_missing:<NAME> (absent or duplicated), pin_malformed:<NAME>,
pin_inconsistent (ELIGIBLE - WARMUP != PRIMARY), eligible_count_mismatch, eligible_sha_mismatch, census_ids_differ,
manifest_sha_mismatch, manifest_unreadable, census_unreadable, census_scored, census_sport_block,
census_key_missing:<key>, census_not_counts, warmup_folds_mismatch, draft_already_has_line, corpus_name,
corpus_identities:<reason>, corpus_identity_refusals (any identities refusal count), self_check_line,
self_check_fields. Before printing, the exact string is replayed through the :96 regex (count 1), json.loads with
guards.unique_object, the :100-108 field rules and guards.denominators on both blocks.

--check (same inputs) reads the draft only: ABSENT (exit 0), MATCH (exit 0), DUPLICATE (exit 1),
DIFFERS first_differing_key=<key> (exit 1). CRLF is folded to LF first, as guards :95 does. It writes nothing.

## Construct results

`python -m pytest tests/platformkit/ingame/test_nba_trial_line.py -q -p no:cacheprovider` -> 30 passed
(interpreter C:/Users/neelj/AppData/Local/Programs/Python/Python310/python.exe, Python 3.10.0). The fixtures are a
3-game construct corpus (one warm-up game), its manifest, a census with the S387 shape, a pins record and a draft.
Covered: all eligible ids including the warm-up game; sorted and byte-identical across runs and a shuffled per_game;
a mutated census count carried verbatim (copied, not recomputed); census_key_missing for state_transition_ticks,
folds and excluded_by_reason; census_not_counts for bool, float, string and negative counts; census_scored and
census_sport_block; a stale MANIFEST_SHA256 pin and an edited manifest both refuse manifest_sha_mismatch; the PRIMARY
digest pinned as ELIGIBLE refuses eligible_sha_mismatch; the primary count pinned as eligible and a census
eligible_games disagreement refuse eligible_count_mismatch; census_ids_differ; warmup_folds_mismatch (both halves);
each of the eight pins missing refuses by name and a duplicated pin refuses; a draft with a line refuses emit;
--check ABSENT, MATCH over a CRLF draft, DUPLICATE, DIFFERS naming census, draft bytes unchanged; --tier has no default.

## Orchestrator real emission

Orchestrator real emission (2026-09-23 16:5xZ, from the h82 candidate over the main tree's landed inputs; the line itself is NOT
reproduced here): --census data/cache/ingame_grade_joined/_census/nba_checkpoints_r1_S387_master/census.json --manifest
data/cache/ingame_grade_joined/nba_checkpoints_r1/manifest.json --corpus-dir data/cache/ingame_grade_joined/nba_checkpoints_r1
--pins-record docs/evidence/harness/S402_reconciliation_real_2026-09-22.md --draft docs/evidence/ingame/
S382_NBA_PREREG_DRAFT_r1_2026-09-21.md --tier T2. RESULT: exit 0; ids=1593;
ids_sha=04c182de96f7433ee1e65d355102e82dcd58693f960bac266d62ef7c66453805 (equals the pinned ELIGIBLE sha);
manifest_sha256 5c4c1d10... (equals the pin); family ingame_four_arm_nba_r1; corpus nba_checkpoints_r1; line_bytes=86171;
line_sha256=a3d968134ab4f3e82e361eb42f370b850e41e2bae309a4abc5507b4c2513e9ba.
--check against the draft: ABSENT, exit 0 (the draft carries no line yet; pasting it is the seal
runbook's step B2(e), after S395 lands). The runner has NOT been invoked against the line (NOT VERIFIED).

## FIX 1b

Local CONSTRUCT fixtures only; no archive, network, pod or runner invocation. The amended regressions were
run before implementation changes with the same per-file pytest command above: `11 failed, 30 passed`.

- Tier 2 correction 1: ticks 6 -> 6.0, warmup true -> 1, and a duplicate tier key each reproduced
  `check=DIFFERS first_differing_key=bytes_or_key_order`. The draft now uses guards.unique_object;
  per-key canonical JSON text comparisons preserve types and follow KEY_ORDER deterministically.
  The three regressions require census, census and duplicate_json_key respectively, and unchanged draft bytes.
- Tier 1 correction 1 / tier 2 correction 2: the memo regression failed with
  `AssertionError: assert 'no real ids count' not in ...`. The final section now attributes the recorded
  emission to the orchestrator, says this lane has not re-run it, and both full hex digests occupy one line.
  The regression checks attribution, whole digests and NOT VERIFIED remaining last.
- Tier 2 note 3, ruled binding by amendment 1: manifest `[1]` with its matching canonical pin reproduced
  `AttributeError: 'list' object has no attribute 'get'`. An object check now refuses manifest_not_object.
  Four fixtures cover array, null, integer and string manifests, requiring exit 2 and empty stdout.
- Tier 1 note 2, ruled binding by amendment 1: folds[0]["x"] = NaN reproduced
  `ValueError: Out of range float values are not JSON compliant`. Serialization now catches ValueError
  and raises census_not_counts. NaN and both infinities require that named refusal, exit 2 and empty stdout.

After fixes, `python -m pytest tests/platformkit/ingame/test_nba_trial_line.py -q -p no:cacheprovider`
reported `41 passed` (the original 30 plus 11 regressions). Type-only drafts now pass the census-key
assertion; duplicate keys pass duplicate_json_key; all seven malformed-input fixtures pass their named
refusal and empty-stdout assertions; the memo regression passes.
`python -m scripts.platformkit.ingame.nba_trial_line --help` exited 0. There is no self-check CLI flag;
the row's self_check API passed one emitted CONSTRUCT line with all three eligible fixture ids.
ASCII, LF and <=300-line checks passed for all three owned files.
Contract preflight with `--base master --spec docs/evidence/tracking/specs/S425_spec.md` and
`--paths scripts/platformkit/ingame/nba_trial_line.py tests/platformkit/ingame/test_nba_trial_line.py
docs/evidence/harness/S425_nba_trial_line_2026-09-23.md` passed 9 checks, with zero FAIL.

## NOT VERIFIED

- The real emission was run by the orchestrator, not the build lane; recorded above. This lane has not re-run it.
- Whether the S387 census still equals the runner's recomputed census after S417 / S395 land (B_lag adds eligibility
  counting such as no_prior_tick_for_b_lag). If the census is re-run, the line must be re-emitted from the new file,
  with the pins from the post-S417 S402 transcription (runbook B3), before the seal.
- The runner itself was not run against an emitted line.
