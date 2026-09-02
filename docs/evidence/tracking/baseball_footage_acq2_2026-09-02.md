# Baseball footage acquisition 2 - G12

Date: 2026-09-02. Lane: G12 MLB footage. This acquisition used the supplied
local cookie jar through `footage_bridge.download_local`, never displayed or
exported cookie material, and downloaded one bounded section at a time. All
sections explicitly used `*00:20:00-00:30:00`, beyond the first 600 seconds.
Each reached 1280x720 on the first cookie-backed HLS rung and is exactly about
600 seconds long.

## Sources and visual quality gate

The source channel for every entry was the official `MLB` YouTube channel.
No reaction stream, pregame show, or non-MLB source was selected. The manual
gate was declared before review: keep only at least 6 of 12 evenly spaced
frames that show a centerfield pitch view or another live field view. Each
contact sheet below was rendered from the local ten-minute section and viewed.

| game_id | source URL | park | day/night | section | field frames | CF pitch frames | decision/reason |
|---|---|---|---|---|---:|---:|---|
| `mlb_9HQ_mYBHO1s` | https://www.youtube.com/watch?v=9HQ_mYBHO1s | loanDepot park | night | `*00:20:00-00:30:00` | 4/12 | 3/12 | REJECT - close-up/dugout dominated |
| `mlb_ZIL6pX5RWs4` | https://www.youtube.com/watch?v=ZIL6pX5RWs4 | Truist Park | day | `*00:20:00-00:30:00` | 4/12 | 2/12 | REJECT - close-up and feature-graphic dominated |
| `mlb_RN21kmv7KiI` | https://www.youtube.com/watch?v=RN21kmv7KiI | Chase Field | day | `*00:20:00-00:30:00` | 4/12 | 3/12 | REJECT - close-up/crowd dominated |
| `mlb__jc2UrbEm8E` | https://www.youtube.com/watch?v=_jc2UrbEm8E | Rogers Centre | night | `*00:20:00-00:30:00` | 5/12 | 3/12 | REJECT - close-up dominated |
| `mlb_ptIBgr6U1Y8` | https://www.youtube.com/watch?v=ptIBgr6U1Y8 | Citizens Bank Park | day | `*00:20:00-00:30:00` | 8/12 | 6/12 | KEEP |
| `mlb__b2FM325c3M` | https://www.youtube.com/watch?v=-b2FM325c3M | Petco Park | day | `*00:20:00-00:30:00` | 5/12 | 3/12 | REJECT - crowd/dugout dominated |
| `mlb_g1FSeJz0voM` | https://www.youtube.com/watch?v=g1FSeJz0voM | Progressive Field | night | `*00:20:00-00:30:00` | 3/12 | 3/12 | REJECT - close-up dominated |
| `mlb_PPj97yvNGOo` | https://www.youtube.com/watch?v=PPj97yvNGOo | Minute Maid Park | night | `*00:20:00-00:30:00` | 7/12 | 5/12 | KEEP |

Day/night distribution is balanced: four daytime and four night-game
sections, each from a different park. The visual gate kept 2/8 clips: one day
and one night.

## Contact sheets

- `baseball_footage_acq2_2026-09-02/mlb_9HQ_mYBHO1s_grid.jpg`
- `baseball_footage_acq2_2026-09-02/mlb_ZIL6pX5RWs4_grid.jpg`
- `baseball_footage_acq2_2026-09-02/mlb_RN21kmv7KiI_grid.jpg`
- `baseball_footage_acq2_2026-09-02/mlb__jc2UrbEm8E_grid.jpg`
- `baseball_footage_acq2_2026-09-02/mlb_ptIBgr6U1Y8_grid.jpg`
- `baseball_footage_acq2_2026-09-02/mlb__b2FM325c3M_grid.jpg`
- `baseball_footage_acq2_2026-09-02/mlb_g1FSeJz0voM_grid.jpg`
- `baseball_footage_acq2_2026-09-02/mlb_PPj97yvNGOo_grid.jpg`

## Pod staging and observation

Only the two kept clips were passed to `footage_bridge.push_staged`. It uses
scp to a `.part` object, then an atomic remote rename into
`/workspace/nba-ai-system/data/footage_bridge/`. No process was killed,
`/workspace/track_daemon.pid` was not read or touched, and no git command ran
on the pod.

| game_id | staging result | pod ledger status after 10 minutes |
|---|---|---|
| `mlb_ptIBgr6U1Y8` | staged | tracked; 48,319 rows; `passed: false` on `coordinate_contract` (`image_px`) after 120 s |
| `mlb_PPj97yvNGOo` | staged | tracked; 38,319 rows; `passed: false` on `coordinate_contract` (`image_px`) after 165 s |

## What this does not verify

This is an acquisition and visual-content result only. It does not establish
tracking success, coordinate-contract acceptance, baseball metric calibration,
or any model or betting claim. The two pod entries are a daemon-ledger result,
not evidence that the image-pixel coordinate contract was satisfied. Rejected
local clips were not staged.
