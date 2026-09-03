# G185 coordinate-contract wall

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` (A2, A3, A7, B1-B10, Q8). Diagnosis only: no coordinate contract, adapter default, threshold, gate, daemon, keeper, production source, or verdict changed.

## Q8 premise first

The supplied premise was a 34-row ledger with 24 declared-`image_px` failures. Before analysis, the current local `data/tracking/track_daemon_ledger.jsonl` was sealed at SHA-256 `02f648eee5b92185e487e6e9e49b9f6d859d5815f8349bf1d4d4fb4f97ca3dd7`. It has 300 records and 60 diagnostics literally saying `rows declare coordinate_space image_px`: 32 baseball-family, 17 football, 11 soccer. It also has three `rows omit coordinate_space` diagnostics. The first 34 records have zero declared-`image_px` rows, so the asserted historical 24 cannot be reconstructed from this mutable ledger.

This is a Q8 **FALSIFIED premise**, not a silent scope change. The constructive population is all 60 current declared-`image_px` rows. The three omitted-coordinate records and other 237 records are excluded because they do not declare the specific coordinate space under diagnosis; the source hash and literal filter make that repeatable.

## 1. Path selection for every current declared-image row

The daemon normalizes `npb`, `kbo`, and `mlb` to `baseball` in `scripts/platformkit/track_daemon.py:72-73`:

```python
SPORT_ADAPTER = {"tennis": "tennis", "soccer": "soccer", "npb": "baseball",
                 "kbo": "baseball", "mlb": "baseball", "baseball": "baseball"}
```

The daemon child then takes this fixed configuration in `scripts/platformkit/adapter_run.py:47,102-105`:

```python
IMAGE_SPACE = {"baseball", "football", "soccer"}
if sport in IMAGE_SPACE:
    options["image_space"] = True
