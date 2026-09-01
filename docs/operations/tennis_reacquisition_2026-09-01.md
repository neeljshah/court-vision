# Tennis source re-acquisition - 2026-09-01

## Scope

Re-acquired sources for `tennis_07`, `tennis_08`, and `tennis_09`, whose prior
tracking CSVs had no surviving source footage. The local queue was absent in
this worktree because it is ignored; its read-only counterpart supplied the
three source URLs. Existing bridge ledger records supplied no original start or
end offsets, so the requested five-minute midpoint fallback was used.

## Verified sections

| Game | Source section | Resolution | FPS | Frames | Pod staged filename |
|---|---|---:|---:|---:|---|
| tennis_07 | 01:31:17-01:36:17 | 1280x720 | 25 | 7,546 | tennis__tennis_07.mp4 |
| tennis_08 | 00:56:12-01:01:12 | 1280x720 | 25 | 7,616 | tennis__tennis_08.mp4 |
| tennis_09 | 02:23:03-02:28:03 | 1280x720 | 25 | 7,507 | tennis__tennis_09.mp4 |

All downloads used authenticated 720p HLS format 95. Four frames from each
clip were decoded and visually inspected. Each contains a broadcast singles
tennis court view; expected close-ups, score graphics, replays, and crowd shots
appear between points. The existing tennis content gate accepted every clip as
`playing_surface_and_shot_continuity_present`.

## Staging record

Each accepted local clip was uploaded with
`scripts.platformkit.footage_bridge.push_staged`, which transfers to the pod's
private bridge directory as `.part` and publishes with an atomic rename. The
same bridge module wrote one `staged fresh_solve_only` ledger entry per game,
including section and local-verification metadata. No daemon process was
stopped, restarted, or otherwise controlled.
