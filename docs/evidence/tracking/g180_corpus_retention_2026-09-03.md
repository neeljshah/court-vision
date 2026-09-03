# G180 Corpus Retention - A5 Early-Stop Evidence

## Result

Verdict: NOT VALIDATED (no retention pass landed).

G180's mandatory A5 reader survey found committed lanes that re-read corpus
sources for re-measurement. Per the G180 acceptance rule, automatic deletion is
unsafe in that state. This is the required full-success early stop: no deletion
implementation, test, deployment, daemon change, source deletion, or change
under `src/` was made.

## Q8 premise reproduction and daemon durability contract

The daemon retains a completed staged source by moving it into the corpus:

```text
scripts/platformkit/track_daemon_done.py:209-214
def retain(video: Path, corpus: Path, printer: Callable[[str], None]) -> bool:
    try:
        corpus.mkdir(parents=True, exist_ok=True)
        video.replace(corpus / video.name)
        return True
```

The daemon's durable predicate is stricter than the mere presence of two paths.
It requires a CSV with at least one data row and a parseable sidecar containing
the required fields with `csv_fsynced` true:

```text
scripts/platformkit/track_daemon_done.py:198-206
def read_adjudicated(tracking: Path, game_id: str) -> dict | None:
    if tracking_rows(tracking, game_id) == 0:
        return None
    try:
        payload = json.loads((tracking / game_id / VERDICT_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if _REQUIRED <= payload.keys() and payload["csv_fsynced"] is True else None
```

`tracking_rows` returns zero for an unreadable CSV or for a header-only CSV
(`scripts/platformkit/track_daemon_done.py:31-38`). The hot-path dedupe branch
uses this same predicate and explicitly preserves missing verdicts for
re-tracking (`scripts/platformkit/track_daemon.py:367-374`). A future retention
pass therefore must call `read_adjudicated`, rather than checking sidecar path
existence alone, to match the daemon exactly.

## A5 exhaustive executable-reader survey

Search method: `git grep` over every tracked executable tree (`scripts`,
`kernel`, `domains`, `api`, `src`, and `tests`) for `footage_corpus` and
`FOOTAGE_CORPUS`, followed by source inspection. `git ls-files --others
--exclude-standard` was empty, so no untracked executable reader was omitted.

Readers that re-measure or regenerate evidence from source footage:

| Reader | Evidence | What deletion breaks |
|---|---|---|
| `scripts/platformkit/tracking_corpus_ab.py` | Defaults `--corpus` to the corpus and enumerates clips at lines 36-45 and 177-195; `run_clip` invokes a tracker subprocess at lines 59-70. | Its bounded corpus A/B re-track cannot run for a deleted source, so its per-game baseline comparison loses a selectable unit. |
| `scripts/platformkit/tracking/footage_census.py` | Uses the corpus by default at lines 47-50; opens each source and reads evenly spaced frames at lines 95-144. | The cross-sport footage census cannot be reproduced for a deleted source. |
| `scripts/platformkit/basketball_relabel_image_px.py` | The `--reemit-out` lane builds a corpus video path and passes it to `source_resolution` at lines 184-198. | The source-plane re-emission measurement skips the game as no footage. |
| `scripts/platformkit/g103_g68_tile_recipe.py` | The remote tile recipe opens `POD_ROOT/source_clip` with `cv2.VideoCapture` at lines 94-100. | G68 tile reconstruction cannot regenerate its fixed source-frame images. |
| `scripts/platformkit/g110_tile_nonreproducibility.py` | Its remote comparison opens corpus clips for seek, sequential, and full-frame reads at lines 102-114 and 172-175. | The nonreproducibility measurement cannot rerun against that source. |
| `scripts/platformkit/g126_g111_label_audit.py` | The remote audit opens `POD_ROOT/<clip>.mp4` at lines 69-75. | The label audit cannot regenerate raw audit frames. |
| `scripts/platformkit/g137_qualifying_frame_scale.py` | The source inventory and render path open corpus clips at lines 33-45 and 139-153. | The qualifying-frame scale measurement cannot reproduce its sampled frames. |
| `scripts/platformkit/g148_two_slot_measure.py` | Its remote program opens selected and sampled corpus frames at lines 108-125. | The two-slot measurement cannot rebuild discarded-frame and contact-sheet evidence. |

The remaining literal references are not source re-measurement readers:
`baseball_s4_emission.py` compares a manifest string to a fixed path;
`footage_bridge.py` and `track_daemon.py` use the corpus path for transport or
existence/dedupe; `worktree_data_links.py` exposes a junction; and the three
test modules use literals or temporary fixtures. They do not weaken the A5
finding above.

## Current exhaustive read-only inventory

The pod inventory was run read-only in `/workspace/nba-ai-system` after the
reader survey. It enumerated every `*.mp4` currently resident in
`data/footage_corpus`, derived the daemon game id with the daemon filename
convention, and applied the exact `read_adjudicated` logic quoted above. No
file was opened for writing, moved, deleted, or deployed.

```text
G180 READ-ONLY INVENTORY
KEEP bytes=3580059573 path=data/footage_corpus/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4 reason=tracking_data.csv has no data rows
KEEP bytes=2931985407 path=data/footage_corpus/wnba__wnba_01.mp4 reason=tracking_data.csv has no data rows
TOTAL sources=2 durable_deletable=0 durable_bytes=0 keep=2 keep_bytes=6512044980
```

The current exhaustive denominator is 2 sources: 0 durable-and-deletable
(0 bytes), and 2 retained (6,512,044,980 bytes). Both are retained because
their tracking CSV has no data rows. This is B3-compliant pass-through behavior,
not a failure classification.

There is no shipped retention-pass dry run because A5 requires that no such
pass land while the above re-measurement readers exist. Consequently there are
no `WOULD_DELETE` lines to paste; the current read-only inventory likewise
contains zero candidates and names every retained source and reason.

## B self-check

| Condition | Self-check |
|---|---|
| B1 circular metric | Pass. The inventory enumerates all current corpus sources; none were excluded. |
| B2 non-additive schema | Pass. No schema or reader changed. |
| B3 fall-through loss | Pass. Both incomplete sources remain retained; absent evidence is never treated as bad. |
| B4 re-claim loop | Pass. No claim or failure behavior changed. |
| B5 pre-verification deploy | Pass. No pod file was deployed. |
| B6 orphans | Pass. No module moved or retired. |
| B7 head-slice evidence | Not applicable. The metric is an exhaustive construct inventory. |
| B8 self-fit evidence | Not applicable. No model or scored residual. |
| B9 degenerate denominator | Pass. Unit is each distinct resident source file. |
| B10 moved bar | Pass. No bar, threshold, eligibility definition, or verdict changed. |

## NOT VERIFIED

- No standalone deletion utility or focused deletion-safety test was added,
  because the A5 early-stop condition prohibits landing it.
- The two retained source rows did not exercise the distinct table-present but
  verdict-absent case in the current pod inventory. The daemon predicate still
  returns `None` for that case by construction, and no deletion code exists to
  act on it.
- The historical manual deletion total cited by G180 was not used as the
  current metric; the counts above are the fresh exhaustive pod reproduction.
