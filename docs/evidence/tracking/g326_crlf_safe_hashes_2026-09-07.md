VERDICT: PARTIAL -- 1 of 6 committed-comparison text-seal sites is converted (g298_audit.py:33, in 4de3f41b9); 0 further sites are convertible because 11 of the 16 sealed (path, expected) pairs equal the RAW digest; 0 committed hashes changed.
# G326 -- CRLF-safe audit hashes (2026-09-07, fix 1b)
Spec `specs/G326_spec.md` (master dce917b36). Prereg seal `a2a5fbc7a3e4f7f6...977fe9ad`; SUPPLEMENT
`g326_prereg_supplement_2026-09-07.md` seal `beae43fb72cbfb8f...88afd87e`, sealed ALONE before the re-sweep.
a17. LOCAL, CPU only. No pod, no GPU, no footage, no `data/` read. Census 39.7 s wall.
## Fix 1b -- the four verifier corrections
1. The "exhaustive" table was a SAME-LINE grep; replaced by an AST walk, `g326_hash_sink_census.py` (stdlib
   `ast`, 300 LOC) -> `g326_artifact/hash_sinks.csv`. It finds all three sinks the verifier named as missing --
   standing_prereg.py:241 and corpus_cache.py:42 FILE_WHOLE, ledger_backup.py:37 FILE_STREAM -- each pinned by
   a test that also asserts a same-line grep cannot reach them.
2. `99 ... (denominator)` was 99 same-line matches and is NOT a denominator. Class table below.
3. `4 LF, 6 RAW of 10 pairs` was wrong arithmetic: 5 LF / 8 RAW over 13 pairs REPRODUCES exactly, and the walk
   adds 3 more pairs (g231:177), giving 5/16 LF and 11/16 RAW.
4. Citations corrected: the converted site is `g298_audit.py:33`, the raw-byte one `:31` (were :29 and :28).
## PREMISE -- TRUE (re-run): `git show dce917b36:.../g298_audit.py` run on this checkout raises AssertionError at
source line 29 before any arithmetic; `python -m scripts.platformkit.tracking.g298_audit` here prints PASS.
## CLASS TABLE -- AST census, exhaustive over 3462 .py under scripts/platformkit/** (0 parse errors)
    513 rows = 480 data-entry sinks + 33 empty constructors (their data enters at the paired .update row)
    237 TAINTED      a call to a hash helper resolved through the calling file's own imports
     75 FILE_WHOLE   read_bytes() / open(...,"rb").read()
     29 FILE_STREAM  chunked: .update() inside a f.read(n) or iter(lambda: f.read(n), b"") loop
    139 MEMORY       encoded text, json.dumps, git cat-file, an in-run slice
    341 file-reading; verdicts 7 DEFECT, 14 REVIEW_UNKNOWN, 18 ALREADY_LF, 31 BINARY, 271 RECORD_ONLY
## RECONCILIATION with the verifier's >= 154 (122 direct/tainted, 32 streamed) -- NOT forced to agree
That figure is a stated lower bound and the census exceeds it; the gap is a counting boundary, not a disagreement. The census counts every hash-helper CALL SITE (237) as its own sink, since that is where a digest meets a committed value; crediting each helper once at its definition instead gives 116 definitions in 102 files against 104 hashlib-level file sinks (75+29).
Streamed is 29 here against 32 there, the difference being whether a chunk loop's paired empty constructor is a second sink; all 17 non-Name `.update()` receivers in the tree were checked and are dict/set/attrs updates, so no streamed sink is missed through that shape.
## HASH DELTA -- 16 unique (path, expected) pairs, both digests recomputed on this checkout
    site                                 sealed path(s)                       n  committed ==  owner
    g298_audit.py:33                     g298_artifact/{A,A_repeat,B,C}.csv   4  LF            CONVERTED 4de3f41b9
    g298_audit.py:31                     g285b_artifact/located_feet.csv      1  RAW           G285b
    golden_loader.py:67                  golden/game_states.json + sidecar    1  RAW           S40b/S51
    s293_tail_metric_replay.py:57        4 .py pinned in FIXED                4  RAW 4/4       S293
    g247_projected_quad_validity.py:149  3 .py in EXPECTED_SOURCE_SHA256      3  RAW 2, LF 1   G247 (MIXED)
    g231_out_of_bounds_structure.py:177  3 tennis *_tracking_data.csv         3  RAW 3/3       G231 (NEW)
