# G01 ingest re-gate dry run (2026-09-02)

## Scope and method

`queue_expander` defines `data/footage_queue_<sport>.json`; the supervisor
also enumerates those files by glob. The local worktree has zero such queue
files, so this dry run read the six live queue files on the pod at
`/workspace/nba-ai-system` through read-only SSH.

No queue JSON, video, tracking artifact, daemon, downloader, or pod process
was changed. There were no probe downloads. For each YouTube URL, the audit
requested its oEmbed title only with a four-second timeout and applied the
corrected whole-token title rule. A missing title has no title verdict and is
counted as falling through to the 90-second probe and 12-frame census; the
runtime marker records this as `title_unknown:<probe-result>`.

The production gate also requests descriptions with yt-dlp. This is a
title-only dry run, so description text is intentionally not represented in
these counts.

## Results

| Sport | Items | Rejected with titles | Ambiguous | Fell through to probe |
|---|---:|---:|---:|---:|
| kbo | 22 | 1 | 0 | 21 |
| mlb | 10 | 0 | 0 | 10 |
| npb | 15 | 0 | 0 | 15 |
| soccer | 15 | 0 | 0 | 15 |
| tennis | 10 | 0 | 0 | 10 |
| wnba | 21 | 3 | 0 | 18 |

The oEmbed audit had no ambiguous titles. All ten MLB URLs and one NPB URL
had no title and therefore fell through as intended. The corrected title gate
was run locally against the read-only queue copies; descriptions were not
requested or evaluated.

### Titles rejected by the title gate

#### kbo: 1

The original Korean title is represented with JSON Unicode escapes to keep the
terminal audit ASCII-safe.

- `kbo_hl_xGuMseB8` - `[LIVE] \u2018\uace0\ubc84\uc9c0\u2019 \uc774\uc7ac\uad6d\uc758 \uc2e0\uc778 \ub4dc\ub798\ud504\ud2b8 \uc2e4\uc2dc\uac04 Q&A \u00b7 \uc678\uc778 vs \uad6d\ub0b4 \uc120\uc218, \uce58\uc5f4\ud55c MVP \uacbd\uc7c1\uc758 \uc2b9\uc790\ub294? \u00b7 \uad73\uc5b4\uc9c0\ub294 5\uac15 \uad6c\ub3c4 | 8.31 | \ud06c\ubcf4\ub77c\uc774\ube0c | \uc57c\uad6c` (`title_reject:q&a`)

#### mlb, npb, soccer, tennis: 0

No title in these queues matches a reject-list or other-sport rule.

#### wnba: 3

- `wnba_ff7izg54AF0` - `CARA JAGO KONTROL BOLA ATAS DI PES PS 3 - TOMBOL DAN PENJELASAN PART I` (`title_reject:pes`)
- `wnba_TI0tG_AAcus` - `RIFKI JOGJA (COBRA) VS IDRIS JEPARA (ACCES GAME) - KANG PS X ARENA CUP | PES PS 3` (`title_reject:pes`)
- `wnba_aUb-iZ9US7E` - `GAMEPLAY PES 2018 PS 3 GEMBOX PATCH - PSG VS PORTUGAL` (`title_reject:gameplay`)

The other observed KBO ceremony/coaching material and WNBA game-like junk do
not carry one of the explicit English title reject phrases. They now proceed
to the 12-frame census, which is the designated USABLE/SUSPECT/JUNK decider.

## Deployment note

The pod daemon and the local downloader still run their old code until they
are restarted. This lane did not restart either process, did not kill any pod
process, and did not touch `/workspace/track_daemon.pid`.

## Not verified

- No 90-second probe was downloaded against a real queue item, so real-queue
  USABLE/SUSPECT/JUNK routing has focused-test coverage only in this worktree.
- The title-only audit does not include yt-dlp descriptions. Those may add
  reject-list matches at runtime but cannot reintroduce a required-keyword
  rejection.
- No daemon has consumed a queue written by gate version 3; a restart is
  outside this task and remains required before the new runtime gate takes
  effect.
