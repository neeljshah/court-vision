# G183 corpus keep-list and deletion accounting

Verdict: ACCEPT. This is an exhaustive construct audit of the seven readers
identified by G180. It adds evidence only: no reader, footage file, threshold,
coordinate contract, verdict, queue, daemon, keeper, or pod file changed.

## Q8 premise reproduction

The premise is confirmed, not falsified. All seven named reader modules still
exist at HEAD and each still selects or opens corpus footage. The committed
G180 ledger record says that 23 corpus sources, about 22.9 GB, were already
deleted across two manual passes before this reader survey. The first pass's
ledger record names the two files it retained and says 18 others were removed;
it does not preserve a filename-by-filename deletion ledger for either pass.

## Reader selection: names versus globs

The table distinguishes a reader that has a fixed, artifact-named source set
from a reader that enumerates a variable corpus. A glob is not converted into a
fictional fixed keep-list entry.

| Reader | Naming or globbing evidence | Need and retention consequence |
|---|---|---|
| `tracking_corpus_ab.py` | `scripts/platformkit/tracking_corpus_ab.py:42-45` uses `corpus.glob("{}__*".format(sport))`; `:177` defaults the corpus to `data/footage_corpus`. | GLOB: every non-quarantined clip of the selected sport is eligible, capped by `--games` (default 3). No static clip name. Requires a per-sport representative-count policy. |
| `tracking/footage_census.py` | `scripts/platformkit/tracking/footage_census.py:48-49` makes the corpus a default directory and `:98-105` iterates every video file in it. | GLOB: every supported corpus video is a census unit. No static clip name. Requires a corpus-coverage policy, not a single-file exception. |
| `basketball_relabel_image_px.py` | `scripts/platformkit/basketball_relabel_image_px.py:47-49` globs every WNBA/NCAA tracking CSV; `:188-192` constructs `"{}__{}.mp4". | DYNAMIC NAME, not a corpus glob: every qualifying current WNBA or NCAA tracking directory names its corresponding corpus MP4 at run time. The separate read-only pod tracking-store enumeration found zero qualifying directories, so it names zero current pod clips; no committed fixed filename list exists. Retention policy must cover this tracking-directory mapping. |
| `g103_g68_tile_recipe.py` | `scripts/platformkit/g103_g68_tile_recipe.py:86-88` reads the fixed manifest and `:95-100` opens each `row['source_clip']`. | NAMED: the committed `g103_recall/tile_manifest.csv` names 11 files. They are in the keep-list below. |
| `g110_tile_nonreproducibility.py` | `scripts/platformkit/g110_tile_nonreproducibility.py:102-114` opens each manifest `row['source_clip']` by seek and sequential decode; its imported `_read_manifest` is `g103_g68_tile_recipe.py:14`. | NAMED: the same 11 G103 manifest files. This reader is the reason re-fetchable cannot be called recoverable. |
| `g126_g111_label_audit.py` | `scripts/platformkit/g126_g111_label_audit.py:51-53` reads labels, and `:70-75` opens `row['clip'] + '.mp4'`. | NAMED: the committed blind selection manifest currently names 11 files. They are in the keep-list. |
| `g137_qualifying_frame_scale.py` | `scripts/platformkit/g137_qualifying_frame_scale.py:32-43` globs `ncaa_basketball__*.mp4` and `wnba__*.mp4`; `:92-101` writes the resulting source names into its sample manifest. | GLOB for a new run: all NCAA and WNBA corpus clips. Its committed current sample manifest also records 18 concrete historical names, which are in the keep-list. Future retention therefore needs a basketball-family policy as well as the fixed historical list. |

## Named keep-list

Eligible denominator for the named-list share: 18 distinct filenames enumerated
from the committed G103 tile manifest, G126 blind selection manifest, and G137
sample manifest. This is not a denominator for the three glob readers. The
pod reconciliation command examined all four MP4 filenames currently in the
one corpus store, not a head sample:

```text
ssh -o BatchMode=yes -o ConnectTimeout=10 config.pod ls -1 /workspace/nba-ai-system/data/footage_corpus
```

The dynamic basketball mapping was reproduced separately against its input
store, not inferred from the corpus listing:

```text
ssh -o BatchMode=yes -o ConnectTimeout=10 config.pod "find /workspace/nba-ai-system/data/tracking -mindepth 2 -maxdepth 2 -type f -name tracking_data.csv -printf '%h\\n' | sed 's#.*/##' | LC_ALL=C sort | grep -E '^(wnba|ncaa_basketball)' || true"
```

It returned no qualifying directory names. The NCAA and WNBA queue existence
checks were also separate read-only calls and both returned `ABSENT`.

| Clip filename | Readers needing the named historical source | Pod now |
|---|---|---|
| `ncaa_basketball__ncaa_basketball_4Drw9t7xqgg.mp4` | G137 | GONE |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4` | G103, G110, G126, G137 | PRESENT |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p.mp4` | G103, G110, G126, G137 | GONE |
| `ncaa_basketball__ncaa_basketball_VIlUnUeCMmE.mp4` | G137 | GONE |
| `ncaa_basketball__ncaa_basketball_WFl3V7ZY4ss.mp4` | G103, G110, G126, G137 | GONE |
| `ncaa_basketball__ncaa_basketball_mRkuGgeECak.mp4` | G137 | GONE |
| `ncaa_basketball__ncaa_basketball_sRtHQbywiTE.mp4` | G103, G110, G126, G137 | GONE |
| `ncaa_basketball__ncaa_basketball_tiUvyvWOCxo.mp4` | G103, G110, G126, G137 | GONE |
| `ncaa_basketball__ncaa_basketball_zqBCKovJCQU.mp4` | G103, G110, G126, G137 | GONE |
| `wnba__wnba_01.mp4` | G103, G110, G126, G137 | PRESENT |
| `wnba__wnba_01_1080p.mp4` | G103, G110, G126, G137 | GONE |
| `wnba__wnba_02.mp4` | G103, G110, G126, G137 | GONE |
| `wnba__wnba_04.mp4` | G103, G110, G126, G137 | GONE |
| `wnba__wnba_05.mp4` | G103, G110, G126, G137 | GONE |
| `wnba__wnba_06.mp4` | G137 | GONE |
| `wnba__wnba_07.mp4` | G137 | GONE |
| `wnba__wnba_08.mp4` | G137 | GONE |
| `wnba__wnba_09.mp4` | G137 | GONE |

Result: 2/18 named required files are present and 16/18 are gone now. The two
other current corpus files are baseball files and do not satisfy this
keep-list. The 16 gone required filenames are the names marked GONE above;
they are intentionally listed individually rather than hidden in a count.

## Accounting for the 23 deletions

This is a full-success result even though sources readers need are gone.

The strongest committed historical cross-check is
`g116_retention/corpus_file_inventory.csv`, a 73-file pod inventory at
2026-09-02T22:59:52Z. It contains 12 of the 18 named keep-list files: all 11
G103/G110/G126 names plus
`ncaa_basketball__ncaa_basketball_mRkuGgeECak.mp4`. G180's post-pass inventory
then retained only `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4` and
`wnba__wnba_01.mp4`; the 10 other historically resident reader-required names
are now absent. Thus the manual deletion period definitely cost reader-needed
sources: at least these 10 were present in the committed pre-pass census and
are gone now:

```text
ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p.mp4
ncaa_basketball__ncaa_basketball_WFl3V7ZY4ss.mp4
ncaa_basketball__ncaa_basketball_mRkuGgeECak.mp4
ncaa_basketball__ncaa_basketball_sRtHQbywiTE.mp4
ncaa_basketball__ncaa_basketball_tiUvyvWOCxo.mp4
ncaa_basketball__ncaa_basketball_zqBCKovJCQU.mp4
wnba__wnba_01_1080p.mp4
wnba__wnba_02.mp4
wnba__wnba_04.mp4
wnba__wnba_05.mp4
```

The ledger records the count (23 total; 18 in the first pass) and the rule,
but not the individual deletion filenames. It therefore cannot prove which of
the 23 contained the other six currently-gone G137 names
(`4Drw9t7xqgg`, `VIlUnUeCMmE`, and `wnba_06` through `wnba_09`), even though
the committed G137 manifest shows that reader named them at its measurement.
Those six are GONE NOW, but their assignment to a particular manual deletion
pass is NOT VERIFIED. This missing individual deletion ledger is evidence loss,
not a reason to call the 23-source action safe.

## Re-fetchability versus recoverability

The read-only checks of the only relevant current queue stores found both
`/workspace/nba-ai-system/data/footage_queue_ncaa_basketball.json` and
`/workspace/nba-ai-system/data/footage_queue_wnba.json` absent. Consequently
none of the 16 GONE filenames is currently re-fetchable from its required
sport queue. None is recoverable as the original bytes from this pod.

| Gone filename | Re-fetchable from its sport queue now | Recoverable as original bytes now |
|---|---|---|
| `ncaa_basketball__ncaa_basketball_4Drw9t7xqgg.mp4` | No: NCAA queue absent | No |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p.mp4` | No: NCAA queue absent | No |
| `ncaa_basketball__ncaa_basketball_VIlUnUeCMmE.mp4` | No: NCAA queue absent | No |
| `ncaa_basketball__ncaa_basketball_WFl3V7ZY4ss.mp4` | No: NCAA queue absent | No |
| `ncaa_basketball__ncaa_basketball_mRkuGgeECak.mp4` | No: NCAA queue absent | No |
| `ncaa_basketball__ncaa_basketball_sRtHQbywiTE.mp4` | No: NCAA queue absent | No |
| `ncaa_basketball__ncaa_basketball_tiUvyvWOCxo.mp4` | No: NCAA queue absent | No |
| `ncaa_basketball__ncaa_basketball_zqBCKovJCQU.mp4` | No: NCAA queue absent | No |
| `wnba__wnba_01_1080p.mp4` | No: WNBA queue absent | No |
| `wnba__wnba_02.mp4` | No: WNBA queue absent | No |
| `wnba__wnba_04.mp4` | No: WNBA queue absent | No |
| `wnba__wnba_05.mp4` | No: WNBA queue absent | No |
| `wnba__wnba_06.mp4` | No: WNBA queue absent | No |
| `wnba__wnba_07.mp4` | No: WNBA queue absent | No |
| `wnba__wnba_08.mp4` | No: WNBA queue absent | No |
| `wnba__wnba_09.mp4` | No: WNBA queue absent | No |

