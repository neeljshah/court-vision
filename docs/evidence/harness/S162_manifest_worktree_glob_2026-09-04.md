# S162 Manifest Worktree Glob Evidence

## Scope and verdict

S162 is a five-case CONSTRUCT. Verdict: ACCEPT.

The only code change makes the manifest's glob pattern relative to the repository
root before calling `Path.glob`. The relative-key helper also uses lexical absolute
paths, rather than dereferencing the worktree's shared `data/` link. This preserves
the manifest's repository-relative keys in both trees.

No test was added, skipped, or rewritten. No threshold, required-source declaration,
sidecar, pod bootstrap probe, `--check-pod` behavior, or `--ship` behavior changed.

## Premise reproduction (worktree, before change)

Command:

```text
python -m pytest tests/platformkit/ops/test_factory_source_manifest.py -q
```

Output:

```text
FF...                                                                    [100%]
================================== FAILURES ===================================
___________________ test_manifest_comes_from_the_registries ___________________

    def test_manifest_comes_from_the_registries():
>       need = fsm.required()

tests\platformkit\ops\test_factory_source_manifest.py:19:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
scripts\platformkit\ops\factory_source_manifest.py:182: in required
    _ingame(out)
scripts\platformkit\ops\factory_source_manifest.py:143: in _ingame
    _add(out, _rel(store) + "/*.jsonl", origin)
scripts\platformkit\ops\factory_source_manifest.py:76: in _add
    hits = sorted(_REPO_ROOT.glob(spec))
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

self = WindowsPath('C:/Users/neelj/nba-track-a12')
pattern = 'C:/Users/neelj/nba-track-a12/data/cache/ingame_grade_joined/soccer_intl/*.jsonl'

    def glob(self, pattern):
        """Iterate over this subtree and yield all existing files (of any
        kind, including directories) matching the given relative pattern.
        """
        sys.audit("pathlib.Path.glob", self, pattern)
        if not pattern:
            raise ValueError("Unacceptable pattern: {!r}".format(pattern))
        drv, root, pattern_parts = self._flavour.parse_parts((pattern,))
        if drv or root:
>           raise NotImplementedError("Non-relative patterns are unsupported")
E           NotImplementedError: Non-relative patterns are unsupported

..\AppData\Local\Programs\Python\Python310\lib\pathlib.py:1030: NotImplementedError
______________ test_pod_path_subset_drops_the_ingame_only_stores ______________

    def test_pod_path_subset_drops_the_ingame_only_stores():
>       full, gated = fsm.required(), fsm.required(ingame=False)

tests\platformkit\ops\test_factory_source_manifest.py:45:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
scripts\platformkit\ops\factory_source_manifest.py:182: in required
    _ingame(out)
scripts\platformkit\ops\factory_source_manifest.py:143: in _ingame
    _add(out, _rel(store) + "/*.jsonl", origin)
scripts\platformkit\ops\factory_source_manifest.py:76: in _add
    hits = sorted(_REPO_ROOT.glob(spec))
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

self = WindowsPath('C:/Users/neelj/nba-track-a12')
pattern = 'C:/Users/neelj/nba-track-a12/data/cache/ingame_grade_joined/soccer_intl/*.jsonl'

    def glob(self, pattern):
        """Iterate over this subtree and yield all existing files (of any
        kind, including directories) matching the given relative pattern.
        """
        sys.audit("pathlib.Path.glob", self, pattern)
        if not pattern:
            raise ValueError("Unacceptable pattern: {!r}".format(pattern))
        drv, root, pattern_parts = self._flavour.parse_parts((pattern,))
        if drv or root:
>           raise NotImplementedError("Non-relative patterns are unsupported")
E           NotImplementedError: Non-relative patterns are unsupported

..\AppData\Local\Programs\Python\Python310\lib\pathlib.py:1030: NotImplementedError
=========================== short test summary info ===========================
FAILED tests/platformkit/ops/test_factory_source_manifest.py::test_manifest_comes_from_the_registries
FAILED tests/platformkit/ops/test_factory_source_manifest.py::test_pod_path_subset_drops_the_ingame_only_stores
2 failed, 3 passed in 19.37s
```

The reproduced traceback line is `scripts/platformkit/ops/factory_source_manifest.py:76`.

## After change (worktree)

Command:

```text
python -m pytest tests/platformkit/ops/test_factory_source_manifest.py -q
```

Output:

```text
.....                                                                    [100%]
5 passed in 15.94s
```

## Main repository reproduction and manifest comparison

Main repository (read only): `C:\Users\neelj\nba-ai-system`

Command run before and after the worktree change:

```text
python scripts/platformkit/ops/factory_source_manifest.py --pod-path-only
```

Before/after comparison output:

```text
MAIN_BEFORE_LINES=63
MAIN_AFTER_LINES=63
MAIN_BEFORE_SOURCES=61
MAIN_AFTER_SOURCES=61
MAIN_BEFORE_AFTER_BYTE_IDENTICAL=True
DIFF=(empty)
```

The 63 physical lines are the two summary lines plus 61 source rows. The required
source set is unchanged at 61. No stderr was emitted by either manifest command.

Main-repository test command and output:

```text
python -m pytest tests/platformkit/ops/test_factory_source_manifest.py -q -p no:cacheprovider
.....                                                                    [100%]
5 passed in 13.56s
```

## Verifier-contract self-check

- B1: The construct runs all five existing cases; none are excluded.
- B2: No schema or field changed; the existing test is the only reader check needed.
- B3-B6: No gate, claim lifecycle, deployment, module move, import, or test reference changed.
- B7-B9: Not applicable to this CONSTRUCT; no sampled, fitted, or recycled metric is claimed.
- B10: No threshold or harness bar changed.
- Q1-Q6 and Q9: Not applicable; S162 is not a scored comparison and makes no calibration claim.
- Q7: The exhaustive construct is `n = 5`; both trees ran all five cases.
- Q8: The worktree premise was remeasured before the code change and reproduced the two named failures.

## NOT VERIFIED

- `--check-pod` and `--ship` were not invoked. S162 requires a local construct and
  a read-only manifest comparison, not a pod connection or transfer.
- Full local-presence output is not comparable between the two working directories:
  the worktree reports `data/cache/venue_history/nba_close_corpus.parquet` absent,
  while the main repository reports it present. Both enumerate the same 61 required
  sources. No data file was changed.
