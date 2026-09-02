# Soccer S1 blind adjudication, pooled n=100 -- VERDICT: AMBIGUOUS

Date: 2026-09-01
Lane: T2c-SOCCER-LABEL (blind labeler)
Gate: pre-registered in `docs/research/organization-sprint/TRACKING_RESEARCH_DIGEST_2026-09-01.md`, step S1.

## Verdict

**AMBIGUOUS.** The pooled manual count falls in neither pre-registered branch.

| Pre-registered branch | Condition | Observed (n=100) | Met? |
|---|---|---|---|
| (a) DETECTOR-BOUND | manual median >= 14 AND manual pct>=14 >= 0.85 | median 13.0, pct 0.490 | NO |
| (b) CAMERA-BOUND | manual median < 14 AND manual pct>=14 <= 0.30 | median 13.0 (<14) but pct 0.490 | NO |
| (c) AMBIGUOUS | manual pct>=14 in 0.30-0.85 | pct 0.490 | **YES** |

The extension to n=100 was itself the prereg's remedy for the first ambiguous read.
It did not resolve it. Per the gate clause, verbatim: *"if it is still ambiguous
soccer stays at S0 and no packet is written this cycle."*

## Consequence (per the prereg, not a new decision)

1. **Soccer stays at S0.** No stage promotion on this evidence.
2. **`docs/research/soccer_coverage_ceiling_packet.md` is NOT written.** S6 states the
   packet ships only if S1 lands in the camera-bound branch; S6's own gate repeats
   that "a packet ... written on the AMBIGUOUS branch does not ship."
3. **No detector-repair route is licensed either** -- that route is the DETECTOR-BOUND
   consequence, which also did not fire. (The association.py Hungarian-assigner
   adoption may still be worth doing on its own merits; it just is not licensed
   *by this measurement*.)
4. **S7 budget stays unspent.** The $1.1-1.7k labelled pilot needs S1 detector-bound or
   ambiguous PLUS a failed soccer synthcal queue in S4; the second condition is not met.
5. No threshold moved. The 14-player minimum and the 0.85 coverage gate in
   `scripts/platformkit/tracking_harness.py` were not touched.

## Pooled numbers (n=100, 3 clips)

| | n | manual median | manual mean | manual pct>=14 | detector median | detector mean | detector pct>=14 | paired mean delta (manual - detector) |
|---|---|---|---|---|---|---|---|---|
| **POOLED** | 100 | 13.0 | 12.15 | **0.490** | 14.5 | 13.38 | 0.550 | **-1.23** |

Paired median delta: -1.0.

## Subsets, reported separately

| subset | n | manual median | manual mean | manual pct>=14 | detector median | detector pct>=14 | paired mean delta |
|---|---|---|---|---|---|---|---|
| n=36 (original, S1_0001-S1_0036) | 36 | 14.0 | 12.86 | 0.583 | 14.5 | 0.583 | -0.72 |
| n=64 (extension, S1_0037-S1_0100) | 64 | 13.0 | 11.75 | 0.438 | 14.5 | 0.531 | -1.52 |

The extension is *slightly sparser* than the original 36, but both subsets land in the
same ambiguous band (0.438 and 0.583 are both inside 0.30-0.85). Pooling did not move
the read; it confirmed it.

## Per clip (pooled across both subsets)

| clip | n | manual median | manual mean | manual pct>=14 | detector median | detector pct>=14 | paired mean delta |
|---|---|---|---|---|---|---|---|
| soccer_AgspyOj5BPk | 34 | 13.5 | 11.97 | 0.500 | 15.0 | 0.529 | -1.79 |
| soccer_DdnvC6-PGYY | 33 | 11.0 | 10.24 | 0.303 | 12.0 | 0.333 | -0.55 |
| soccer_kSgNjoaqCpI_1080p | 33 | 15.0 | 14.24 | 0.667 | 16.0 | 0.788 | -1.33 |

No clip on its own reaches either branch. The KOR-GER clip (DdnvC6-PGYY) comes closest
to camera-bound at pct 0.303, which is *just outside* the <=0.30 threshold -- a
one-frame difference. That near-miss is recorded, not acted on: the gate is pooled,
and a single clip is not the pre-registered unit.

## The finding that matters most: the detector is NOT under-counting

The prereg named the biggest risk as "filing an impossibility packet on a number that
measures OUR DETECTOR, not the camera" -- i.e. the fear that the camera shows 16 and our
detector finds 11. **The measurement falsifies that direction.** The paired mean delta is
**negative** (-1.23): across 100 frames the detector reports *more* bodies than a human
counts, not fewer. 10 frames have detector >= 14 while manual < 14; only 4 have the
reverse. Whatever is wrong with the soccer coverage figure, systematic under-detection of
distant players is not the dominant term on this corpus.

