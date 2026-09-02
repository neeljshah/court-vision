# S68 -- portable gate-corpus sidecars (2026-09-03)

Bookkeeping only: this row moves BYTES and PATHS, never a number, a bar or a
verdict. No hypothesis was scored, no ledger was read or charged, no K moved.
Calibration language only.

VERDICT: **ACCEPT**. `combo/corpus_cache` now records source paths RELATIVE to
the repo root plus the corpus parquet's own `corpus_sha256`; an explicit
`load_gate_corpus(sport, portable=True)` loads a corpus whose recorded sources
are unavailable on this host by verifying those parquet bytes instead. On the
pod all four gate corpora now load (was 1/4, soccer only): **mlb 39,162 /
nba 1,814 / soccer 25,834 / tennis 41,886 rows**, matching the local row counts
exactly. Default (non-portable) behaviour is unchanged, byte for byte.

## 1. THE CHANGE (additive; no semantics change on the build host)

| before | after |
|---|---|
| `_source_manifest` keys = `str(p)` (absolute host path) | `_source_key(p)` = repo-relative posix; absolute only for a source outside the repo |
| sidecar has no hash of its own parquet | sidecar records `corpus_sha256` of the parquet as written |
| `load_gate_corpus(sport)` resolves `Path(src)` | resolves via `_resolve_source`: relative -> CURRENT `_REPO`; **absolute = legacy, still honoured when it exists here** |
| an unavailable source always refuses | refuses by default; `portable=True` answers it with the `corpus_sha256` check |
| `freshness_report` says nothing about loadability | additive key `load_provenance` in {`host-local`, `portable-sidecar`, `unloadable`} |

`portable=True` covers BOTH ways a recorded source can be unavailable: the path
is missing, and a DIFFERENT file sits at that path. The second case is not
hypothetical -- the pod carries its own `data/domains/mlb/games.parquet`, and
without that arm mlb still refused on the pod (measured, first deploy attempt).

Two honest limits of the portable check, stated because it is an opt-in:
it is an INTEGRITY check, not a freshness check -- it proves the parquet is the
file the sidecar describes, and says nothing about whether the sources have
moved since; and `freshness_report(sport)["stale"]` is left telling the source
truth independently (a portable-loadable corpus on a source-less host reports
`stale = True`, which is correct and is asserted by a test).

NAMING DEVIATION (deliberate, B2): the spec asked for the label
`provenance: portable-sidecar`. `freshness_report`'s `provenance` key already
carries S53's per-column join provenance and has a reader
(`test_corpus_cache_soccer_enrich.py:74`), so the label went to a NEW key
`load_provenance` rather than clobbering an existing one.

## 2. BACKWARD COMPATIBILITY -- proven BEFORE any sidecar was rewritten

New code + the four UNCHANGED legacy absolute sidecars, versus the same call
under the old code:

    freshness_report(sport) for mlb/nba/soccer/tennis
    shared-key diffs: []            (all 13 pre-existing keys identical, 4/4 sports)
    additive new keys: ['load_provenance']   (host-local on all four)
    load_gate_corpus: OK 4/4        mlb 39162  nba 1814  soccer 25834  tennis 41886

So a sidecar written before this change keeps loading, and its report is
unchanged except for the one added key. (Snapshots:
`before.json` / `after_legacy.json` in the lane scratchpad.)

## 3. THE FOUR SIDECARS REGENERATED -- parquets byte-identical

The four sidecars were rewritten in place into the relative form (same keys the
new `build_gate_corpus` writes: relativised source keys, unchanged mtime+sha256
per source, plus `corpus_sha256`). The parquets were NOT rebuilt and NOT
touched, so byte-identity is exact, not approximate:

| sport | parquet md5 before == after | recorded corpus_sha256 | rows |
|---|---|---|---|
| mlb | 04289c55decd4a1e5ce3085767c50837 | ac60c9cb18958c20ff53d7d0b698700375b6a0ce15e7ef0ecd20fb730e0903bd | 39,162 |
| nba | f0547f43a668f336bb80c0835dae0db3 | 716f6f5f3f2181051e352936efa60d616c9de029a026b85cc585d6ed20cb0aaf | 1,814 |
| soccer | aca8942d54e37aeff735989eb6c3d8be | e0d2f13e7a53b3ed578e81e38db82f14bb6d3a71e31a9c7cb636d5b4c7e92bc6 | 25,834 |
| tennis | 1a1e26173f266827f0e9b6d438918031 | 22d006f2b4f7a7186876e133508e1e9ddf14af3570f1d20a73d73d1d3669d700 | 41,886 |

`freshness_report` after the rewrite versus the ORIGINAL before-snapshot: the
only key that differs on any sport is `sources` (each `path` absolute ->
relative, e.g. `C:\Users\neelj\nba-ai-system\data\domains\mlb\games.parquet` ->
`data/domains/mlb/games.parquet`). `built_at`, `n_rows_at_build`,
`n_rows_cached`, `order_basis`, `provenance`, `stale`, `stale_reason`,
`cache_mtime` and the load result are identical on all four. All four still
report `stale = False`, `load_provenance = host-local`, `order_basis =
event_date`.

## 4. THE POD -- 4/4, and what was shipped

Local verification (section 2, 3 and the tests) completed BEFORE anything left
this host. Shipped: three sidecars (read-only inputs) and the module.

    scp data/cache/combo/gate_corpus_{nba,mlb,tennis}.sources.json  ->  pod data/cache/combo/
    scp scripts/platformkit/combo/corpus_cache.py                   ->  pod (md5 parity)

