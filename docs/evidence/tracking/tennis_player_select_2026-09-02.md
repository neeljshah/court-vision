# G26 tennis court-prior player selection (2026-09-02)

This is a measured follow-up to G18. The court solver, camera lock, range
selection, seed (`20260901`), range count (5), frame count (300), and frozen
harness thresholds were not changed. The adapter now admits a person only
when its projected foot is within x=[-6,84] and y=[-4,40] feet, ranks one
candidate in each half by the previous 15 evaluated frames, and retains
out-of-court candidates in `last_non_players`.

## Step 0: pod confirmation

The pod detector dump used the current-frame court solve on the two reported
frames before the implementation change. Every valid person box is listed as
`xyxy -> projected foot` in feet.

| frame | boxes | old emitted feet | confirmation |
|---|---|---|---|
| tennis_09 f5070 | (741.6,166.7,799.0,265.8)->(95.2,5.9); (987.6,555.8,1052.0,749.3)->(1.3,19.7); (1695.9,454.2,1919.1,587.5)->(21.0,50.4); (591.5,130.2,623.3,222.3)->(113.2,-6.5); (1285.9,139.7,1314.2,227.7)->(110.9,40.8); (1399.2,223.7,1631.5,505.8)->(33.8,41.5); (1569.5,208.6,1632.7,283.3)->(89.1,56.6); (1573.7,340.0,1713.4,444.0)->(45.7,49.5) | (45.7,49.5), (33.8,41.5) | staff and ball kid were selected; neither real player was emitted. |
| tennis_10 f255 | (732.8,1002.4,821.2,1080.0)->(-15.7,13.9); (1101.8,609.8,1183.5,875.0)->(-0.8,22.9); (625.4,159.5,699.6,285.1)->(80.2,5.7); (1158.0,1011.2,1251.5,1080.0)->(-15.9,23.7); (196.9,394.2,258.5,506.4)->(40.4,-6.9); (1261.3,1016.9,1363.6,1080.0)->(-15.9,26.2); (831.2,1050.7,915.5,1080.0)->(-15.7,16.1); (1685.9,230.9,1769.3,356.4)->(64.8,48.8); (1812.0,430.7,1919.1,620.3)->(24.5,46.6) | (-0.8,22.9), (64.8,48.8) | the chair umpire was selected as the far player. |

## Same-range remeasurement

The final pod run was a separate `nohup setsid nice -n 15` job in
`/tmp/g26_final/`. Solver coverage below is identical before and after on
every range, confirming that no court/camera component changed. `oob` is the
frozen harness metric.

| match | range | oob before -> after | verdict before -> after | solver coverage |
|---|---:|---:|---|---:|
| nyYk 720p | 5715-6014 | 0.0000 -> 0.0000 | PASS -> FAIL | 0.6100 |
| nyYk 720p | 33105-33404 | 0.0000 -> 0.0000 | PASS -> FAIL | 0.9900 |
| nyYk 720p | 33855-34154 | 0.0000 -> 0.0000 | PASS -> FAIL | 0.9967 |
| nyYk 720p | 41985-42284 | 0.0000 -> 0.0000 | PASS -> FAIL | 0.5733 |
| nyYk 720p | 43830-44129 | 0.0000 -> 0.0000 | PASS -> PASS | 0.5600 |
| tennis 09 | 615-914 | 0.5000 -> 0.0000 | FAIL -> FAIL | 0.7067 |
| tennis 09 | 5070-5369 | 0.5133 -> 0.0000 | FAIL -> FAIL | 1.0000 |
| tennis 09 | 5775-6074 | 0.1067 -> 0.0000 | FAIL -> FAIL | 0.5933 |
| tennis 09 | 6960-7259 | 0.0083 -> 0.0000 | PASS -> FAIL | 1.0000 |
| tennis 09 | 7140-7439 | 0.3533 -> 0.0000 | FAIL -> FAIL | 1.0000 |
| tennis 10 | 150-449 | 0.4916 -> 0.0000 | FAIL -> PASS | 0.3967 |
| tennis 10 | 3585-3884 | 0.0000 -> 0.0000 | PASS -> FAIL | 0.4600 |
| tennis 10 | 3930-4229 | 0.0000 -> 0.0000 | PASS -> FAIL | 0.6767 |
| tennis 10 | 6345-6644 | 0.0000 -> 0.0000 | PASS -> FAIL | 0.8433 |
| tennis 10 | 6405-6704 | 0.0000 -> 0.0000 | PASS -> FAIL | 0.6533 |

Pass fractions are nyYk 5/5 -> 1/5, tennis 09 1/5 -> 0/5, and tennis 10
4/5 -> 1/5. All changed failures are frozen two-player coverage failures:
the detector often has only one candidate inside the stipulated expanded
rectangle. This is a valid rejection/no-fallback result, not a court-solve
regression; it does not establish a harness improvement.

## Render-and-look

Eight renders are adjacent to this memo. Green marks a selected candidate and
red marks a rejected candidate. The four tennis 09 frame centers are the
midpoints of its four formerly failing ranges; tennis 10 uses f255, f315,
f345, and f375 in its formerly failing range.

| renders viewed | selected candidates | correct selections | observed limitation |
|---|---:|---:|---|
| 8/8 | 13 | 12/13 | At tennis09 f7289, one courtside person just inside the expanded rectangle is selected; four real players are rejected in the tennis09 renders because their projected feet lie outside that stipulated rectangle. |

The tennis10 renders correctly select both players in all four views and
reject the chair umpire. The tennis09 renders reject the staff, ball kids, and
chair-umpire area, but have the explicitly recorded false positive at f7289.

## Local checks

`python -m pytest domains/tennis/tracking/test_player_select.py -q`:
3 passed.

`python -m pytest domains/tennis/tracking/test_court_lines.py -q`:
5 passed.

`python -m pytest domains/tennis/tracking/test_adapter.py -q`:
16 passed.

`adapter.py` is 264 lines; `player_select.py` is 73 lines.

Not verified: this rule does not recover the frozen two-player coverage gate,
has not been evaluated on a labelled role dataset, and has not been exercised
by a production daemon.
