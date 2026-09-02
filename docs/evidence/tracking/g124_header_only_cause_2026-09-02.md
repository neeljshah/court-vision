# G124 Header-Only Cause Diagnosis

**Verdict: ACCEPT WITH CORRECTIONS.** This is a read-only cause investigation
of the adapter-registry `thin` population described by G100 and G105. It
follows [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), including A7 and the
section B self-check. No job was rerun; no daemon, threshold, coordinate
contract, ledger row, source, verdict, or pod process was changed.

## Preregistered vocabulary and selection

The vocabulary was written before opening any selected CSV, log, or footage
frame in [g124_headers/protocol.md](g124_headers/protocol.md). It includes
`non_game_footage`, `decode_failure_after_open`,
`adapter_exception_after_header`, `detector_no_observations_on_usable_game`,
`source_corrupt_or_truncated`,
`source_missing_or_historically_unattributable`, and
`insufficient_retained_evidence`.

At the frozen read, 157 of the historical adapter thin outcomes still had a
readable canonical CSV. Within every sport the ledger line was the only time
proxy; content, rows, logs, source state, and image appearance were excluded
from selection. The protocol's evenly spaced ranks selected 12 job outcomes:
three each from baseball and football, two each from KBO and MLB, and one each
from soccer and tennis. The two KBO selections refer to two separate historic
outcomes for the same current table path, leaving 11 distinct current paths.
To ensure the requested header-only mechanism was directly represented, the
three pre-existing G100 ordinal-third spot checks were additionally opened.
They add three distinct paths, for **15 opened historic thin outcomes and 14
distinct current CSV paths**, across six sports and the ledger's early, middle,
and late regions. Every case, its historical duration, current output state,
source presence and byte size, log tail, and cause label is retained in
[selected_cases.csv](g124_headers/selected_cases.csv).

## First correction: this population is not synonymous with header-only output

G100's historic baseline remains **158 adapter-path thin jobs, 145,702 ledger
seconds (40.47 estimated job-hours), and 0 confirmed recoverable**. But the
largest class cannot honestly be called 158 header-only jobs. Of the 157
currently readable historical thin records, 85 recorded zero rows, four
recorded 1--4 rows, and 68 recorded 5--499 rows; none recorded 500 or more.
All 157 retain the legacy ledger shape, without the additive `adjudicated`
field. The pre-G15 daemon source classified a non-timeout job as `thin` when
its output had fewer than `MIN_TRACKING_ROWS = 500`; the later G15 change
removed that row-count definition. The 415-row tennis outcome in the selected
set confirms the point directly: its historic and current row counts match,
yet its old ledger status is `thin`.

Therefore the 158-row bucket combines actual zero-row/header-only attempts
with nonempty legacy low-row outputs. A current table is also mutable after a
re-track, so a current nonempty table cannot silently be treated as the
historic output. This correction narrows rather than inflates the claim.

## Opened-output cause distribution

| Cause class | Outcomes / 15 | Share |
|---|---:|---:|
| Source missing or historic output unattributable | 13 | 86.67% |
| Non-game footage | 1 | 6.67% |
| Decode failure after open | 1 | 6.67% |
| Every other preregistered class | 0 | 0.00% |

The additive source is [cause_distribution.csv](g124_headers/cause_distribution.csv).
The 13 are not a claim that the input was bad or the adapter was good: their
original source bytes are absent, or their current table was later overwritten
and cannot establish what the historic job did. One of those tails includes a
`ModuleNotFoundError` for `domains.baseball.tracking.field_mask`, but that
import happens before adapter output creation and the original source is gone;
it is not relabelled as an after-header adapter failure.

The non-game control is `mlb_FGtFanovws4`: its current CSV is 64 bytes and has
only a header, its 23,277,425-byte source remains present, and I inspected its
three G113 interior frames myself. All show an MLB RBI World Series title card,
not game footage; the frame paths are retained in the case table. The
decode-failure control is `tennis_10`: its current CSV is an 87-byte header,
the 97,325,005-byte source is retained, and the logged
`FileNotFoundError: Could not open video` names the failure before usable-frame
processing. Its G113 frames show actual Wimbledon match coverage, so this is
not attributed to bad footage. The selected `tennis_nyYk2nPZAwY` source is
also retained (68,996,181 bytes); I inspected three spread G113 frames and
they show a Wimbledon match, not worthless input.