```

No row carries a per-run override. Its actual `image_px` declaration independently establishes that this branch emitted its file.

| Adapter sport | Exhaustive current rows (ledger offset: game id [raw sport], emitted rows) | Default-selected branch and cause |
|---|---|---|
| baseball (32) | 223 `kbo_hl_xGuMseB8` [kbo] 9,950; 225 `npb_01` [baseball] 36,684; 226 `npb_02` [baseball] 43,025; 227 `npb_04` [baseball] 32,744; 228 `npb_09` [baseball] 41,348; 231 `mlb_A5AkcaXA2fk` [mlb] 15,889; 233 `mlb_nLoG6gvC-Nk` [mlb] 23,345; 234 `mlb_gDv5xF2AA2E` [mlb] 49,475; 242 `npb_10` [baseball] 43,625; 247 `kbo_QrO9d2csjsg` [kbo] 11,400; 248 `kbo_cyRosVcG7zI` [kbo] 21,208; 249 `mlb_6SEjheAAtcs` [mlb] 28,798; 251 `mlb_Z5u9T4b1qxk` [mlb] 31,016; 252 `mlb_dSX2ujmGBgg` [mlb] 18,128; 253 `npb_Arpw32zVTuc` [npb] 30,965; 254 `npb_RIwbEjh-zTs` [npb] 36,367; 255 `npb_aEpT4HU_ilg` [npb] 34,836; 256 `kbo_10` [baseball] 82,967; 269 `npb_YI146E0gNnA` [npb] 42,827; 272 `mlb_5WpMyA0Xj6Y` [mlb] 33,247; 273 `kbo_eeH8RMtS24U` [kbo] 13,907; 274 `kbo_UuivYJVZYtY` [kbo] 14,323; 276 `kbo_fy6pf01O2gE` [kbo] 19,500; 280 `kbo_OJfFKo9Dq2A` [kbo] 44,485; 281 `mlb_MUbgCYez-LY` [mlb] 49,586; 283 `npb_2iFIuWxu6HI` [npb] 41,591; 284 `mlb_VxQlqZhLJso` [mlb] 41,756; 294 `kbo_1IwwT5ysVSY` [kbo] 30,119; 295 `kbo_64cdlFkEuCc` [kbo] 33,942; 296 `kbo_FA3W5xMyYRY` [kbo] 41,028; 297 `kbo_vPUqzscNQIk` [kbo] 28,965; 298 `mlb_Fu9kVrQRg0M` [mlb] 36,656 | `image_space=True`. `domains/baseball/tracking/adapter.py:210-224` emits `coordinate_space: "image_px"` and `calibration: "none"` irrespective of geometry. The later `if self._geometry is not None` records metadata/counts but appends no calibrated coordinate row. Thus the claimed separate calibrated baseball coordinate-*emit* path is false. |
| football (17) | 222 `football_lsYEcWf4Zbg` 16,305; 229 `football_fh9CTJ0-PpQ` 58,652; 230 `football_owXX5PI64gU` 9,635; 238 `football_P_TdW-vpywo` 12,578; 239 `football_J9WamaxtwdQ` 89,052; 240 `football_6oUm30M1HZ8` 23,081; 241 `football_tKc73Meexzo` 68,965; 257 `football_TqKwnvxbKDw` 67,082; 261 `football_qzjIo3_M_3U` 9,591; 262 `football_aL_ZQEaQ_LY` 9,575; 264 `football__Bsqeb795J0` 59,321; 275 `football_kXfNJsCLLIA` 96,562; 277 `football_bj9lY3FEDw0` 43,005; 290 `football_B-aAcjvtu9I` 66,722; 291 `football_ZHJWGNGE0Cg` 31,467; 292 `football_jK1AuQzymVE` 81,441; 293 `football_tEpTKZKk7ks` 61,273 | `image_space=True`. `domains/football/tracking/adapter.py:97-100` emits pixel detections and `continue`s before line 106's `_stable_homography`; only that later path can append `court_feet` at line 116. The football contradiction is fully explained: the calibrated branch exists but the daemon did not take it. |
| soccer (11) | 217 `soccer_6dIn3fUfI6U` 96,168; 232 `soccer_Cn26lFZ0_jI` 64,359; 235 `soccer_JIQnnYy7qYk` 88,867; 236 `soccer_8_DRy2i5-hs` 75,954; 237 `soccer_HxBqMbI5kqQ` 91,744; 258 `soccer_GF-WteOINCc` 80,980; 265 `soccer_QIpZ1pad73w` 110,774; 266 `soccer_ci4vyd6PsNg` 102,639; 282 `soccer_7fOG8j_ncWY` 68,211; 287 `soccer_Pbyn08kfhXY` 81,222; 299 `soccer_A9ad17VZvs8` 6,126 | `image_space=True`. `domains/soccer/tracking/adapter.py:112-115` emits and `continue`s before calibration-keyframes and `_stable_homography` at lines 124-128; line 140 declares `image_px`. Thus daemon image-mode rows never exercised soccer calibration. |

The uncalibrated preservation route is deliberate for all 60 current declared rows. It preserves observations; it does not make them scorable under the coordinate contract.

## 2. Calibration measurement on real pod footage

The additive harness `scripts/platformkit/tracking/g185_coordinate_contract_wall.py` was sent only to an inline pod process; no source file was copied to the pod checkout. Each source was decoded sequentially, but the unmodified calibration method was called only at 120 inclusive `numpy.linspace` positions. Per-frame records are [`baseball.json`](g185_coordinate_contract_wall/baseball.json), [`soccer.json`](g185_coordinate_contract_wall/soccer.json), and [`football.json`](g185_coordinate_contract_wall/football.json). Every record retains source index, attempt, candidate, final result, and detail.

The **eligible denominator for every non-tennis row is 120 adapter-evaluated frames**. It is neither the metadata decoded-frame count nor emitted rows; metadata count solely defines the even-sampling universe.

| Sport | Pod source at run start | First five ... last five source indices | Final calibration success / eligible denominator | Candidate / eligible denominator | Rate | Tennis reference |
|---|---|---|---:|---:|---:|---:|
| baseball | `footage_corpus/baseball__npb_02.mp4`, 411,191 metadata frames | 0, 3,455, 6,910, 10,366, 13,821 ... 397,368, 400,823, 404,279, 407,734, 411,190 | 0 / 120 adapter-evaluated | N/A: pitch geometry is the calibration method | 0.000% | 2,660 / 28,773 decoded/evaluated corner calls = 9.245% |
| soccer | `footage_bridge/soccer__soccer_dnR5C6WLJI4.mp4`, 250,200 metadata frames | 0, 2,102, 4,205, 6,307, 8,410 ... 241,788, 243,891, 245,993, 248,096, 250,199 | 0 / 120 adapter-evaluated | 0 / 120 adapter-evaluated (`_validated_homography`) | 0.000% | 2,660 / 28,773 decoded/evaluated corner calls = 9.245% |
| football | `footage_corpus/football__football_Z8Ezd95NnjM.mp4`, 288,230 metadata frames | 0, 2,422, 4,844, 7,266, 9,688 ... 278,540, 280,962, 283,384, 285,806, 288,229 | 0 / 120 adapter-evaluated | 0 / 120 adapter-evaluated (`homography_from_yard_lines`) | 0.000% | 2,660 / 28,773 decoded/evaluated corner calls = 9.245% |

The soccer staging path was moved by the live pipeline after the measurement opened it. The retained descriptor completed with empty stderr; that mutable pathname is run-start provenance, not a durable-source claim. Tennis is G182's exhaustive reference, not an estimate recomputed here; it is not statistically interchangeable with these bounded samples.

## 3. Even-sampled eye check: modal baseball failure

All 120 baseball evaluations failed. Inclusive positions `0, 29, 59, 89, 119` over that complete failure decision set yield source frames `0, 100205, 203867, 307528, 411190`, not a head slice.

| Frame | Render | Human observation |
|---:|---|---|
| 0 | [render](g185_coordinate_contract_wall/renders/frame_000000.jpg) | Wide but oblique/base-side field view, not the required center-field mound-and-infield-dirt geometry. |
| 100205 | [render](g185_coordinate_contract_wall/renders/frame_100205.jpg) | Tight player/coach close-up; no usable mound or infield geometry. |
| 203867 | [render](g185_coordinate_contract_wall/renders/frame_203867.jpg) | Oblique field view with large score graphic; not the required center-field pitch geometry. |
| 307528 | [render](g185_coordinate_contract_wall/renders/frame_307528.jpg) | Tight player crop; no usable mound or infield geometry. |
| 411190 | [render](g185_coordinate_contract_wall/renders/frame_411190.jpg) | Crowd/scoreboard view; no usable mound or infield geometry. |

None visibly carries the particular center-field mound, grass, and infield-dirt configuration requested by `detect_pitch_geometry`. This five-frame check is not a label of all failures and does not establish a footage-only cause.

## Same-or-different verdict

**Different walls with one shared preservation-path symptom.** `IMAGE_SPACE` is a common and deliberate selector, but calibration does not have one demonstrated common cause. Baseball has 120/120 no pitch geometry and the eye check cannot separate footage from detector behavior. Soccer has 120/120 no validated candidate; this does not separate raw-landmark absence from held-out validation rejection. Football's `homography_from_yard_lines` explicitly fails closed when independent physical scale is unavailable. The common 0.000% sample rate is therefore not evidence of a common cause.

The hypothesis is partly falsified: all three daemon paths are deliberate preservation paths, football's contradiction is resolved, and baseball lacks the asserted calibrated coordinate-emission path.

## Reproduction and self-check

- **A2:** Recounting each JSON yields 120 unique frame records and 0 final successes; each rate recomputes to 0.000%. The sealed ledger filter yields 60 declared-`image_px` rows.
- **A3/B7:** All measurement positions and all five render positions are inclusive even samples of their complete decision sets.
- **A7:** This memo, the three JSON records, five renders, harness, and focused test exist before commit.
- **B1:** Clear: no outcome-based removal; denominator is every adapter-evaluated sample frame.
- **B2-B6:** Clear: no schema, reader, fall-through, claim, queue, deployment, move, or retirement changed.
- **B8-B9:** Clear: direct observations of unique source frames, not a fitted residual or recycled unit.
- **B10/Q3:** Clear: no bar, threshold, gate, contract, adapter default, or verdict moved.
- **Q8:** Clear: premise measured first and falsified.

## NOT VERIFIED

- The absent historical 34-row/24-row snapshot's membership or order.
- Full-clip calibration rates; these are bounded 120-frame even samples.
- Whether baseball's zero is footage, detector, or both; whether soccer fails before or during held-out validation.
- Alternative football scale evidence or any downstream quality consequence.
- Any relaxation of the coordinate contract or conversion of preserved `image_px` rows into scorable coordinates.

## Orchestrator verification at landing, and one correction to the Q8 section

**Verified by recomputation in master, independent of the lane's harness:** each
of the three artifacts holds 120 frame records over 120 unique frames, 120
calibration attempts, **0 successes and 0 candidates**, so every rate recomputes
to 0.000 pct on a stated `adapter_evaluated_frames` denominator of 120. The
sampling positions run from frame 0 to the final metadata frame in all three
sports (baseball 0..411,190 of 411,191; football 0..288,229; soccer 0..250,199),
so none is a head slice. `test_g185_coordinate_contract_wall.py` passes in master.
The `IMAGE_SPACE = {"baseball", "football", "soccer"}` selector is confirmed at
`scripts/platformkit/adapter_run.py:47`, applied at `:102-105`, and its own
comment states the rule: "Add a sport here only once its adapter supports
image_space=True AND its calibration failure is MEASURED, not assumed."

**The premise was not falsified -- it was a different ledger.** The memo reports
the orchestrator's "24 of 34" as unreconstructible, and that is correct about the
file the lane read, but the two numbers come from different sources and both
reproduce:

| | rows | declared `image_px` | field | by sport |
|---|---:|---:|---|---|
| LOCAL `data/tracking/...` (the lane's source) | 300 | **60** | `failures` | soccer 11, football 17, baseball-family 32 |
| POD `/workspace/.../data/tracking/...` (the orchestrator's source) | 38 | **27** | `failure_heads` | baseball 19, soccer 3, football 3, mlb 2 |

Both were recomputed at landing. The pod figure was "24 of 34" when the spec was
written and has since grown with the daemon; the pod ledger still shows **0 rows
passing** (29 `false`, 9 `null`). The lane was right to state its own population
explicitly and to refuse to invent the orchestrator's; "FALSIFIED" overstates it,
and the fix is that **a spec must name the ledger it means, and the field, not
just a count.** That omission is the orchestrator's.

## Why this row matters more than its rate table

The headline is not the 0.000 pct. It is that **all three sports take the
uncalibrated path by configuration, not by failure**: `adapter_run.py` sets
`image_space=True` for baseball, football and soccer unconditionally, and each
adapter then emits pixel rows and `continue`s before its calibration branch. So
the coordinate-contract rejections are a deliberate preservation route working as
designed, not a bug to fix.

Two specific corrections the lane earned:

- **Baseball has no calibrated coordinate-emit path at all.** Its
  `if self._geometry is not None` branch records metadata and counts but appends
  no calibrated coordinate row. The G185 spec asserted such a path existed; that
  assertion is withdrawn.
- **The football contradiction is resolved.** Its adapter does emit `court_feet`
  at line 116, but the daemon `continue`s at lines 97-100 before reaching it. The
  calibrated branch exists and was never taken.

And the lane declined the tempting synthesis: three sports at 0.000 pct is **not**
evidence of one shared wall. It reported "different walls with one shared
preservation-path symptom" and named why each is separate. That refusal is the
right call and is the part of this row most worth keeping.
