# G159 raw read-only samples

All timestamps are UTC. Each probe was independently invoked and exited; no monitor, task, process, file copy, configuration change, restart, or deletion was started. The pod command was `ps -eo pid,etimes,args` (not `pgrep -f`), followed by `find` of the staging directory, `du -sb` of the stage and retained corpus, and a read of the daemon ledger. The local command listed `data/videos/bridge` and the seven bridge process command lines. The raw `ps` output also contained unrelated live-service command lines and an access token; those unrelated lines are omitted rather than committed. Every relevant daemon, tracker, and `ffprobe` line is retained verbatim below.

## Sample 001

Command start: `2026-09-03T14:34:22.9122148Z`; pod timestamp: `2026-09-03T14:34:25Z`.

```text
LOCAL_STAGE
tennis_07.f137.mp4|10295368|2026-09-01T18:51:20.6912205Z
tennis_07.mp4|1403118072|2026-09-01T18:58:27.6877575Z
tennis_07.reacq.mp4|30906857|2026-09-01T18:52:21.3282407Z
tennis_08.reacq.mp4|30729994|2026-09-01T18:53:46.2384972Z
tennis_09.reacq.mp4|29765497|2026-09-01T18:54:15.0976767Z
LOCAL_BRIDGE_PROCESS_QUEUE_BINDINGS
9528|kbo, npb
4072|wnba
5116|tennis
18008|soccer
28152|football
16416|mlb
7696|ncaa_basketball
POD_PS_RELEVANT
33064 1226 python -u -m scripts.platformkit.track_daemon --workers 10 --forever --interval 15
44354 57 ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of default=nokey=1:noprint_wrappers=1 data/footage_bridge/baseball__kbo_01.mp4
POD_STAGE
baseball__kbo_01.log|191|2026-09-03T14:33:18.0000000000Z
baseball__kbo_01.mp4|824358578|2026-09-03T14:25:50.0000000000Z
baseball__mlb_2026-08-30_0f36e8cc.mp4|430129314|2026-09-03T14:33:25.0000000000Z
tennis__tennis_01.mp4.part|23239680|2026-09-03T14:34:25.0000000000Z
POD_DU
1277727763 data/footage_bridge
342144561 data/footage_corpus
POD_LEDGER
1 data/tracking/track_daemon_ledger.jsonl
{"game_id":"mlb_2026-08-30_10893dca","seconds":296,"finished_at":1788445421}
```

## Sample 002

Command start: `2026-09-03T14:35:30.4887427Z`; pod timestamp: `2026-09-03T14:35:32Z`.

```text
LOCAL_STAGE
tennis_07.f137.mp4|10295368|2026-09-01T18:51:20.6912205Z
tennis_07.mp4|1403118072|2026-09-01T18:58:27.6877575Z
tennis_07.reacq.mp4|30906857|2026-09-01T18:52:21.3282407Z
tennis_08.reacq.mp4|30729994|2026-09-01T18:53:46.2384972Z
tennis_09.reacq.mp4|29765497|2026-09-01T18:54:15.0976767Z
LOCAL_BRIDGE_PROCESS_QUEUE_BINDINGS
4072|wnba
5116|tennis
7696|ncaa_basketball
9528|kbo, npb
16416|mlb
18008|soccer
28152|football
LOCAL_YTDLP_OR_FFMPEG_COUNT
6
POD_PS_RELEVANT
33064 1293 python -u -m scripts.platformkit.track_daemon --workers 10 --forever --interval 15
44354 124 ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of default=nokey=1:noprint_wrappers=1 data/footage_bridge/baseball__kbo_01.mp4
POD_STAGE
baseball__kbo_01.log|191|2026-09-03T14:33:18.0000000000Z
baseball__kbo_01.mp4|824358578|2026-09-03T14:25:50.0000000000Z
baseball__mlb_2026-08-30_0f36e8cc.mp4|430129314|2026-09-03T14:33:25.0000000000Z
tennis__tennis_01.mp4.part|91653120|2026-09-03T14:35:08.0000000000Z
POD_DU
1346141203 data/footage_bridge
342144561 data/footage_corpus
POD_LEDGER
1 data/tracking/track_daemon_ledger.jsonl
{"game_id":"mlb_2026-08-30_10893dca","seconds":296,"finished_at":1788445421}
```

## Sample 003

Command start: `2026-09-03T14:36:16.8510364Z`; pod timestamp: `2026-09-03T14:36:21Z`.

```text
LOCAL_STAGE
tennis_07.f137.mp4|10295368|2026-09-01T18:51:20.6912205Z
tennis_07.mp4|1403118072|2026-09-01T18:58:27.6877575Z
tennis_07.reacq.mp4|30906857|2026-09-01T18:52:21.3282407Z
tennis_08.reacq.mp4|30729994|2026-09-01T18:53:46.2384972Z
tennis_09.reacq.mp4|29765497|2026-09-01T18:54:15.0976767Z
LOCAL_BRIDGE_PROCESS_QUEUE_BINDINGS
4072|wnba
5116|tennis
7696|ncaa_basketball
9528|kbo, npb
16416|mlb
18008|soccer
28152|football
LOCAL_YTDLP_OR_FFMPEG_COUNT
8
POD_PS_RELEVANT
33064 1341 python -u -m scripts.platformkit.track_daemon --workers 10 --forever --interval 15
44354 173 ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of default=nokey=1:noprint_wrappers=1 data/footage_bridge/baseball__kbo_01.mp4
POD_STAGE
baseball__kbo_01.log|191|2026-09-03T14:33:18.0000000000Z
baseball__kbo_01.mp4|824358578|2026-09-03T14:25:50.0000000000Z
baseball__mlb_2026-08-30_0f36e8cc.mp4|430129314|2026-09-03T14:33:25.0000000000Z
tennis__tennis_01.mp4.part|91653120|2026-09-03T14:35:08.0000000000Z
POD_DU
1346141203 data/footage_bridge
342144561 data/footage_corpus
POD_LEDGER
1 data/tracking/track_daemon_ledger.jsonl
{"game_id":"mlb_2026-08-30_10893dca","seconds":296,"finished_at":1788445421}
```