Totals 5/16 LF, 11/16 RAW, 0/16 neither. **0 committed hashes changed**, none edited. The verifier's 13 pairs are rows 1-5 and reproduce there as 5 LF + 8 RAW.
## CONVERTED THIS PASS -- none; and the UNTOUCHED RAW-SEALED list
No unconverted site's committed constant equals its LF digest, so the conversion set is empty; the one LF site was converted in 4de3f41b9 through the single shared helper `scripts/platformkit/hash_lf.py`.
Left raw-byte: g298_audit.py:31 (G285b), golden_loader.py:67 (S40b/S51), s293:57 (S293), g247:149 (G247), g231:177 (G231). Only g231 gains a source comment -- the census newly found it and nothing else recorded it; the other four are named here and in the prior memo, so their owners' modules stay untouched.
## CENSUS FALSE POSITIVES, resolved by hand (the walker is static, so it over-reports)
The 4 DEFECT false positives are ledger_backup.py:161, test_soccer_s1_ext_packet.py:34, g291:111 and g295:109. ledger_backup.py:161 compares against a manifest the tool itself wrote under `data/` at run time; test_soccer_s1_ext_packet.py:34 hashes a tmp_path file from the same run; g291:111 and g295:109 hash a `.jpg` render (BINARY), read as TEXT only because a `.json` order file is reachable from the same expression. corpus_cache.py:125,166,179 are NOT among the four -- they stay under REVIEW_UNKNOWN (same run-time manifest shape, resolved by hand on the next line).
13/14 REVIEW_UNKNOWN rows resolve the same way (runtime watermark, tmp fixture, same-run before/after identity, an in-memory dict, one `.mp4`); the 14th, g231:177, is the real new defect. g247:149 reads MEMORY, not DEFECT -- its bytes arrive base64-encoded from `g242._source_payload`, which the one-hop taint rule does not cross -- so its 3 pairs were resolved by hand.
## NOT VERIFIED
- That any seal, converted or not, is CORRECT. LF normalization makes a digest checkout-invariant; it says NOTHING about whether the artifact it seals is right.
- That `g298_audit` is re-executable on an LF checkout. It is NOT: line 31 would fail there. This row made it re-executable on a Windows CRLF clone only, and a module left unconverted because its committed seal is CRLF-derived stays un-re-executable on an LF checkout -- the sweep did not repair it.
- The 271 record-only and 139 in-memory sinks were classified from source, never executed; no run-time-built path was resolved (those stay UNKNOWN and are reported, not folded into a fine bucket). No video decoded, no tracking output read, no frames, no renders, no labels. NO EYE CHECK. No recall, precision, accuracy or registration claim is made or implied anywhere in this row.
- `g298_audit` still rewrites its committed `artifact_inventory.json` with absolute worktree paths, so direct execution dirties the tree: a second re-executability defect, independent of CRLF, still open.
## TESTS (per-file only, never a full pytest; each `-q -p no:cacheprovider --confcutdir=tests/platformkit`)
    tests/platformkit/test_g326_hash_sink_census.py 4 passed 0.15s | test_g326_crlf_safe_hashes.py 4 passed 1.83s
    tracking/test_g231_out_of_bounds_structure.py 1 passed 0.95s | tracking/test_g298_compare.py 5 passed 0.91s
    tests/platformkit/test_loc_rail_scope.py 1 passed 0.38s
## SHA-256 (LF-normalized)
    c7b5c8f9a35ef2f8e3a1898545512dd02a924958eccbead7cf007443be2ca652  scripts/platformkit/g326_hash_sink_census.py
    c6a72a15546416ecbf8b2152af224b2d0c6b99ed8049c482690ef7627903daa4  docs/evidence/tracking/g326_artifact/hash_sinks.csv
    df02b12b12c715d4de72f24334111f72458c9b53e7ed969a24d0a53a541bf509  tests/platformkit/test_g326_hash_sink_census.py
## Corrections applied at landing (verifier codex-sol, `G326_VERIFY_2026-09-07.md`:33-37)
- CORRECTION verify:33 applied to memo:17 -- file scope `3461` -> `3462` .py under `scripts/platformkit/**`. The
  verifier recounted the tree; 3461 was the candidate's figure and is wrong. The same number is corrected in the
  ledger row appended for this row. No other figure and no committed hash changes.
- CORRECTION verify:34 applied to memo:40 -- the four DEFECT false positives are now named explicitly
  (ledger_backup.py:161, test_soccer_s1_ext_packet.py:34, g291:111, g295:109) and corpus_cache.py:125,166,179 is
  kept under REVIEW_UNKNOWN rather than counted among them.
- NEW GAP verify:36 -- memo:15-16 SUMMARIZES the baseline traceback; it is not verbatim. The verifier reproduced
  all four traceback lines under `core.autocrlf=true` ending at source line 29, but its memo records only that
  fact, not the four lines, so no verbatim traceback could be carried here. The premise evidence in this row is a
  summary, not a transcript.
- NEW GAP verify:37 -- `tests/platformkit/test_g326_hash_sink_census.py`:28-77 pins three sites and the verdict
  vocabulary but NOT full artifact equality, so a stale `g326_artifact/hash_sinks.csv` could pass it. The verifier
  independently reproduced 513/513 at verification time; the test does not pin that for a later checkout.
