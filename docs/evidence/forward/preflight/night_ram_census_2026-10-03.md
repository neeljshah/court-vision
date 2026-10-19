# S728 paper-night RAM census

PAPER ONLY. Status: ATTENTION
Receipts: seven; attempts: thirty-eight; counted refusals: zero.
Margin: 1048576000 bytes; minimum: 268435456 bytes; ceiling is four times the largest observed peak or the minimum.
Two observed October nights are a small sample; a night with more served games may peak higher.
Earlier nights also constrain the proposal. Refused attempts have no measured peak; admission does not establish completion.

| Receipt | Status | Served games | Largest measured peak (bytes) |
|---|---|---|---|
| 2026-09-24.json | PARTIAL | four | 1638944768 |
| 2026-09-25.json | PARTIAL | three | None |
| 2026-09-26.json | PARTIAL | six | 102117376 |
| 2026-09-29.json | PARTIAL | three | 507265024 |
| 2026-09-30.json | PARTIAL | three | 431976448 |
| 2026-10-01.json | PARTIAL | two | 140816384 |
| 2026-10-02.json | COMPLETE | two | 180260864 |

| Step | Largest peak (bytes) | Proposed kill ceiling (bytes) | Admission floor (bytes) | Deadline (seconds, unchanged) |
|---|---|---|---|---|
| qualification | 1638944768 | 6555779072 | 7604355072 | 900 |
| fill_realism | 361926656 | 1447706624 | 2496282624 | 600 |
| week | 21680128 | 268435456 | 1317011456 | 300 |
| scoreboard | 198336512 | 793346048 | 1841922048 | 900 |
| history | 138125312 | 552501248 | 1601077248 | 900 |
| e | 180260864 | 721043456 | 1769619456 | 1800 |