The likely mechanism for the over-count is that the extension's sealed column is
`raw_boxes` -- person boxes, not de-duplicated player tracks -- so referees, assistants,
4th officials, medics, orange-bib staff, stewards, photographers and suited coaches all
land in the detector number while the manual protocol explicitly excludes them. This is a
*definition* gap, not a recall gap, and it means the paired delta should not be read as a
detector quality score. It does not change the verdict: the verdict branch is decided by
the manual median and manual pct>=14 alone, and the paired-delta clause only binds inside
the camera-bound branch, which did not fire.

Second caveat, stated because it is a real asymmetry: the n=36 subset's detector column is
`detector_observed_distinct_player_count` while the n=64 subset's is `raw_boxes`. The two
subsets' detector numbers are therefore not strictly the same statistic. Manual counts --
the side the gate is decided on -- were produced under one identical protocol throughout.

## Five example frames each way

**Manual count HIGH (the camera does sometimes hold a full-ish picture):**

| frame | clip | manual | detector |
|---|---|---|---|
| S1_0016 | soccer_DdnvC6-PGYY | 20 | 18 |
| S1_0044 | soccer_AgspyOj5BPk | 20 | 20 |
| S1_0009 | soccer_AgspyOj5BPk | 19 | 22 |
| S1_0022 | soccer_DdnvC6-PGYY | 19 | 17 |
| S1_0027 | soccer_kSgNjoaqCpI_1080p | 19 | 18 |

**Manual count LOW (the broadcast cut, not the algorithm):**

| frame | clip | manual | detector | what the frame is |
|---|---|---|---|---|
| S1_0002 | soccer_AgspyOj5BPk | 1 | 1 | single-player close-up |
| S1_0042 | soccer_AgspyOj5BPk | 1 | 1 | single-player close-up |
| S1_0043 | soccer_AgspyOj5BPk | 1 | 1 | single-player portrait |
| S1_0087 | soccer_kSgNjoaqCpI_1080p | 1 | 1 | grounded player, face-filling zoom |
| S1_0004 | soccer_AgspyOj5BPk | 2 | 5 | tight duel |

The low tail is dominated by broadcast close-ups and replay-style zooms, where the manual
and detector counts agree closely. That is the honest shape of the corpus: it is not one
camera at one focal length, it is a directed broadcast that cuts between wide play and
close-ups, and the pooled pct>=14 is partly a statistic about editing.

**Largest positive deltas (manual > detector, i.e. detector missed bodies):**
S1_0018 (+11, manual 16 / detector 5), S1_0075 (+7, 12/5), S1_0011 (+3, 13/10),
S1_0010 (+2, 14/12), S1_0016 (+2, 20/18). S1_0075 is shot through the goal net, which is
a plausible mechanism for real detector loss.

**Largest negative deltas (detector > manual, i.e. detector counted non-players or
duplicates):** S1_0053 (-9, 16/25), S1_0070 (-7, 5/12), S1_0050 (-7, 12/19),
S1_0097 (-6, 17/23), S1_0048 (-5, 16/21). S1_0097 is a stoppage with staff on the
touchline; S1_0070 is an extreme close-up where duplicate boxes on partial bodies are
the likely cause.

## Method and blinding audit trail

- The 64 extension labels were produced from the frame JPEGs alone, using
  `crops_2x/` only to split dense clusters, per `ext_2026-09-01/labeling_protocol_ext.md`.
- Counting rule (verbatim from the protocol): distinct human players, outfield plus
  goalkeepers, partial bodies at the frame edge included when identifiable; referees,
  assistants, fourth official, coaches, ball kids and photographers excluded.
- Every frame got a per-frame reasoning string recording the team split and which
  non-player figures were excluded. No frame was skipped; no frame was unlabelable.
- **Blinding held.** The sealed files were opened only AFTER the labels were committed:
  - `59722fbf5` -- "soccer S1 ext: 64 blind labels (sealed counts unopened)"
  - the sealed CSVs and the original labels were first read after that commit.
  - `ext_2026-09-01/detector_counts_separate_ext.csv` sha256 verified at unseal time as
    `c87158551d03fc1c5e6c852baeed0bb55ba639ebbac87573c4c0646d88882c83`, matching
    `manifest_ext_2026-09-01.json` -- the sealed file was not modified between sealing
    and unsealing.

## Artifacts

- `scripts/platformkit/a1_artifacts/soccer_s1/ext_2026-09-01/blind_labels_ext_2026-09-01.csv` (64 rows, this lane)
- `scripts/platformkit/a1_artifacts/soccer_s1/blind_labels_2026-09-01.csv` (36 rows, prior)
- `scripts/platformkit/a1_artifacts/soccer_s1/ext_2026-09-01/detector_counts_separate_ext.csv` (sealed)
- `scripts/platformkit/a1_artifacts/soccer_s1/detector_counts_separate.csv` (sealed, prior)
- `scripts/platformkit/a1_artifacts/soccer_s1/ext_2026-09-01/manifest_ext_2026-09-01.json`

An honest AMBIGUOUS is the successful outcome of this instrument. It bought a real thing:
the packet that would have been the fast, satisfying result is now formally not
licensed, and the under-detection hypothesis that would have made that packet a
fabrication has been measured and pointed the other way.
