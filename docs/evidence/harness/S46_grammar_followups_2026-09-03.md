# S46 -- grammar follow-ups from the S11 landing (a)-(e)

Verdict: **ACCEPT**. Every number below was measured in MASTER this session.
Calibration language only; nothing here is evaluated, priced or promoted.

## (a) `.gitignore:342` untracked every `__init__.py` under `scripts/` -- FIXED

PREMISE re-measured first (Q8), and it held:

| check | result |
|---|---|
| `git check-ignore -v scripts/platformkit/__init__.py` | `.gitignore:342:scripts/**/_*` |
| `git ls-files scripts \| grep -c __init__.py` | **20** |
| `find scripts -name __init__.py \| wc -l` | **114** (0 under `node_modules` / vendored) |

FIX: ONE line, `!scripts/**/__init__.py` at `.gitignore:343`, keeping the original
`scripts/**/_*` rule that protects `_scratch`-style throwaways. The four
pre-existing per-package negations below it are now redundant but were left
alone (one targeted change).

Proof, by `git check-ignore` exit status over all 94 previously-untracked files:
**93 not ignored, 1 still ignored**. Tracked `__init__.py` under `scripts/`:
**20 -> 113 of 114**. Commit `4ca819047`, 94 files, 603 insertions, 0 paths under
`data/` or `vault/`.

The 1 exception is `scripts/team_system/models/__init__.py`, held by the
unrelated `.gitignore:208 models/` directory rule. That rule hides the WHOLE
package -- `domain_model.py` and `domain_registry.py` are untracked too, so
adding only the marker would have been cosmetic. Filed as a new gap, not forced.

FRESH-CLONE SIMULATION: `git worktree add --detach <tmp> HEAD` (12,635 files
checked out), then in that clean checkout
`python -c "import scripts.platformkit.eval_gate.scoring"` -> resolved to the
worktree's own `scoring.py`, and `scripts.platformkit.foundry.grammar` likewise.
Worktree removed and pruned afterwards.

## (b) `family` + `runtime_available` on `Hypothesis` -- ADDITIVE

Both added with defaults (`family=""`, `runtime_available=False`), so every
pre-S46 construction (lane B `tiers.py`, lane C `results_db.py` and their tests)
still builds. Both are EXCLUDED from `canonical_payload`, so neither can move a
`semantic_hash`: the same feature grid must hash identically no matter which
family enumerated it or whether the column is servable at runtime. The exclusion
is documented in the dataclass docstring and asserted by
`test_family_and_runtime_available_do_not_move_the_hash`.
`enumerate_family` now fills both from the family spec it already required.

## (c) `_REGISTRY_PATH` anchored to the repo root

`Path(__file__).resolve().parents[3] / "data" / "registry" / "signal_registry.parquet"`.

| cwd | registry resolves (before, relative) | registry resolves (after) | `semantic_hash` |
|---|---|---|---|
| `C:\Users\neelj\nba-ai-system` | True | True | `0a4562c2...8bd88c0f` |
| `C:\Users\neelj` | **False** | True | `0a4562c2...8bd88c0f` |
| `C:\Program Files\Git` | not run | True | `0a4562c2...8bd88c0f` |

Identical hash from all three cwds. HONEST CEILING: the hash was not observably
different off-root even before, because `signal_registry.parquet` (86 rows) has
no `feature` / `column` / `source_column` / `name` column -- its identity columns
are `signal_id` and `entity` -- so `_signal_ids()` returns `{}` and every feature
already hashes as its raw column name. The fix removes a latent cwd dependence;
it does not change any hash today.

## (d) `phase` alphabet closed

Enumerated once from the source columns `regime_calibration.buckets` reads
(`game_phase`, `phase`, `period`, `quarter`, `inning`) across every gate corpus,
domain and ingame parquet: only `period` is materialized, in **5 files**
(4 `basketball_nba/ingame_hypothesis_*_rows`, 1 `wnba/cdn_backfill_states`), with
value union **{"1", "2", "3"}**. Snapshot: the ordinals `1`-`9` (all five sources
are ordinal counters; 9 covers an NBA overtime period and an MLB ninth inning)
PLUS the three phase kinds `period|quarter|inning`, which are the S11 spec's own
written vocabulary and already in use downstream. Unknown value -> `ValueError`;
`phase=periods`, `phase=Q1`, `phase=10` all raise.

## (e) `catalogue.py` -- the shared catalogue-to-sport mapping

Lifted out of `test_grammar.py` into `scripts/platformkit/foundry/catalogue.py`
(`NAMED` 32 entries, `GLOBS` 2, `sport_of`, `entries`, `absent`, and a `__main__`
readout). Import-free of `foundry/tiers.py` and `foundry/results_db.py` by
design, since it is the shared input to both.

`python -m scripts.platformkit.foundry.catalogue`:

```
PRESENT: 69 parquets    mlb: 15  nba: 18  soccer: 23  tennis: 13
ABSENT / SKIPPED: 5 of 32 named
  - data/domains/soccer/asof_discipline_features.parquet
  - data/domains/tennis/asof_features_wta.parquet
  - data/domains/tennis/asof_return_wta.parquet
  - data/domains/tennis/asof_meta_wta.parquet
  - data/domains/tennis/schedule_density_wta.parquet
```

Exactly the 5 the S11 verifier named.

## S11 numbers reproduced

| quantity | S11 verifier | S46 shared catalogue |
|---|---|---|
| present parquets | 69 | **69** |
| columns kept | 979 | **979** |
| enumerated | 264,330 | **264,330** |
| distinct `semantic_hash` | 116,370 | **116,370** |
| collisions | 0 | **0** |

DEFECT FOUND while lifting the mapping: the inline mapping in `test_grammar.py`
fell through to `tennis` for `data/cache/combo/gate_corpus_nba.parquet` (it tested
for the substring `basketball_nba`, never `nba`). Re-running the same 69 files
with that pre-S46 mapping gives **115,560 distinct, 810 fewer**; the verifier's
own reproduction used a correct labelling, which is why `catalogue.py` matches
116,370 exactly. Enumerated total and collision count are invariant to the label.

## Tests (per-file, in master)

- `tests/platformkit/foundry/test_grammar.py` -- **5 passed** (was 3; +2 for (b) and (d))
- `tests/platformkit/foundry/test_catalogue.py` -- **13 passed** (new)
- A5 readers re-run unchanged: `test_tiers.py` **6 passed**, `test_results_db.py` **7 passed**

LOC: `grammar.py` 206, `catalogue.py` 109, `__init__.py` 1, `test_grammar.py` 56,
`test_catalogue.py` 49 -- all <= 300. stdlib + pandas only. No write path, no
`_charge_ledger`, `data/registry/**` read-only, no trial charged, no threshold moved.

## NOT VERIFIED

- `n = 116,370 (CONSTRUCT)` -- an enumeration. No hypothesis here has been
  evaluated, scored, priced, promoted or charged against the FWER ledger.
- The cwd fix (c) is structural: with `signal_registry.parquet` carrying no
  feature-name column, zero features resolve to a `signal_id` today, so no hash
  observably changed. The guarantee is untested against a registry that does
  resolve.
- The `phase` snapshot rests on the columns materialized on disk 2026-09-03.
  A future corpus with a `game_phase` column holding labels outside
  `{1..9, period, quarter, inning}` will raise -- by design, but it is a bar that
  a later corpus can hit.
- `scripts/team_system/models/` (3 modules) is still entirely untracked via
  `.gitignore:208`; not fixed here, filed as a new gap.
- The fresh-clone check imported two packages, not every one of the 93 markers.