## G117 non-game confound

The G117-named set was reconstructed from the 12 quarantine sidecars whose
reason is `human_confirmed_predominantly_studio_or_statistics_programming_g117`.
Using every current adapter-path ledger outcome for those exact clip IDs gives
**0/15 thin (0.00%)**, versus **158/354 (44.63%)** for every other adapter
clip ID. The denominators, status counts, and unique-clip counts are retained
in [g117_thin_rate.csv](g124_headers/g117_thin_rate.csv).

Thus the obvious acquisition confound is not the explanation for this historic
thin bucket: the explicitly quarantined studio clips have no thin outcomes.
This is descriptive job-outcome comparison, not a causal estimate; the G117
clips may have been quarantined after their successful tracked runs.

## Worthless input versus adapter failure

Only three of the 15 opened outcomes retain a matching input. Among that
denominator, **1/3 is confirmed worthless non-game footage**
(`mlb_FGtFanovws4`); **1/3 is a logged decoder-open failure on visually usable
game footage** (`tennis_10`); and **1/3 is usable game footage with a nonempty
415-row legacy-thin output** (`tennis_nyYk2nPZAwY`). The other **12/15 lack a
matching historic source or a non-mutable historic output**, so they are not
included in either the worthless-input or usable-input adapter-failure
numerator. This is the needed separation, with explicit denominators.

## Recommendation

Do not change the daemon in this row. A future human-reviewed guard should
write an immutable per-attempt sidecar before completion cleanup containing the
input path, byte size and checksum, decoder-open result, decoded-frame count,
adapter exception (if any), output path, row count, and a stable attempt ID;
then it should report a nonzero-row/sidecar mismatch as a loud failed attempt
rather than a silent table. This is cheaper and more diagnostic than a
row-count threshold: it preserves the difference between bad footage, decoder
failure, adapter failure, and a legitimate zero-detection run without changing
the coordinate contract or re-running historical footage.

## NOT VERIFIED

- The original source bytes and per-attempt output files are absent for 12/15
  opened outcomes, so their physical cause cannot be recovered from their
  mutable current tables.
- The G117 comparison is a current-ledger association; it does not establish
  that the quarantine caused the zero thin rate.
- No selected case supports a `detector_no_observations_on_usable_game` or
  `source_corrupt_or_truncated` attribution.
- No proposed guard was implemented, tested, deployed, or copied to the pod.

## VERIFIER_CONTRACT self-check

### A

- **A1:** No code was added, so no new per-file test exists to rerun.
- **A2:** The 15 case labels sum to the cause table, and the thin-rate table
  recomputes to 0/15 and 158/354 from its retained counts.
- **A3:** The 12 primary rows are evenly rank-selected within sport over ledger
  order, not a head slice; G100's three pre-existing controls span its ordinal
  thirds.
- **A4:** This memo reports both 15 historic job outcomes and 14 distinct
  current CSV paths; the duplicate KBO path is named, not hidden.
- **A5:** Evidence only; no schema field, reader, or production file changed.
- **A6:** This lane makes an explicit-path evidence commit only. Archive
  landing and master-side ledger/register work remain verifier responsibilities.
- **A7:** Before commit/report, every memo-named repository evidence path is
  checked to exist, including the G113 eye-check frames.

### B

- **B1:** Clear. Every selected outcome remains in the retained case table;
  missing sources are a named result, not an exclusion.
- **B2--B6:** Clear. No schema, gate, claim/retry path, deployment, module,
  import, or test changed.
- **B7:** Clear. The primary selection is time-spread within sport and the
  controls came from G100's ordinal thirds.
- **B8--B9:** Clear. This is direct artifact inspection by distinct ledger
  outcome, not a fitted metric or recycled unit.
- **B10:** Clear. No timeout, harness bar, threshold, gate, verdict, or
  coordinate-contract value moved.