md5 parity local == pod: `corpus_cache.py` **90f22b510aa624c82fd2a6ad8ab34ec2**;
sidecars mlb `1cdd2b1b...`, nba `f490be00...`, tennis `ae4521bf...`. The three
gate-corpus PARQUETS did not need copying -- the pod's copies (shipped in the
S16 hour) were already byte-identical to local (md5 `f0547f43` / `04289c55` /
`1a1e2617`), which is exactly why the `corpus_sha256` vouch succeeds. The pod's
soccer pair was left ALONE: it was rebuilt on the pod in the S16 hour, its
sidecar carries pod-local ABSOLUTE keys, and it loads through the legacy arm.

Measured on the pod (`/usr/local/bin/python`, Python 3.12):

    === portable=True ===
    mlb     rows  39162 cols  9 units era_2010_2021,era_2022_2026 prov portable-sidecar order event_date
    nba     rows   1814 cols 15 units 2024-25,2025-26             prov portable-sidecar order event_date
    soccer  rows  25834 cols 33 units D1,E0,E1,F1,I1,SP1          prov host-local      order event_date
    tennis  rows  41886 cols 11 units ATP,WTA                     prov portable-sidecar order event_date

    === default (portable OFF) ===
    mlb     REFUSED StaleCorpusError source data/domains/mlb/games.parquet ... changed since build
    nba     REFUSED StaleCorpusError source data/domains/basketball_nba/games.parquet ... no longer exists
    soccer  rows 25834
    tennis  REFUSED StaleCorpusError source data/domains/tennis/matches.parquet ... no longer exists

4/4 loadable in portable mode; the default mode still refuses all three with a
NAMED source, so nothing loads silently. This closes the S16 hour's
`2,220 T0 StaleCorpusError` denominator (mlb 540 + nba 1,350 + tennis 330) as a
CAUSE; it does not re-run that hour and claims no throughput number.

MUST NOT MOVE, checked after the deploy: the foundry runner **pid 165812 ALIVE**
and untouched (its results DB was never opened by this lane), no process started
or killed, `data/cache/eval_gate/backtest_fwer.jsonl` **still absent**,
`data/registry/` **still absent** on the pod, no ProcSpec added, no threshold
touched. Nothing under `scripts/platformkit/eval_gate/` was deployed.

## 5. TESTS (per-file only)

    python -m pytest scripts/platformkit/combo/test_corpus_cache_freshness.py -q   -> 22 passed (was 10)

The 12 added cases (8 named + a 4-sport parametrization) build a corpus on a
simulated host A via the REAL `build_gate_corpus`, copy ONLY the cache to a host
B with no sources, and assert: relative keys + `corpus_sha256` written; host B
REFUSES by default naming `data/domains/fake_source.parquet`; host B LOADS with
`portable=True`; a tampered parquet is refused in portable mode (`unloadable`);
a pre-S68 sidecar with no `corpus_sha256` is refused in portable mode rather
than loaded silently; a DIFFERENT file at the recorded path behaves like an
absent one under `portable=True` and still refuses by default; a legacy ABSOLUTE
sidecar still loads (`host-local`); and every real shipped sidecar is relative,
resolvable and hash-matched.

Readers of the touched surface, re-run in master (A5):

    python -m pytest tests/platform/test_combo_factory.py -q                        -> 13 passed
    python -m pytest scripts/platformkit/combo/test_corpus_cache_soccer_enrich.py -q ->  5 passed
    python -m pytest scripts/platformkit/eval_gate/test_calibration_report.py -q     ->  9 passed

Every other caller (`batch_gate.py:193`, `close_join.py:162/194`,
`catalog_rescreen.py:284`, `screen_predictor.py:265`, `tiers.py:215`,
`mechanism_close_effect.py:55`, `calibration_report.py:346`) calls
`load_gate_corpus(sport)` positionally with one argument and is unaffected --
`portable` defaults to False, so no caller opts in by accident.

## NOT VERIFIED

- **Nothing here is a finding.** No hypothesis was screened or scored, no prereg
  sealed, no K read, no ledger row appended. Row counts are file facts.
- **The portable check is integrity, not freshness.** A corpus loaded with
  `portable=True` is provably the file its sidecar describes; whether its
  SOURCES have since changed is unknowable on a host that does not have them.
  A pod screen run on a portable-loaded corpus inherits that limit.
- **No caller passes `portable=True` yet.** The pod runner (pid 165812) still
  calls `load_gate_corpus(sport)`, so mlb/nba/tennis hypotheses would still fail
  T0 there. Wiring the runner (an explicit, labelled opt-in at the T0 boundary)
  is NOT done in this row and is not claimed.
- **The pod's soccer sidecar is still absolute** (pod-local, from the S16
  rebuild). It loads through the legacy arm; it was deliberately not overwritten
  and would not travel to a third host.
- **`build_gate_corpus` was not re-run on any sport.** The four sidecars were
  migrated in place; the new writer's output shape is asserted by test, not by a
  full local rebuild of the four corpora.
- The four parquets' byte-identity is asserted by md5 before/after with no
  rebuild in between -- a stronger statement than a reproduced build, but it is
  NOT evidence that a rebuild would reproduce them byte for byte.
- S67 (results_db drops `family`) is untouched and still open; this row changes
  no promotion, tier or ledger path.