Even if a later queue entry made one of the G103/G110 names re-fetchable, it
would still not make it recoverable for G110: that reader tests the fact that
a re-download and later decode need not reproduce the original byte timeline.
The same limitation applies to the G103/G126/G137 evidence that depends on
their named historical source frames.

## Recommendation

Do not implement retention in this row. Any future retention policy must keep
these 18 named historical files before deleting anything, and must separately
define and enforce a documented per-sport representative policy for the three
glob/dynamic readers; a durable verdict alone is not a safe deletion rule.

## VERIFIER_CONTRACT section B self-check

| Condition | Self-check |
|---|---|
| B1 circular metric | Clear. All seven specified readers and all 18 distinct named manifest files are included; the absent names remain in the result. |
| B2 non-additive schema | Clear. Evidence-only memo; no schema or reader changed. |
| B3 fall-through loss | Clear. Absence is reported as GONE, never classified as bad or passed on silently. |
| B4 re-claim loop | Clear. No claim or retry behavior changed. |
| B5 pre-verification deploy | Clear. Pod actions were read-only listings and absent-queue checks; nothing was copied or deployed. |
| B6 orphans | Clear. No module was moved or retired. |
| B7 head-slice evidence | Clear. The construct is exhaustive over all seven readers; the pod listing examined every current corpus filename. |
| B8 self-fit evidence | Not applicable. No fitted model or residual is claimed. |
| B9 degenerate denominator | Clear. Named-list unit is one distinct filename; reader unit is one specified reader. |
| B10 moved bar | Clear. No threshold, eligibility definition, coordinate contract, or verdict changed. |