| Receipt / step | Peak (bytes) | Free RAM (bytes) | Outcome / reason | Original floor (bytes) | Proposed decision / completion |
|---|---|---|---|---|---|
| 2026-09-24.json / qualification | 1638944768 | 2942418944 | KILLED / ceiling_exceeded | 2621440000 | REFUSED / UNKNOWN |
| 2026-09-24.json / fill_realism | 223252480 | 2888220672 | RAN / None | 2621440000 | ADMITTED / OBSERVED_RAN |
| 2026-09-24.json / week | 21680128 | 3270479872 | RAN / None | 2621440000 | ADMITTED / OBSERVED_RAN |
| 2026-09-24.json / scoreboard | 144351232 | 3237814272 | RAN / None | 2621440000 | ADMITTED / OBSERVED_RAN |
| 2026-09-25.json / qualification | None | 670683136 | REFUSED / free_ram_below_floor | 2621440000 | REFUSED / UNKNOWN |
| 2026-09-25.json / fill_realism | None | 670334976 | REFUSED / free_ram_below_floor | 2621440000 | REFUSED / UNKNOWN |
| 2026-09-25.json / week | None | 670212096 | REFUSED / free_ram_below_floor | 2621440000 | REFUSED / UNKNOWN |
| 2026-09-25.json / scoreboard | None | 670019584 | REFUSED / free_ram_below_floor | 2621440000 | REFUSED / UNKNOWN |
| 2026-09-26.json / qualification | None | 1712693248 | REFUSED / free_ram_below_floor | 2621440000 | REFUSED / UNKNOWN |
| 2026-09-26.json / fill_realism | None | 1712693248 | REFUSED / free_ram_below_floor | 2621440000 | REFUSED / UNKNOWN |
| 2026-09-26.json / week | None | 1712693248 | REFUSED / free_ram_below_floor | 2621440000 | ADMITTED / UNKNOWN |
| 2026-09-26.json / scoreboard | None | 1712693248 | REFUSED / free_ram_below_floor | 2621440000 | REFUSED / UNKNOWN |
| 2026-09-26.json / history | None | 1712693248 | REFUSED / free_ram_below_floor | 2621440000 | ADMITTED / UNKNOWN |
| 2026-09-26.json / e | 102117376 | 1712693248 | RAN / None | 1677721600 | REFUSED / UNKNOWN |
| 2026-09-29.json / qualification | 507265024 | 3533635584 | RAN / None | 2621440000 | REFUSED / UNKNOWN |
| 2026-09-29.json / fill_realism | 266657792 | 3250356224 | RAN / None | 2621440000 | ADMITTED / OBSERVED_RAN |
| 2026-09-29.json / week | 20783104 | 2683297792 | RAN / None | 2621440000 | ADMITTED / OBSERVED_RAN |
| 2026-09-29.json / scoreboard | 80879616 | 2696564736 | RAN / child_nonzero_exit | 2621440000 | UNKNOWN / UNKNOWN |
| 2026-09-29.json / history | 137875456 | 2666446848 | RAN / None | 2621440000 | ADMITTED / OBSERVED_RAN |
| 2026-09-29.json / e | 111300608 | 2719277056 | RAN / None | 1677721600 | ADMITTED / OBSERVED_RAN |
| 2026-09-30.json / qualification | 431976448 | 4025282560 | KILLED / step_deadline_exceeded | 2621440000 | REFUSED / UNKNOWN |
| 2026-09-30.json / fill_realism | 361926656 | 4098064384 | RAN / None | 2621440000 | ADMITTED / OBSERVED_RAN |
| 2026-09-30.json / week | 20631552 | 4285145088 | RAN / None | 2621440000 | ADMITTED / OBSERVED_RAN |
| 2026-09-30.json / scoreboard | 198336512 | 4292419584 | RAN / None | 2621440000 | ADMITTED / OBSERVED_RAN |
| 2026-09-30.json / history | 138125312 | 4210876416 | RAN / None | 2621440000 | ADMITTED / OBSERVED_RAN |
| 2026-09-30.json / e | 171458560 | 4229320704 | RAN / None | 1677721600 | ADMITTED / OBSERVED_RAN |
| 2026-10-01.json / qualification | 102342656 | 5183606784 | KILLED / step_deadline_exceeded | 2621440000 | REFUSED / UNKNOWN |
| 2026-10-01.json / fill_realism | None | 2310520832 | REFUSED / free_ram_below_floor | 2621440000 | REFUSED / UNKNOWN |
| 2026-10-01.json / week | None | 2322931712 | REFUSED / free_ram_below_floor | 2621440000 | ADMITTED / UNKNOWN |
| 2026-10-01.json / scoreboard | None | 2328580096 | REFUSED / free_ram_below_floor | 2621440000 | ADMITTED / UNKNOWN |
| 2026-10-01.json / history | None | 2329018368 | REFUSED / free_ram_below_floor | 2621440000 | ADMITTED / UNKNOWN |
| 2026-10-01.json / e | 140816384 | 2329808896 | KILLED / step_deadline_exceeded | 1677721600 | KILLED / KILLED |
| 2026-10-02.json / qualification | 134074368 | 3832086528 | RAN / None | 2621440000 | REFUSED / UNKNOWN |
| 2026-10-02.json / fill_realism | 51453952 | 3868467200 | RAN / None | 2621440000 | ADMITTED / OBSERVED_RAN |
| 2026-10-02.json / week | 20471808 | 3870171136 | RAN / None | 2621440000 | ADMITTED / OBSERVED_RAN |
| 2026-10-02.json / scoreboard | 101068800 | 3859177472 | RAN / None | 2621440000 | ADMITTED / OBSERVED_RAN |
| 2026-10-02.json / history | 120643584 | 3785838592 | RAN / None | 2621440000 | ADMITTED / OBSERVED_RAN |
| 2026-10-02.json / e | 180260864 | 3840262144 | RAN / None | 1677721600 | ADMITTED / OBSERVED_RAN |

