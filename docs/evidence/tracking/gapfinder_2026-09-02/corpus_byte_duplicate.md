# A byte-identical duplicate inflates the corpus denominator (2026-09-02)

Read-only on the pod, `md5sum` over the two 1080p football files flagged by the
resolution census (identical frame count 9,124 and identical size 148,410,XXX
bytes under two different names).

    1855b74edf86166cb23348f5b4da8a4a  data/footage_corpus/football__football_wHZt1eY3A9s_1080p.mp4
    1855b74edf86166cb23348f5b4da8a4a  data/footage_corpus/football__giants_jets_format96_1080p.mp4

Same md5. So `data/footage_corpus` holds 60 distinct clips, not 61, and the
football 1080p denominator is 1, not 2. `scripts/platformkit/tracking/
footage_census.py` (the G01 tool) dedupes and quarantines by name and content
class, never by content hash, so a re-download under a second name is counted
twice in every corpus denominator that cites it.

Scale of the blind spot: this was found by noticing two rows with identical
`frames` and `bytes` in `pod_corpus_census.json`; no other pair in the 61 rows
matches on both, so the measured duplicate count is exactly 1 pair today. The
gap is that nothing prevents the next one.

## Achievable limit

One md5 (or size+frames) pass in `footage_census.py` that flags exact
duplicates. 6.6 GB hashes in a couple of minutes on the pod; the ceiling is
exact duplicates only -- a re-encode of the same broadcast at a different
bitrate will not hash-match and still needs the name/content class rules.