## NOT VERIFIED

- The exact filename membership of all 23 manual deletions: the committed
  ledger preserves totals and the first-pass retained names, not an immutable
  per-file deletion manifest.
- Whether any off-pod archive still has original bytes for a GONE file.
- Re-fetchability from a future or external queue: the two relevant queues are
  absent on the pod now, and no external provider was queried.
- A glob-reader retention cardinality beyond the existing corpus-A/B default
  of three selected games; setting such a policy is outside this evidence row.

## Orchestrator verification and the cost, added at landing

Verified independently in master before landing (A2), recomputing from the
committed artifacts rather than trusting the lane:

- `g103_recall/tile_manifest.csv` holds 33 rows naming **11 distinct** source
  clips, matching the memo's NAMED count for G103/G110.
- The committed pod inventory `g116_retention/corpus_file_inventory.csv`
  (73 files, 2026-09-02T22:59:52Z) contains **12 of the 18** keep-list names,
  reproducing the memo exactly.
- Of those 12, **10 are gone from the pod now**, reproducing the memo's list
  name for name.

**The number the memo did not state: those 10 destroyed reader-required sources
totalled 2.94 GB**, recomputed by summing the `bytes` column of the committed
inventory over exactly those filenames.

**This is the orchestrator's error and it is recorded here as damage, not as a
managed trade-off.** I deleted 23 corpus sources across two manual passes on a
durability test alone, before the G180 reader survey that established which
sources are read existed. Ten sources that four separate readers name are gone
as a direct result, none is re-fetchable (both relevant sport queues are absent
from the pod), and none is recoverable as original bytes. For G110 specifically,
re-downloading would not repair the loss even if a queue returned: that reader
exists to test that a re-fetch does not reproduce the original byte timeline, so
its named sources are irreplaceable by construction.

The evidence loss compounds the footage loss: the ledger recorded deletion
COUNTS and the retained names, never a per-file deletion manifest, so six
further gone G137 names cannot be attributed to a pass at all. A retention
action that cannot say what it removed cannot be audited afterwards.

One discrepancy against the memo, checked and benign: the pod corpus now lists
**five** files rather than the four the memo enumerated. The extra is
`football__football_Z8Ezd95NnjM.mp4`, consistent with the bridge delivering it
after the lane's listing. It is not a keep-list name and does not affect any
count above.