Inputs (byte hashes identify exact source bytes; resolution: not applicable, JSON):
- C:\Users\neelj\cxp-S728\scripts\platformkit\execution\paper_night_budget.json (2002 bytes; hash 0979ed7255ea6b1ae227bd8765039562eff171486e7f8ae8de0b99c47c63208b)
- C:\Users\neelj\nba-ai-system\docs\evidence\forward\nights\2026-09-24.json (7213 bytes; hash 89010ca0ecc5af12e8d155f18da12e9f89ace1fa5a8a4472e1ac9afb4989c86e)
- C:\Users\neelj\nba-ai-system\docs\evidence\forward\nights\2026-09-25.json (6202 bytes; hash fec12c74bd26f04446c186bc38292f8bfe3af0398c28c520074d69ec947f91b6)
- C:\Users\neelj\nba-ai-system\docs\evidence\forward\nights\2026-09-26.json (10920 bytes; hash ab9d880e2135859111c26b817a2251ab376adb327070d874d49ec01937df2ade)
- C:\Users\neelj\nba-ai-system\docs\evidence\forward\nights\2026-09-29.json (13556 bytes; hash 5df0442222c30efc24a29ab4d615510e0fe4a85c766faa7265e7f5652da069df)
- C:\Users\neelj\nba-ai-system\docs\evidence\forward\nights\2026-09-30.json (12715 bytes; hash 9877ebb3db716c3a30658791a3408191d70db09f698e58290aea9b1ae2d68ad9)
- C:\Users\neelj\nba-ai-system\docs\evidence\forward\nights\2026-10-01.json (11800 bytes; hash 16404d37570403277e4ce80eddeff20408c06abd563b89ffca75b5e67f56b5ec)
- C:\Users\neelj\nba-ai-system\docs\evidence\forward\nights\2026-10-02.json (13558 bytes; hash 3fdf437e69c542c07f323c94b8a5a3c9de0ae9a137941d4d66008e775d206a71)
- C:\Users\neelj\nba-ai-system\docs\evidence\forward\schedules\2026-09-24_maker_forward.json (1131 bytes; hash 686462bba2b0f32e32515ea9b22dafa93ef55c21d4a4fa694b6733d5ddcb7e21)
- C:\Users\neelj\nba-ai-system\docs\evidence\forward\schedules\2026-09-25_maker_forward.json (849 bytes; hash 50816c272266c2325a2a2d34e480ebc9803be7213ff611b2810cd7eb75021b24)
- C:\Users\neelj\nba-ai-system\docs\evidence\forward\schedules\2026-09-26_maker_forward.json (1737 bytes; hash d2d11baffcdaf8fdc1facad301bc4afa99b8cec18f4910219fcfe11f304afe7d)
- C:\Users\neelj\nba-ai-system\docs\evidence\forward\schedules\2026-09-29_maker_forward.json (865 bytes; hash b4e37a4fab8132852b4920f24a635fbb12dbcf0f152d63bb7c21b18617c381ac)
- C:\Users\neelj\nba-ai-system\docs\evidence\forward\schedules\2026-09-30_maker_forward.json (870 bytes; hash f34f8ac3723a1f8bc27e115d9f89c3b9dfbef3f4e0413d4e3797469de057bab9)
- C:\Users\neelj\nba-ai-system\docs\evidence\forward\schedules\2026-10-01_maker_forward.json (578 bytes; hash ba8e8ed27313c5da402dd3a9afa9f19f98ab088432ac152f6b62cdbc024e7ecf)
- C:\Users\neelj\nba-ai-system\docs\evidence\forward\schedules\2026-10-02_maker_forward.json (576 bytes; hash 56c18b503939ba8b8300059ef65f97a0458b832f37e8b43913486fdadda0bc57)

NOT VERIFIED: unstarted completion, higher served-game workloads, live adoption, actual process termination.
