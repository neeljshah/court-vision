# Worktree inventory 2026-09-30

Read-only inventory by O1 (no deletions, no prunes). Main repo master = cfbeb4660.
Worktrees registered (excluding main): 295. Rows gathered: 281. Columns: ancestor = HEAD is an ancestor of master; ahead = git rev-list --count master..HEAD; dirty = git status --short line count.
S-row = first S### on a line in HARNESS_GAPS_2026-09-03.md or .planning/NOW.md 6205-end matching the sha, the hNNN name, or the branch (heuristic; 'unknown' = no hit).

Disk: du -sk measured 67 of 295 worktrees within the time box, sum = 71960 MB (70.3 GB). Unmeasured worktrees not included; total is a LOWER BOUND.

## SAFE TO PRUNE (ancestor of master AND zero uncommitted changes)

- C:/Users/neelj/nba-codex-night (codex-night, b6a5c82c7, unknown)
- C:/Users/neelj/nba-harness-bisect-postS405 ((detached), 32c9915f9, S405)
- C:/Users/neelj/nba-harness-bisect-preS405 ((detached), c2f478131, unknown)
- C:/Users/neelj/nba-harness-h111 (harness-h111, f13ae4e16, S456)
- C:/Users/neelj/nba-harness-h113 (harness-h113, 1d8adacdd, S463)
- C:/Users/neelj/nba-harness-h123 (harness-h123, 01eb75421, S468)
- C:/Users/neelj/nba-harness-h125 (harness-h125, 74d521e41, S472)
- C:/Users/neelj/nba-harness-h127 (harness-h127, 63fe1eb83, S478)
- C:/Users/neelj/nba-harness-h128 (harness-h128, bfd526163, S473)
- C:/Users/neelj/nba-harness-h142 (harness-h142, ae14c7dd8, S499)
- C:/Users/neelj/nba-harness-h146 (harness-h146, d7963c173, S495)
- C:/Users/neelj/nba-harness-h220 (harness-h220, 026c77413, S500)
- C:/Users/neelj/nba-harness-h258 (harness-h258, ab76a6555, S581)
- C:/Users/neelj/nba-harness-h259 (harness-h259, e21c084da, S581)
- C:/Users/neelj/nba-harness-h264 (harness-h264, e321cc303, S530)
- C:/Users/neelj/nba-harness-h53 (harness-h53, 2df397247, S394)
- C:/Users/neelj/nba-harness-h79 ((detached), 22f80c370, unknown)
- C:/Users/neelj/nba-harness-h98 (harness-h98, 3d5de3ff9, S443)
- C:/Users/neelj/nba-track-a17 (track-a17, 012a05c09, unknown)

## HOLDS UNLANDED WORK (not an ancestor of master, or uncommitted changes)

- C:/Users/neelj/AppData/Local/Temp/s501_v5_land ((detached), d31fe9fd9, unknown): dirty 32
- C:/Users/neelj/court-vision-public (public-master, 1bfcaf034, unknown): ahead 1
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a0770c38e5ec6ce6d (worktree-agent-a0770c38e5ec6ce6d, b9164c5a6, unknown): dirty 3
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a185280a448a7445c (worktree-agent-a185280a448a7445c, 25bdf62a4, S350): ahead 3, dirty 3
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a2659481984a5ca9a (worktree-agent-a2659481984a5ca9a, dd5e2efee, unknown): ahead 1100, dirty 1
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a3fc32dc771781dac (worktree-agent-a3fc32dc771781dac, 66b1cfcea, unknown): dirty 2
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a42893d500548e9a5 (worktree-agent-a42893d500548e9a5, 929927b79, unknown): dirty 3
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a4e5e3b288f67ed2e (worktree-agent-a4e5e3b288f67ed2e, ca1ac4350, unknown): ahead 1156, dirty 1
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a50a2064b396fdf1a (worktree-agent-a50a2064b396fdf1a, 9d67f4a03, unknown): ahead 1147, dirty 2
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a52cef917492ce905 (worktree-agent-a52cef917492ce905, f3d18f5bd, unknown): ahead 6
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a54c6e89786656cb6 (worktree-agent-a54c6e89786656cb6, a78bae5f2, unknown): ahead 1204, dirty 3
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a5ca2ef27f4802997 (worktree-agent-a5ca2ef27f4802997, cb12ee8d6, unknown): ahead 3
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a5f88edf68abf095d (worktree-agent-a5f88edf68abf095d, ad48312d8, unknown): ahead 1072, dirty 1
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a61929c4dc9f795c9 (worktree-agent-a61929c4dc9f795c9, 3d85c8fb7, unknown): ahead 1091, dirty 1
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a74348a133af6eb77 (worktree-agent-a74348a133af6eb77, a66bbfa24, unknown): dirty 2
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a7aa0b440954f6d57 (worktree-agent-a7aa0b440954f6d57, b9164c5a6, unknown): dirty 2
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a7f86f2dd83c908c4 (worktree-agent-a7f86f2dd83c908c4, c379f42cb, unknown): ahead 1193, dirty 2
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a8d0deda7a265ad53 (bot/2026-05-21-linear-stacker, f8d77e327, unknown): ahead 494, dirty 1
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a920344eccacb8301 (worktree-agent-a920344eccacb8301, 26f350a39, unknown): dirty 4
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a92bf4ea900c97f5b (worktree-agent-a92bf4ea900c97f5b, 9e0d563a1, unknown): ahead 25
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a9a9244887901795e (worktree-agent-a9a9244887901795e, 9c9d3ade2, unknown): dirty 2
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-aa03d56672820b39f (worktree-agent-aa03d56672820b39f, 39733a78a, unknown): dirty 7
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-aa516e62da185e2d7 (worktree-agent-aa516e62da185e2d7, 4a57bad3d, unknown): ahead 8
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-aa5a076d654ebc6d2 (worktree-agent-aa5a076d654ebc6d2, 929927b79, unknown): dirty 4
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-abc79256819bce620 (worktree-agent-abc79256819bce620, e515eb26c, unknown): dirty 3
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-abdebbbb7e24b9ba2 (worktree-agent-abdebbbb7e24b9ba2, 6ca6fc768, S343): ahead 3
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-ac3280400ce3dc538 (worktree-agent-ac3280400ce3dc538, 2d60b2517, unknown): ahead 1170, dirty 1
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-ac5e9137f3e35db31 (worktree-agent-ac5e9137f3e35db31, 858e7d4cc, unknown): ahead 1171, dirty 1
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-acb589985e035b44f (worktree-agent-acb589985e035b44f, 198405ce5, unknown): ahead 1193, dirty 1
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-adb174d1b7b2adb57 (worktree-agent-adb174d1b7b2adb57, 960505431, unknown): dirty 2
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-add974d29f0d7f97e (worktree-agent-add974d29f0d7f97e, 43f925d66, unknown): ahead 1136, dirty 2
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-ae307bda2c484fd85 (worktree-agent-ae307bda2c484fd85, bf2604948, unknown): ahead 3, dirty 4
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-ae705ef85aaa2a219 (worktree-agent-ae705ef85aaa2a219, ab45a3bbf, unknown): ahead 1136, dirty 1
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-afadc3bfd799f0eb1 (worktree-agent-afadc3bfd799f0eb1, defe6703f, unknown): ahead 1072, dirty 1
- C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-afc48faf51fc28f79 (worktree-agent-afc48faf51fc28f79, 929927b79, unknown): dirty 3
- C:/Users/neelj/nba-ai-system/.claude/worktrees/codex-analytics (codex/analytics-redesign, 5fc03df6e, unknown): ahead 43
- C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-57 (worktree-wf_1f1e8c90-97b-57, d7f6c76db, unknown): ahead 1504, dirty 1
- C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-63 (worktree-wf_1f1e8c90-97b-63, db1ba32e7, unknown): ahead 1832, dirty 1
- C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-64 (worktree-wf_1f1e8c90-97b-64, 093d05375, unknown): ahead 1505, dirty 302
- C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-65 (worktree-wf_1f1e8c90-97b-65, d7f6c76db, unknown): ahead 1504, dirty 1
- C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-70 (worktree-wf_1f1e8c90-97b-70, d7f6c76db, unknown): ahead 1504, dirty 3
- C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-71 (worktree-wf_1f1e8c90-97b-71, db1ba32e7, unknown): ahead 1832, dirty 1
- C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-72 (wt-match-engine-fix, db1ba32e7, unknown): ahead 1832, dirty 1
- C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-73 (worktree-wf_1f1e8c90-97b-73, d7f6c76db, unknown): ahead 1504, dirty 7
- C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-74 (worktree-wf_1f1e8c90-97b-74, d7f6c76db, unknown): ahead 1504, dirty 1
- C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-75 (worktree-wf_1f1e8c90-97b-75, db1ba32e7, unknown): ahead 1832, dirty 1
- C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-78 (worktree-wf_1f1e8c90-97b-78, d7f6c76db, unknown): ahead 1504, dirty 1
- C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-80 (worktree-wf_1f1e8c90-97b-80, d7f6c76db, unknown): ahead 1504, dirty 1
- C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-81 (fix-pbp-mapper-loc, db1ba32e7, unknown): ahead 1832, dirty 2
- C:/Users/neelj/nba-backup-docs (backup/local-docs, b39e7d001, unknown): ahead 1
- C:/Users/neelj/nba-codex-combo (codex/combo-search, eec55de18, unknown): ahead 7, dirty 2
- C:/Users/neelj/nba-codex-dmtest (codex/harden-dm-test, eca910ffa, unknown): ahead 6
- C:/Users/neelj/nba-codex-tennis-lock (codex/tennis-camera-lock-honest, 196b3f57d, unknown): ahead 1
- C:/Users/neelj/nba-codex-wave6e (codex/football-wave6e, 4f7aedd2c, unknown): ahead 4
- C:/Users/neelj/nba-codex-wave6g (codex/football-wave6g, fd95073fc, unknown): ahead 6, dirty 2
- C:/Users/neelj/nba-codex-wt (codex-lane, a995494b9, unknown): dirty 61
- C:/Users/neelj/nba-harness-h1 (harness-h1, 6c0525ca4, unknown): ahead 1
- C:/Users/neelj/nba-harness-h10 (harness-h10, 5cb4cadcb, unknown): dirty 17
- C:/Users/neelj/nba-harness-h100 (harness-h100, 409f36ae2, S444): ahead 1
- C:/Users/neelj/nba-harness-h101 (harness-h101, ffb1e849a, S445): ahead 1
- C:/Users/neelj/nba-harness-h102 (harness-h102, e2c3269a5, S447): ahead 1
- C:/Users/neelj/nba-harness-h103 (harness-h103, 9020e2c70, S448): ahead 1
- C:/Users/neelj/nba-harness-h104 (harness-h104, 9743a89c1, S450): ahead 1
- C:/Users/neelj/nba-harness-h106 (harness-h106, 7b4fd7c80, unknown): ahead 1
- C:/Users/neelj/nba-harness-h107 (harness-h107, c79cfe78d, S453): ahead 1
- C:/Users/neelj/nba-harness-h108 (harness-h108, 74669cfb7, S455): ahead 1
- C:/Users/neelj/nba-harness-h11 (harness-h11, f11c194de, S354): ahead 1
- C:/Users/neelj/nba-harness-h110 (harness-h110, e6693150f, S457): ahead 1
- C:/Users/neelj/nba-harness-h112 (harness-h112, c10fbf712, unknown): ahead 1
- C:/Users/neelj/nba-harness-h114 (harness-h114, 506694e41, S459): ahead 1
- C:/Users/neelj/nba-harness-h115 (harness-h115, 0f945413b, S460): ahead 1
- C:/Users/neelj/nba-harness-h116 (harness-h116, ec9d3ee1b, S461): ahead 1
- C:/Users/neelj/nba-harness-h117 (harness-h117, 71314ea9d, S462): ahead 1
- C:/Users/neelj/nba-harness-h118 (harness-h118, c1a47b377, S464): ahead 1
- C:/Users/neelj/nba-harness-h119 (harness-h119, 2dfff62ae, S465): ahead 1
- C:/Users/neelj/nba-harness-h12 (harness-h12, f2812e876, unknown): ahead 5, dirty 1
- C:/Users/neelj/nba-harness-h120 (harness-h120, 279edbcf3, S467): ahead 1
- C:/Users/neelj/nba-harness-h121 (harness-h121, fd5595a69, S466): ahead 1
- C:/Users/neelj/nba-harness-h122 (harness-h122, b28713145, S470): ahead 1
- C:/Users/neelj/nba-harness-h124 (harness-h124, 93e524736, unknown): ahead 1
- C:/Users/neelj/nba-harness-h126 (harness-h126, c7acc495e, unknown): ahead 1
- C:/Users/neelj/nba-harness-h129 (harness-h129, 7cb9638bd, unknown): ahead 1
- C:/Users/neelj/nba-harness-h13 (harness-h13, effb39e76, S355): ahead 1, dirty 1
- C:/Users/neelj/nba-harness-h130 (harness-h130, 17feae002, unknown): ahead 1
- C:/Users/neelj/nba-harness-h131 (harness-h131, 2a01da759, unknown): ahead 1
- C:/Users/neelj/nba-harness-h132 (harness-h132, 5d57e230f, unknown): ahead 1
- C:/Users/neelj/nba-harness-h133 (harness-h133, 4b420cda5, unknown): ahead 1
- C:/Users/neelj/nba-harness-h134 (harness-h134, 757f25979, unknown): ahead 1
- C:/Users/neelj/nba-harness-h135 (harness-h135, 0c7a606b6, unknown): ahead 1
- C:/Users/neelj/nba-harness-h136 (harness-h136, 5f302cb24, unknown): ahead 1
- C:/Users/neelj/nba-harness-h137 (harness-h137, 2162b5de2, unknown): ahead 1
- C:/Users/neelj/nba-harness-h138 (harness-h138, b45c36700, unknown): ahead 1
- C:/Users/neelj/nba-harness-h139 (harness-h139, e5e9783a9, S448): ahead 1, dirty 3
- C:/Users/neelj/nba-harness-h14 (harness-h14, 3f2297163, S356): ahead 1
- C:/Users/neelj/nba-harness-h140 (harness-h140, 3c3339eb0, S448): ahead 1, dirty 1
- C:/Users/neelj/nba-harness-h141 (harness-h141, b26fe5bd0, S492): dirty 24
- C:/Users/neelj/nba-harness-h143 (harness-h143, 40cc5974c, unknown): ahead 1
- C:/Users/neelj/nba-harness-h144 (harness-h144, d3aee7c41, S500): ahead 1, dirty 23
- C:/Users/neelj/nba-harness-h145 (harness-h145, 544e44c64, unknown): ahead 1
- C:/Users/neelj/nba-harness-h15 (harness-h15, 20f475ba4, S357): ahead 1
- C:/Users/neelj/nba-harness-h150 (harness-h150, a2ea710e8, S500): ahead 1
- C:/Users/neelj/nba-harness-h151 (harness-h151, 118cf191f, unknown): ahead 1
- C:/Users/neelj/nba-harness-h152 (harness-h152, 439d5298a, unknown): ahead 1
- C:/Users/neelj/nba-harness-h153 (harness-h153, 1cf83e428, unknown): ahead 1
- C:/Users/neelj/nba-harness-h16 (harness-h16, 5127ea6e7, unknown): ahead 1, dirty 1
- C:/Users/neelj/nba-harness-h160 (harness-h160, 9f3ab27a8, S500): ahead 1
- C:/Users/neelj/nba-harness-h161 (harness-h161, 92436d2a9, S496): ahead 1, dirty 5
- C:/Users/neelj/nba-harness-h162 (harness-h162, 148dee461, S612): dirty 1
- C:/Users/neelj/nba-harness-h163 (harness-h163, 14a83fcb3, S492): ahead 2, dirty 14
- C:/Users/neelj/nba-harness-h17 (harness-h17, 333ad94e0, unknown): ahead 1, dirty 2
- C:/Users/neelj/nba-harness-h170 (harness-h170, ac4fc8c7d, S510): ahead 10
- C:/Users/neelj/nba-harness-h18 (harness-h18, 82e86b43a, unknown): ahead 1
- C:/Users/neelj/nba-harness-h180 (harness-h180, 890b5e556, unknown): ahead 1, dirty 1
- C:/Users/neelj/nba-harness-h181 (harness-h181, 3ba0cb30e, unknown): ahead 1
- C:/Users/neelj/nba-harness-h19 (harness-h19, 978513a81, unknown): ahead 1
- C:/Users/neelj/nba-harness-h2 (harness-h2, ba29f792e, unknown): ahead 1, dirty 1
- C:/Users/neelj/nba-harness-h20 (harness-h20, f6eee46f6, unknown): dirty 7
- C:/Users/neelj/nba-harness-h21 (harness-h21, 6c5647161, unknown): ahead 1
- C:/Users/neelj/nba-harness-h210 (harness-h210, 3c48e37cd, S500): ahead 1
- C:/Users/neelj/nba-harness-h211 (harness-h211, 31cfe99df, S541): ahead 1
- C:/Users/neelj/nba-harness-h212 (harness-h212, bcd8787be, S541): ahead 1
- C:/Users/neelj/nba-harness-h213 (harness-h213, 6964b73ba, S544): ahead 1
- C:/Users/neelj/nba-harness-h22 (harness-h22, 2bca67395, unknown): ahead 1
- C:/Users/neelj/nba-harness-h221 (harness-h221, a9c63bd16, unknown): ahead 1, dirty 1
- C:/Users/neelj/nba-harness-h222 (harness-h222, 02076c183, unknown): ahead 1
- C:/Users/neelj/nba-harness-h23 (harness-h23, 6eab526b5, unknown): ahead 1, dirty 1
- C:/Users/neelj/nba-harness-h230 (harness-h230, 4562037bf, S510): ahead 1
- C:/Users/neelj/nba-harness-h231 (harness-h231, 53cf71ba5, unknown): ahead 1
- C:/Users/neelj/nba-harness-h232 (harness-h232, c4bd924c4, S561): ahead 1
- C:/Users/neelj/nba-harness-h233 (harness-h233, b0ea18da7, unknown): ahead 1
- C:/Users/neelj/nba-harness-h24 (harness-h24, a910e7de2, unknown): ahead 1
- C:/Users/neelj/nba-harness-h240 (harness-h240, 2076a28a8, S570): ahead 1
- C:/Users/neelj/nba-harness-h241 (harness-h241, 27fdd5c0e, unknown): ahead 1
- C:/Users/neelj/nba-harness-h242 (harness-h242, 5e5debd6d, unknown): ahead 1
- C:/Users/neelj/nba-harness-h243 (harness-h243, 4125d25d4, unknown): ahead 1
- C:/Users/neelj/nba-harness-h244 (harness-h244, b7fad6d27, unknown): ahead 1
- C:/Users/neelj/nba-harness-h245 (harness-h245, 1e78defa9, unknown): ahead 1
- C:/Users/neelj/nba-harness-h246 (harness-h246, c4a23c3d7, unknown): ahead 1
- C:/Users/neelj/nba-harness-h247 (harness-h247, 3591e3530, unknown): ahead 1
- C:/Users/neelj/nba-harness-h248 (harness-h248, 5215fc72d, unknown): ahead 1
- C:/Users/neelj/nba-harness-h249 (harness-h249, 07718a600, S570): ahead 1
- C:/Users/neelj/nba-harness-h25 (harness-h25, f1673252c, unknown): ahead 1
- C:/Users/neelj/nba-harness-h250 (harness-h250, f3c480eb2, S570): ahead 16
- C:/Users/neelj/nba-harness-h251 (harness-h251, 67529d35c, S581): ahead 10, dirty 6
- C:/Users/neelj/nba-harness-h252 (harness-h252, 67529d35c, S581): ahead 10, dirty 8
- C:/Users/neelj/nba-harness-h253 (harness-h253, 67529d35c, S581): ahead 10, dirty 9
- C:/Users/neelj/nba-harness-h254 (harness-h254, 0357b0873, unknown): ahead 1
- C:/Users/neelj/nba-harness-h255 (harness-h255, 4768bc71d, unknown): ahead 1
- C:/Users/neelj/nba-harness-h256 (harness-h256, adebfac08, S581): ahead 1
- C:/Users/neelj/nba-harness-h257 (harness-h257, 1efd9aac9, S588): dirty 4
- C:/Users/neelj/nba-harness-h26 (harness-h26, b8e1d7879, unknown): ahead 1, dirty 1
- C:/Users/neelj/nba-harness-h260 (harness-h260, 609aea951, S534): dirty 12
- C:/Users/neelj/nba-harness-h261 (harness-h261, 609aea951, S534): dirty 12
- C:/Users/neelj/nba-harness-h262 (harness-h262, 295ee5c01, S535): ahead 1
- C:/Users/neelj/nba-harness-h263 (harness-h263, f85716f3f, S535): ahead 1
- C:/Users/neelj/nba-harness-h27 (harness-h27, 57a567d11, unknown): ahead 1
- C:/Users/neelj/nba-harness-h270 (harness-h270, 25e74cba7, S550): ahead 1
- C:/Users/neelj/nba-harness-h271 (harness-h271, d80f68f9e, S598): dirty 19
- C:/Users/neelj/nba-harness-h272 (harness-h272, 52f4f69f1, unknown): ahead 1, dirty 1
- C:/Users/neelj/nba-harness-h273 (harness-h273, da5a1864c, unknown): ahead 1
- C:/Users/neelj/nba-harness-h274 (harness-h274, 7418c5b5d, unknown): ahead 1
- C:/Users/neelj/nba-harness-h275 (harness-h275, ee866fa4b, unknown): ahead 1
- C:/Users/neelj/nba-harness-h276 (harness-h276, 2ae6eef65, unknown): ahead 1
- C:/Users/neelj/nba-harness-h28 (harness-h28, aa8ecf17f, unknown): ahead 1
- C:/Users/neelj/nba-harness-h280 (harness-h280, fbb553868, S561): ahead 1
- C:/Users/neelj/nba-harness-h281 (harness-h281, 22b05fb04, S518): ahead 1
- C:/Users/neelj/nba-harness-h29 (harness-h29, fd82a37a4, unknown): ahead 1, dirty 1
- C:/Users/neelj/nba-harness-h295 (harness-h295, 8bca3a90f, S570): ahead 1
- C:/Users/neelj/nba-harness-h3 (harness-h3, 784d1e22e, S348): ahead 1
- C:/Users/neelj/nba-harness-h30 (harness-h30, 168f95604, unknown): ahead 1
- C:/Users/neelj/nba-harness-h300 (harness-h300, 2aee65757, S492): ahead 2
- C:/Users/neelj/nba-harness-h301 (harness-h301, 2d50e1b1b, S611): ahead 1
- C:/Users/neelj/nba-harness-h302 (harness-h302, a9930ed15, S611): ahead 1
- C:/Users/neelj/nba-harness-h31 (harness-h31, cf0041942, unknown): ahead 1
- C:/Users/neelj/nba-harness-h32 (harness-h32, e0a317be8, unknown): ahead 1
- C:/Users/neelj/nba-harness-h320 (harness-h320, a1205d333, S613): ahead 1
- C:/Users/neelj/nba-harness-h322 (harness-h322, 5893deb5f, S625): ahead 5
- C:/Users/neelj/nba-harness-h33 (harness-h33, d99bc90d9, unknown): ahead 1, dirty 1
- C:/Users/neelj/nba-harness-h34 (harness-h34, 9632082e4, unknown): ahead 1, dirty 1
- C:/Users/neelj/nba-harness-h35 (harness-h35, e9e8131d2, unknown): ahead 1
- C:/Users/neelj/nba-harness-h36 (harness-h36, c2852908f, unknown): ahead 2
- C:/Users/neelj/nba-harness-h37 (harness-h37, 65bba1339, unknown): ahead 1
- C:/Users/neelj/nba-harness-h38 (harness-h38, 4266fddbf, unknown): ahead 1
- C:/Users/neelj/nba-harness-h39 (harness-h39, 60c82b57e, unknown): ahead 1, dirty 1
- C:/Users/neelj/nba-harness-h4 (harness-h4, 4cd01fcf0, S344): ahead 1, dirty 1
- C:/Users/neelj/nba-harness-h40 (harness-h40, a3433684a, S374): ahead 1
- C:/Users/neelj/nba-harness-h41 (harness-h41, 35c2887e9, S375): ahead 1
- C:/Users/neelj/nba-harness-h42 (harness-h42, 4fe733e16, unknown): ahead 1
- C:/Users/neelj/nba-harness-h43 (harness-h43, 76bf05c3a, unknown): ahead 2
- C:/Users/neelj/nba-harness-h44 (harness-h44, 0bf28a37d, unknown): ahead 1
- C:/Users/neelj/nba-harness-h45 (harness-h45, d12652e6d, unknown): ahead 1
- C:/Users/neelj/nba-harness-h46 (harness-h46, bfeb34d84, unknown): ahead 1
- C:/Users/neelj/nba-harness-h47 (harness-h47, 74cd4d772, unknown): ahead 2
- C:/Users/neelj/nba-harness-h48 (harness-h48, 963028d8c, unknown): ahead 1, dirty 1
- C:/Users/neelj/nba-harness-h49 (harness-h49, 2d8bf08df, unknown): ahead 1
- C:/Users/neelj/nba-harness-h5 (harness-h5, b40563e0d, S347): ahead 1
- C:/Users/neelj/nba-harness-h50 (harness-h50, 2512426d3, unknown): ahead 1
- C:/Users/neelj/nba-harness-h51 (harness-h51, bd2ff8c7a, unknown): ahead 1
- C:/Users/neelj/nba-harness-h52 (harness-h52, 5a42c84ed, unknown): ahead 1, dirty 6
- C:/Users/neelj/nba-harness-h54 (harness-h54, 5a45d40a4, unknown): ahead 1
- C:/Users/neelj/nba-harness-h55 (harness-h55, 4339a935d, unknown): ahead 1
- C:/Users/neelj/nba-harness-h56 (harness-h56, a65299104, unknown): ahead 1, dirty 19
- C:/Users/neelj/nba-harness-h57 (harness-h57, 4488d1e34, unknown): ahead 1
- C:/Users/neelj/nba-harness-h58 (harness-h58, 33e61412d, unknown): ahead 1
- C:/Users/neelj/nba-harness-h59 (harness-h59, e90efef6c, unknown): ahead 1, dirty 1
- C:/Users/neelj/nba-harness-h6 (harness-h6, 7535ac502, S351): ahead 1
- C:/Users/neelj/nba-harness-h60 (harness-h60, 9afd67ab9, unknown): ahead 1
- C:/Users/neelj/nba-harness-h61 (harness-h61, b38d86ecf, unknown): ahead 1, dirty 1
- C:/Users/neelj/nba-harness-h62 (harness-h62, 2945026dd, S401): ahead 1
- C:/Users/neelj/nba-harness-h63 (harness-h63, ec3290807, S402): ahead 1
- C:/Users/neelj/nba-harness-h64 (harness-h64, 02afe1320, S403): ahead 1
- C:/Users/neelj/nba-harness-h65 (harness-h65, 57a3d5f83, S404): ahead 1
- C:/Users/neelj/nba-harness-h66 (harness-h66, 579624ca3, S405): ahead 1
- C:/Users/neelj/nba-harness-h67 (harness-h67, 19a8e6a1d, S406): ahead 1, dirty 1
- C:/Users/neelj/nba-harness-h68 (harness-h68, 8011e63bc, unknown): ahead 1
- C:/Users/neelj/nba-harness-h69 (harness-h69, 5a42c84ed, unknown): ahead 1, dirty 7
- C:/Users/neelj/nba-harness-h7 (harness-h7, 65de58ac1, S353): dirty 2
- C:/Users/neelj/nba-harness-h72 (harness-h72, 3371d7f8f, unknown): ahead 1, dirty 1
- C:/Users/neelj/nba-harness-h73 (harness-h73, 2a7e6d1e7, unknown): ahead 1
- C:/Users/neelj/nba-harness-h74 (harness-h74, c270e669e, unknown): ahead 1
- C:/Users/neelj/nba-harness-h75 (harness-h75, ee3e97561, unknown): ahead 1
- C:/Users/neelj/nba-harness-h76 (harness-h76, 3fcf1f0e2, unknown): ahead 1
- C:/Users/neelj/nba-harness-h77 (harness-h77, a535e362d, unknown): ahead 1
- C:/Users/neelj/nba-harness-h78 (harness-h78, 89f262a9f, S422): ahead 1
- C:/Users/neelj/nba-harness-h8 (harness-h8, d6dc6d4fe, unknown): ahead 5, dirty 1
- C:/Users/neelj/nba-harness-h80 (harness-h80, 6efea946a, S423): ahead 1
- C:/Users/neelj/nba-harness-h81 (harness-h81, 19e8cf1bd, S424): ahead 1
- C:/Users/neelj/nba-harness-h82 (harness-h82, 11d96ed97, S425): ahead 1
- C:/Users/neelj/nba-harness-h83 (harness-h83, d0d93ee5d, unknown): ahead 1
- C:/Users/neelj/nba-harness-h84 (harness-h84, d881409ae, unknown): ahead 1
- C:/Users/neelj/nba-harness-h85 (harness-h85, b8c2b3cdd, unknown): ahead 1, dirty 2
- C:/Users/neelj/nba-harness-h86 (harness-h86, 267a2a6ed, unknown): ahead 1
- C:/Users/neelj/nba-harness-h87 (harness-h87, c2a844dd5, unknown): ahead 1
- C:/Users/neelj/nba-harness-h88 (harness-h88, 40c2576c2, unknown): ahead 1
- C:/Users/neelj/nba-harness-h89 (harness-h89, a221a4a55, S433): ahead 1
- C:/Users/neelj/nba-harness-h9 (harness-h9, bf2604948, unknown): ahead 3, dirty 6
- C:/Users/neelj/nba-harness-h90 (harness-h90, 7f0c85f94, unknown): ahead 1
- C:/Users/neelj/nba-harness-h91 (harness-h91, a0527446e, unknown): ahead 1
- C:/Users/neelj/nba-harness-h92 (harness-h92, 61dd51811, unknown): ahead 1
- C:/Users/neelj/nba-harness-h93 (harness-h93, d065fbcec, unknown): ahead 1
- C:/Users/neelj/nba-harness-h94 (harness-h94, d1d4cc828, S439): ahead 1
- C:/Users/neelj/nba-harness-h95 (harness-h95, 67e14480f, S440): ahead 1
- C:/Users/neelj/nba-harness-h97 (harness-h97, 305a23eff, unknown): ahead 1
- C:/Users/neelj/nba-harness-h99 (harness-h99, 9fb2a1e55, S446): ahead 1
- C:/Users/neelj/nba-soccer-geometry-wt (codex/soccer-geometry-guard, 475903be1, unknown): ahead 6, dirty 2
- C:/Users/neelj/nba-track-a1 (track-a1, 20f307afc, unknown): ahead 4, dirty 1
- C:/Users/neelj/nba-track-a10 (track-a10, ca3a8de5e, unknown): ahead 7
- C:/Users/neelj/nba-track-a11 (track-a11, 8ea2910cd, unknown): ahead 5
- C:/Users/neelj/nba-track-a12 (track-a12, 7734d2b56, unknown): ahead 6, dirty 12
- C:/Users/neelj/nba-track-a13 (track-a13, 554754a8d, unknown): ahead 5, dirty 7
- C:/Users/neelj/nba-track-a14 (track-a14, 05eb2fb87, S187): ahead 2, dirty 1
- C:/Users/neelj/nba-track-a15 (track-a15, b4cf9be71, unknown): ahead 7, dirty 1
- C:/Users/neelj/nba-track-a16 (track-a16, b69633b37, unknown): ahead 2, dirty 6
- C:/Users/neelj/nba-track-a18 (track-a18, 6eaa61382, unknown): ahead 7, dirty 1
- C:/Users/neelj/nba-track-a19 (track-a19, f6d44027a, unknown): ahead 7
- C:/Users/neelj/nba-track-a2 (track-a2, 259585da4, unknown): ahead 7
- C:/Users/neelj/nba-track-a20 (track-a20, acf9f3182, unknown): ahead 11
- C:/Users/neelj/nba-track-a21 (track-a21, 9203d6be3, unknown): ahead 9
- C:/Users/neelj/nba-track-a22 (track-a22, 088c81d13, unknown): ahead 17
- C:/Users/neelj/nba-track-a3 (track-a3, 0e0c6cdee, unknown): ahead 7, dirty 2
- C:/Users/neelj/nba-track-a4 (track-a4, decb187d1, unknown): ahead 3, dirty 1
- C:/Users/neelj/nba-track-a5 (track-a5, 91d80a74b, unknown): ahead 7, dirty 3

## Full table

| path | branch | HEAD | subject | dirty | first dirty paths | ancestor | ahead | S-row |
|---|---|---|---|---|---|---|---|---|
| C:/Users/neelj/AppData/Local/Temp/s501_v5_land | (detached) | d31fe9fd9 | spec: S501 AMENDMENT 6 (verify r4: C9 time-bomb fix -- declared-manifest + disjo | 32 | .gitattributes scripts/platformkit/execution/ingame_scoreboard_amendment.py scripts/platformkit/execution/ingame_scoreboard_night.py  | yes | 0 | unknown |
| C:/Users/neelj/court-vision-public | public-master | 1bfcaf034 | publish: sync the public tree from 4f66acfb5 | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a0770c38e5ec6ce6d | worktree-agent-a0770c38e5ec6ce6d | b9164c5a6 | G416 correction applied post-landing (codex-sol ACCEPT WITH CORRECTIONS): memo l | 3 | scripts/platformkit/dist_metrics.py scripts/platformkit/proof_nba/prop_game_model.py tests/platformkit/test_prop_game_model.py  | yes | 0 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a185280a448a7445c | worktree-agent-a185280a448a7445c | 25bdf62a4 | fix(domains/nfl): S350 lane 1b -- address verifier rejection (yardline_100, sour | 3 | docs/evidence/tracking/specs/S350_spec.md scripts/platformkit/tracking/ tmp/  | no | 3 | S350 |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a2659481984a5ca9a | worktree-agent-a2659481984a5ca9a | dd5e2efee | R22_O8: NBA injury report scraper + production wire | 1 | data/cache/alerts/  | no | 1100 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a3fc32dc771781dac | worktree-agent-a3fc32dc771781dac | 66b1cfcea | docs: S337 landing hash after rebase (register row + ledger correction line) | 2 | scripts/platformkit/execution/coherence_audit.py tests/platformkit/test_coherence_audit.py  | yes | 0 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a42893d500548e9a5 | worktree-agent-a42893d500548e9a5 | 929927b79 | Build interactive CourtVision analytics workspace from published evidence | 3 | scripts/platformkit/tracking/contract_preflight.py scripts/platformkit/tracking/contract_preflight_extra.py tests/platformkit/test_contract_preflight.py  | yes | 0 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a4e5e3b288f67ed2e | worktree-agent-a4e5e3b288f67ed2e | ca1ac4350 | R27_T3: feature drift detector + dashboard + daily workflow hook | 1 | data/cache/feature_drift_latest.json  | no | 1156 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a50a2064b396fdf1a | worktree-agent-a50a2064b396fdf1a | 9d67f4a03 | R26_S7: free-arb critical alert wire (middle_finder -> alert()) | 2 | data/cache/alerts/critical_2026-05-26.json data/cache/daemon_heartbeats/middle_finder_daemon.txt  | no | 1147 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a52cef917492ce905 | worktree-agent-a52cef917492ce905 | f3d18f5bd | analytics: atlas_factory --check guards the card_path relativization | 0 |  | no | 6 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a54c6e89786656cb6 | worktree-agent-a54c6e89786656cb6 | a78bae5f2 | R31_X2: extend R21_N1 worktree resolver to 3 more loaders (game_models, residual | 3 | data/cache/alerts/critical_2026-05-26.json data/cache/daemon_heartbeats/middle_finder_daemon.txt data/cache/probe_R30_W6_results.json  | no | 1204 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a5ca2ef27f4802997 | worktree-agent-a5ca2ef27f4802997 | cb12ee8d6 | fix(execution): S345 fix all six verifier-rejection findings | 0 |  | no | 3 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a5f88edf68abf095d | worktree-agent-a5f88edf68abf095d | ad48312d8 | R20_M3: betting pipeline test coverage +169 tests, +11 pp coverage | 1 | data/cache/daemon_heartbeats/bov_scraper.txt  | no | 1072 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a61929c4dc9f795c9 | worktree-agent-a61929c4dc9f795c9 | 3d85c8fb7 | R21_N3: layered alert with vault + critical-stack fallback | 1 | data/cache/alerts/  | no | 1091 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a74348a133af6eb77 | worktree-agent-a74348a133af6eb77 | a66bbfa24 | docs: S333 lane_commit preflight hook applied (register + ledger note) | 2 | scripts/platformkit/tracking/proposed_apply.py tests/platformkit/test_proposed_apply.py  | yes | 0 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a7aa0b440954f6d57 | worktree-agent-a7aa0b440954f6d57 | b9164c5a6 | G416 correction applied post-landing (codex-sol ACCEPT WITH CORRECTIONS): memo l | 2 | scripts/platformkit/proof_nba/winprob_feature_challenger.py tests/platformkit/test_winprob_feature_challenger.py  | yes | 0 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a7f86f2dd83c908c4 | worktree-agent-a7f86f2dd83c908c4 | c379f42cb | R30_W3 PARTIAL: predictions_cache rebuild infra (player-prop cache, zero delta) | 2 | data/cache/predictions_cache_2026-05-26.parquet data/cache/predictions_cache_2026-05-26.parquet.bak_R30_W3  | no | 1193 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a8d0deda7a265ad53 | bot/2026-05-21-linear-stacker | f8d77e327 | feat: linear stacker meta-learner (XGB+LGB+CAT ensemble) | 1 | data/models/live_win_prob_metrics.json  | no | 494 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a920344eccacb8301 | worktree-agent-a920344eccacb8301 | 26f350a39 | docs: S335 corrected-module note (760984070) in register + ledger | 4 | scripts/platformkit/ingame/polymarket_book_capture.py scripts/platformkit/ingame/polymarket_book_row.py scripts/platformkit/ingame/polymarket_scope.py  | yes | 0 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a92bf4ea900c97f5b | worktree-agent-a92bf4ea900c97f5b | 9e0d563a1 | chore: refresh check_all_report.json after the with-data --check fixes | 0 |  | no | 25 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-a9a9244887901795e | worktree-agent-a9a9244887901795e | 9c9d3ade2 | docs: S338 Q20 refresh complete (all advanced as-of tables 100 pct for 2025-26) | 2 | scripts/platformkit/asof_nightly_refresh.py tests/platformkit/test_asof_nightly_refresh.py  | yes | 0 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-aa03d56672820b39f | worktree-agent-aa03d56672820b39f | 39733a78a | docs: S339 register row + ledger line for Q04 (74b1e26aa); NEXT_GAP_ID -> S340 | 7 | scripts/platformkit/ingame/kalshi_book_capture.py scripts/platformkit/ingame/kalshi_book_row.py scripts/platformkit/ingame/polymarket_book_capture.py  | yes | 0 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-aa516e62da185e2d7 | worktree-agent-aa516e62da185e2d7 | 4a57bad3d | exec: markout pairs strictly, and unkeyed fills share one cluster | 0 |  | no | 8 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-aa5a076d654ebc6d2 | worktree-agent-aa5a076d654ebc6d2 | 929927b79 | Build interactive CourtVision analytics workspace from published evidence | 4 | scripts/platformkit/ingame/kalshi_book_capture.py scripts/platformkit/ingame/kalshi_book_row.py scripts/platformkit/ingame/kalshi_series_scope.py  | yes | 0 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-abc79256819bce620 | worktree-agent-abc79256819bce620 | e515eb26c | docs: S332 register row + ledger line for Q15 (698283376); NEXT_GAP_ID -> S333 | 3 | scripts/platformkit/proof_nba/gate_b_diagnostics.py scripts/platformkit/proof_nba/gate_b_tracking_ablation.py tests/platformkit/test_gate_b_tracking_ablation.py  | yes | 0 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-abdebbbb7e24b9ba2 | worktree-agent-abdebbbb7e24b9ba2 | 6ca6fc768 | fix(execution): S343 causal markout -- spec window boundary (lane 1c) | 0 |  | no | 3 | S343 |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-ac3280400ce3dc538 | worktree-agent-ac3280400ce3dc538 | 2d60b2517 | R28_U3: nightly cleanup orchestrator + daily_workflow integration | 1 | data/cache/feature_drift_latest.json  | no | 1170 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-ac5e9137f3e35db31 | worktree-agent-ac5e9137f3e35db31 | 858e7d4cc | R28_U5: auto-generate vault/MORNING.md one-page operator brief | 1 | data/cache/probe_R28_U5_results.json  | no | 1171 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-acb589985e035b44f | worktree-agent-acb589985e035b44f | 198405ce5 | R30_W4: dashboard data freshness section (13 sources, per-source thresholds) | 1 | data/cache/feature_drift_latest.json  | no | 1193 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-adb174d1b7b2adb57 | worktree-agent-adb174d1b7b2adb57 | 960505431 | docs: S335 Gate B 2025-26 adjudication (c1eeaf9bb): per-game family tested, smal | 2 | scripts/platformkit/proof_nba/prop_game_model_matchup.py tests/platformkit/test_prop_game_model_matchup.py  | yes | 0 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-add974d29f0d7f97e | worktree-agent-add974d29f0d7f97e | 43f925d66 | R25_R2: settle disagreement audit + fix top failure mode | 2 | data/cache/recon_full_R25_R2.json data/cache/recon_substantive_R25_R2.json  | no | 1136 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-ae307bda2c484fd85 | worktree-agent-ae307bda2c484fd85 | bf2604948 | fix(platformkit): S346 rev3 -- verifier REJECT fixes per spec AMENDMENT 1 | 4 | docs/evidence/tracking/specs/S346_spec.md scripts/platformkit/clv/ scripts/platformkit/segment_ingame_join.py  | no | 3 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-ae705ef85aaa2a219 | worktree-agent-ae705ef85aaa2a219 | ab45a3bbf | R25_R1: backfill 2025-26 team-level pregame features (1225 games) | 1 | data/cache/probe_R25_R1_results.json  | no | 1136 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-afadc3bfd799f0eb1 | worktree-agent-afadc3bfd799f0eb1 | defe6703f | R20_M1: Bov alt-line normalizer + arb-join guard | 1 | data/cache/daemon_heartbeats/bov_scraper.txt  | no | 1072 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/agent-afc48faf51fc28f79 | worktree-agent-afc48faf51fc28f79 | 929927b79 | Build interactive CourtVision analytics workspace from published evidence | 3 | docs/evidence/ingame/ scripts/platformkit/ingame/gate_a0_ingame_vs_market.py tests/platformkit/test_gate_a0_ingame_vs_market.py  | yes | 0 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/codex-analytics | codex/analytics-redesign | 5fc03df6e | fix(analytics): align calibration Scout summaries with source receipts | 0 |  | no | 43 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-57 | worktree-wf_1f1e8c90-97b-57 | d7f6c76db | docs: world-class honest showcase rewrite + edge/ops quarantine | 1 | scripts/platformkit/cohesive_read.py  | no | 1504 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-63 | worktree-wf_1f1e8c90-97b-63 | db1ba32e7 | feat(mlb): W129  wire validated NegBinom into JointDistribution.sample() (pro | 1 | scripts/platformkit/rating_calibrated.py  | no | 1832 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-64 | worktree-wf_1f1e8c90-97b-64 | 093d05375 | baseline: import platformkit + vault from fullsend for isolated fix | 302 | scripts/platformkit/sport_read.py tests/basketball_nba/test_asof_features.py tests/basketball_nba/test_ingest_boxscores.py  | no | 1505 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-65 | worktree-wf_1f1e8c90-97b-65 | d7f6c76db | docs: world-class honest showcase rewrite + edge/ops quarantine | 1 | tests/platform/test_inning_engine.py  | no | 1504 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-70 | worktree-wf_1f1e8c90-97b-70 | d7f6c76db | docs: world-class honest showcase rewrite + edge/ops quarantine | 3 | domains/ scripts/platformkit/ tests/platform/  | no | 1504 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-71 | worktree-wf_1f1e8c90-97b-71 | db1ba32e7 | feat(mlb): W129  wire validated NegBinom into JointDistribution.sample() (pro | 1 | scripts/platformkit/live_read.py  | no | 1832 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-72 | wt-match-engine-fix | db1ba32e7 | feat(mlb): W129  wire validated NegBinom into JointDistribution.sample() (pro | 1 | tests/platform/test_match_engine.py  | no | 1832 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-73 | worktree-wf_1f1e8c90-97b-73 | d7f6c76db | docs: world-class honest showcase rewrite + edge/ops quarantine | 7 | domains/__init__.py domains/mlb/__init__.py domains/mlb/inning_engine.py  | no | 1504 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-74 | worktree-wf_1f1e8c90-97b-74 | d7f6c76db | docs: world-class honest showcase rewrite + edge/ops quarantine | 1 | scripts/platformkit/brain_pipeline.py  | no | 1504 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-75 | worktree-wf_1f1e8c90-97b-75 | db1ba32e7 | feat(mlb): W129  wire validated NegBinom into JointDistribution.sample() (pro | 1 | domains/tennis/match_engine.py  | no | 1832 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-78 | worktree-wf_1f1e8c90-97b-78 | d7f6c76db | docs: world-class honest showcase rewrite + edge/ops quarantine | 1 | scripts/ingame/repricer_calibration.py  | no | 1504 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-80 | worktree-wf_1f1e8c90-97b-80 | d7f6c76db | docs: world-class honest showcase rewrite + edge/ops quarantine | 1 | tests/platform/test_nba_pbp_mapper.py  | no | 1504 | unknown |
| C:/Users/neelj/nba-ai-system/.claude/worktrees/wf_1f1e8c90-97b-81 | fix-pbp-mapper-loc | db1ba32e7 | feat(mlb): W129  wire validated NegBinom into JointDistribution.sample() (pro | 2 | domains/basketball_nba/pbp_event_map.py domains/basketball_nba/pbp_mapper.py  | no | 1832 | unknown |
| C:/Users/neelj/nba-backup-docs | backup/local-docs | b39e7d001 | backup(local-docs): private snapshot 2026-09-04 of .planning, docs/research, doc | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-codex-combo | codex/combo-search | eec55de18 | feat(eval-gate): add preregistered elastic-net combo search | 2 | findings.md task_plan.md  | no | 7 | unknown |
| C:/Users/neelj/nba-codex-dmtest | codex/harden-dm-test | eca910ffa | fix(eval-gate): fail closed DM clustering | 0 |  | no | 6 | unknown |
| C:/Users/neelj/nba-codex-night | codex-night | b6a5c82c7 | docs(evidence): the two tracking demo clips themselves | 0 |  | yes | 0 | unknown |
| C:/Users/neelj/nba-codex-tennis-lock | codex/tennis-camera-lock-honest | 196b3f57d | evidence(tennis): measure camera lock on accepting sections | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-codex-wave6e | codex/football-wave6e | 4f7aedd2c | evidence(football): record 1080p resolution gate | 0 |  | no | 4 | unknown |
| C:/Users/neelj/nba-codex-wave6g | codex/football-wave6g | fd95073fc | football: measure numeral anchored registration | 2 | findings.md task_plan.md  | no | 6 | unknown |
| C:/Users/neelj/nba-codex-wt | codex-lane | a995494b9 | fix(footage_bridge): private remote stage, row-count success test, never-stoppin | 61 | domains/baseball/tracking/adapter.py domains/baseball/tracking/test_adapter.py domains/football/tracking/__init__.py  | yes | 0 | unknown |
| C:/Users/neelj/nba-harness-bisect-postS405 | (detached) | 32c9915f9 | fix(S405): memo size test pins LF bytes at the landing commit b66352c69 (git sho | 0 |  | yes | 0 | S405 |
| C:/Users/neelj/nba-harness-bisect-preS405 | (detached) | c2f478131 | spec(S393) AMENDMENT 7 (astra r11): restart never aborts unrelated discovery (cr | 0 |  | yes | 0 | unknown |
| C:/Users/neelj/nba-harness-h1 | harness-h1 | 6c0525ca4 | feat(execution): S342 minimal maker quote engine (prepare-only; codex terra buil | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h10 | harness-h10 | 5cb4cadcb | docs(harness): S341 spec -- binding data-integrity requirements R1-R9 for the lo | 17 | docs/evidence/tracking/specs/S341_spec.md docs/evidence/harness/S341_local_capture_2026-09-21.md scripts/platformkit/ingame/local_capture_backfill.py  | yes | 0 | unknown |
| C:/Users/neelj/nba-harness-h100 | harness-h100 | 409f36ae2 | feat(S444): attested seal provenance -- seal_provenance.py (git-attested first-c | 0 |  | no | 1 | S444 |
| C:/Users/neelj/nba-harness-h101 | harness-h101 | ffb1e849a | feat(S445): continuous paper decision history -- paper_account.py + paper_accoun | 0 |  | no | 1 | S445 |
| C:/Users/neelj/nba-harness-h102 | harness-h102 | e2c3269a5 | feat(S447): served MLB in-game = pregame carry, measured -- mlb_predict_live_vs_ | 0 |  | no | 1 | S447 |
| C:/Users/neelj/nba-harness-h103 | harness-h103 | 9020e2c70 | S448 ACCEPT: MLB served ratings frozen -- frozen-vs-walk-forward Elo eval gate ( | 0 |  | no | 1 | S448 |
| C:/Users/neelj/nba-harness-h104 | harness-h104 | 9743a89c1 | S450 ACCEPT: MLB pitcher strikeout distribution -- a pre-registered, launch-char | 0 |  | no | 1 | S450 |
| C:/Users/neelj/nba-harness-h106 | harness-h106 | 7b4fd7c80 | S452 ACCEPT: served-path adjudication (season binds to opp_team at stitch_router | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h107 | harness-h107 | c79cfe78d | feat(S453): bound TradeGroup.archived_ids in the Kalshi books runner -- ARCHIVED | 0 |  | no | 1 | S453 |
| C:/Users/neelj/nba-harness-h108 | harness-h108 | 74669cfb7 | S455 ACCEPT: Polymarket archived ids are bounded -- a route-local bounded insert | 0 |  | no | 1 | S455 |
| C:/Users/neelj/nba-harness-h11 | harness-h11 | f11c194de | fix(execution): S354 shared version-independent venue-time parser; markout_causa | 0 |  | no | 1 | S354 |
| C:/Users/neelj/nba-harness-h110 | harness-h110 | e6693150f | S457 ACCEPT: MLB event-response ops hardening (six-place quantisation of output  | 0 |  | no | 1 | S457 |
| C:/Users/neelj/nba-harness-h111 | harness-h111 | f13ae4e16 | S456 ACCEPT: MLB starter ordinals attach to pitcher rows only (explicit ordered  | 0 |  | yes | 0 | S456 |
| C:/Users/neelj/nba-harness-h112 | harness-h112 | c10fbf712 | S458 ACCEPT: request_class label on every books/state row (focus_books, bulk, di | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h113 | harness-h113 | 1d8adacdd | S463 ACCEPT: pointer hand-off at startup unions the --schedule rows -- both the  | 0 |  | yes | 0 | S463 |
| C:/Users/neelj/nba-harness-h114 | harness-h114 | 506694e41 | S459 ACCEPT: feasible late-game focus close under a capacity cap -- an opt-in pl | 0 |  | no | 1 | S459 |
| C:/Users/neelj/nba-harness-h115 | harness-h115 | 0f945413b | S460 ACCEPT: arm E of the in-game scoreboard -- a feature registry of typed bloc | 0 |  | no | 1 | S460 |
| C:/Users/neelj/nba-harness-h116 | harness-h116 | ec9d3ee1b | S461 ACCEPT: atomic replace survives a Windows replace race -- bounded Permissio | 0 |  | no | 1 | S461 |
| C:/Users/neelj/nba-harness-h117 | harness-h117 | 71314ea9d | S462 ACCEPT: the local capture client heals its own wedge -- a per-source ATTEMP | 0 |  | no | 1 | S462 |
| C:/Users/neelj/nba-harness-h118 | harness-h118 | c1a47b377 | S464 ACCEPT: pointer and supervisor atomic writes survive a Windows replace race | 0 |  | no | 1 | S464 |
| C:/Users/neelj/nba-harness-h119 | harness-h119 | 2dfff62ae | S465 ACCEPT: the unattended paper night runs the in-game scoreboard -- a fourth  | 0 |  | no | 1 | S465 |
| C:/Users/neelj/nba-harness-h12 | harness-h12 | f2812e876 | fix(platformkit): S346 fix lane 1d (codex) -- spec AMENDMENT 3: corroborated sco | 1 | docs/evidence/tracking/specs/S346_spec.md  | no | 5 | unknown |
| C:/Users/neelj/nba-harness-h120 | harness-h120 | 279edbcf3 | S467 ACCEPT: MLB lineup, batting order and pitcher hand reach the state row -- a | 0 |  | no | 1 | S467 |
| C:/Users/neelj/nba-harness-h121 | harness-h121 | fd5595a69 | S466 ACCEPT: capture supervisor lock recovery -- stale-lock takeover keyed on ow | 0 |  | no | 1 | S466 |
| C:/Users/neelj/nba-harness-h122 | harness-h122 | b28713145 | S470 ACCEPT: paper-night steps get a per-step wall-time deadline -- an optional  | 0 |  | no | 1 | S470 |
| C:/Users/neelj/nba-harness-h123 | harness-h123 | 01eb75421 | S468 ACCEPT: NBA per-player live block from play-by-play (PREPARE) -- declared p | 0 |  | yes | 0 | S468 |
| C:/Users/neelj/nba-harness-h124 | harness-h124 | 93e524736 | S471 LANDED: arm E registry consumes the S467 lineup blocks under the supersedin | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h125 | harness-h125 | 74d521e41 | S472 LANDED: NBA starter inference from first appearances in orderNumber order ( | 0 |  | yes | 0 | S472 |
| C:/Users/neelj/nba-harness-h126 | harness-h126 | c7acc495e | S477 LANDED: forward schedule --local-date-tz (NFL primetime + tennis local-date | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h127 | harness-h127 | 63fe1eb83 | S478 LANDED: nightly six-sport coverage census, report-only (scheduled / capture | 0 |  | yes | 0 | S478 |
| C:/Users/neelj/nba-harness-h128 | harness-h128 | bfd526163 | S473 LANDED: paper-night input roots as a production gate (junction targets chec | 0 |  | yes | 0 | S473 |
| C:/Users/neelj/nba-harness-h129 | harness-h129 | 7cb9638bd | S475 LANDED: S439 arms B/C eligible without model_prob on an opt-in route (B = m | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h13 | harness-h13 | effb39e76 | feat(ingame): S355 four-arm scorer eligibility (never an abort), duplicate-key r | 1 | docs/evidence/tracking/specs/S355_spec.md  | no | 1 | S355 |
| C:/Users/neelj/nba-harness-h130 | harness-h130 | 17feae002 | S486 LANDED: WNBA books capture registered (one sport tuple; other sports byte-i | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h131 | harness-h131 | 2a01da759 | S474 LANDED: S439 scoreboard training-history producer (guarded paper-night hist | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h132 | harness-h132 | 5d57e230f | S479 LANDED: paper-night qualification streams through a SQLite spool with a tot | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h133 | harness-h133 | 4b420cda5 | S481 LANDED: WNBA state / schedule / identity registration (separate WNBA clock: | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h134 | harness-h134 | 757f25979 | S480 LANDED: MLB arm E numeric for the first time (shared count helper accepts e | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h135 | harness-h135 | 0c7a606b6 | S484 LANDED: night-dated seal selection (append-only SEALS table in ingame_score | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h136 | harness-h136 | 5f302cb24 | S483 LANDED: state capture memory -- exact tennis groupings strip (landed path k | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h137 | harness-h137 | 2162b5de2 | S488 LANDED: night-module output replace goes through the shared replace_with_re | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h138 | harness-h138 | b45c36700 | S476 LANDED DORMANT: arm E paper-night step (orientation from the first state ro | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h139 | harness-h139 | e5e9783a9 | S489 LANDED: arm-E paper-night step memory fix -- rows slimmed to the fields the | 3 | .s489_c20/ .s489_tmp/ .s489_verify/  | no | 1 | S448 |
| C:/Users/neelj/nba-harness-h14 | harness-h14 | 3f2297163 | fix(execution): S356 causal markout selects marks by time, never by price change | 0 |  | no | 1 | S356 |
| C:/Users/neelj/nba-harness-h140 | harness-h140 | 3c3339eb0 | S485 LANDED: per-sport qualification refusal (one sport's missing D state no lon | 1 | .s485_verify/  | no | 1 | S448 |
| C:/Users/neelj/nba-harness-h141 | harness-h141 | b26fe5bd0 | spec: S492 AMENDMENT 5 (commit A' = seal JSON alone, landed d507296d7; SEALS lin | 24 | .gitattributes scripts/platformkit/execution/ingame_scoreboard_amendment.py scripts/platformkit/execution/ingame_scoreboard_night.py  | yes | 0 | S492 |
| C:/Users/neelj/nba-harness-h142 | harness-h142 | ae14c7dd8 | S499 LANDED: arm E declared in the committed paper-night budget (ceiling_bytes.e | 0 |  | yes | 0 | S499 |
| C:/Users/neelj/nba-harness-h143 | harness-h143 | 40cc5974c | construct: S492 commit A trial (local only) | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h144 | harness-h144 | d3aee7c41 | S500 LANDED: unattended paper desk tick (Windows task every 30 min: capture live | 23 | .s500_tmp/ .s500_verify/ tmp28uf4nug/  | no | 1 | S500 |
| C:/Users/neelj/nba-harness-h145 | harness-h145 | 544e44c64 | S501 LANDED: a RAM-refused paper night defers (exit 4, non-terminal bounded nigh | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h146 | harness-h146 | d7963c173 | spec: S495 arm A is the venue mid, not a devigged price (docs-only relabel; astr | 0 |  | yes | 0 | S495 |
| C:/Users/neelj/nba-harness-h15 | harness-h15 | 20f475ba4 | feat(execution): S357 fractional quantities end to end (Decimal ledger, caps, qu | 0 |  | no | 1 | S357 |
| C:/Users/neelj/nba-harness-h150 | harness-h150 | a2ea710e8 | S490: six-league soccer state + schedule writer (eng.1 ger.1 esp.1 ita.1 fra.1 u | 0 |  | no | 1 | S500 |
| C:/Users/neelj/nba-harness-h151 | harness-h151 | 118cf191f | S497: restore c21 streamed hard-kill test (stale one-arg _sample_peak wrapper sw | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h152 | harness-h152 | 439d5298a | S494: NBA season-type labels captured on state rows and schedule entries (raw ES | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h153 | harness-h153 | 1cf83e428 | S533: census test wnba zero-coverage reasons match the registered sport; test_18 | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h16 | harness-h16 | 5127ea6e7 | feat(ingame): S352 + S358 local game-state capture -- commit-then-promote writes | 1 | docs/evidence/tracking/specs/S358_spec.md  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h160 | harness-h160 | 9f3ab27a8 | S496 LANDED: a state row whose sport differs from its shard directory is counted | 0 |  | no | 1 | S500 |
| C:/Users/neelj/nba-harness-h161 | harness-h161 | 92436d2a9 | S503 LANDED: prospective cumulative cross-night scoreboard evaluator over commit | 5 | .s503-e2e-accepted/ .s503-e2e-final/ .s503-e2e-temp/  | no | 1 | S496 |
| C:/Users/neelj/nba-harness-h162 | harness-h162 | 148dee461 | S612: D1 writer resolves venue team codes per sport (MLB only): the aliased defa | 1 | docs/evidence/forward/scoreboard/training/  | yes | 0 | S612 |
| C:/Users/neelj/nba-harness-h163 | harness-h163 | 14a83fcb3 | S492 commit-B candidate: memo records the R1 verifier notes (prep only) | 14 | scripts/platformkit/execution/ingame_scoreboard.py scripts/platformkit/execution/ingame_scoreboard_night.py tests/platformkit/execution/test_ingame_scoreboard_amendment_model_optional.py  | no | 2 | S492 |
| C:/Users/neelj/nba-harness-h17 | harness-h17 | 333ad94e0 | feat(ingame): S359 charged four-arm trial runner -- canonical ledger only, manif | 2 | docs/evidence/tracking/specs/S359_spec.md pytest-of-neelj/  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h170 | harness-h170 | ac4fc8c7d | S510 fix 4 (AMENDMENT 5) | 0 |  | no | 10 | S510 |
| C:/Users/neelj/nba-harness-h18 | harness-h18 | 82e86b43a | feat(ingame): S360 NBA checkpoints to joined corpus -- exact-key join, precision | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h180 | harness-h180 | 890b5e556 | S515: live shadow quote recorder (MLB): tail-only causal reads, frozen venue-pre | 1 | .s515_fix3_tmp/  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h181 | harness-h181 | 3ba0cb30e | S516: live shadow fill receipt (offline): per-arm independent tape_fill_sim simu | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h19 | harness-h19 | 978513a81 | feat(ingame): S361 tennis point-level recursion model + state parser -- unreacha | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h2 | harness-h2 | ba29f792e | feat(harness): S349 strict preflight -- missing spec, broken seal, uncommitted p | 1 | .pytest_tmp_s349/  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h20 | harness-h20 | f6eee46f6 | docs(harness): specs + rows S360 NBA joined corpus, S361 tennis recursion model, | 7 | docs/evidence/harness/AUDIT_EXEC_CHAIN_2026-09-21.md docs/evidence/harness/S362_forward_replay_harness_2026-09-21.md scripts/platformkit/execution/forward_replay.py  | yes | 0 | unknown |
| C:/Users/neelj/nba-harness-h21 | harness-h21 | 6c5647161 | feat(ingame): S363 capture watchdog + daily coverage -- a process that collects  | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h210 | harness-h210 | 3c48e37cd | S541: historical in-game corpus hygiene (corpus_hygiene.py keep/drop with reason | 0 |  | no | 1 | S500 |
| C:/Users/neelj/nba-harness-h211 | harness-h211 | 31cfe99df | S542: market-anchored state projection (PROJ: Stern WP NBA/WNBA, normal-approxim | 0 |  | no | 1 | S541 |
| C:/Users/neelj/nba-harness-h212 | harness-h212 | bcd8787be | S545: read-only S439 integrity audit (s439_integrity_audit + _io): terminal cens | 0 |  | no | 1 | S541 |
| C:/Users/neelj/nba-harness-h213 | harness-h213 | 6964b73ba | S544 commit B: Model 2.0 prospective read-out (m2_readout + _io + _history): sea | 0 |  | no | 1 | S544 |
| C:/Users/neelj/nba-harness-h22 | harness-h22 | 2bca67395 | feat(execution): S364 dated fee fixtures + counts-only capture clock diagnostics | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h220 | harness-h220 | 026c77413 | spec: S550 (execution-quality audit receipt) + S551 (offline cancel-policy repla | 0 |  | yes | 0 | S500 |
| C:/Users/neelj/nba-harness-h221 | harness-h221 | a9c63bd16 | S550: execution-quality audit receipt (exec_quality_audit core/pool/io; r2 probe | 1 | tests/platformkit/execution/fixtures/s550_make_expected.py  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h222 | harness-h222 | 02076c183 | S551: offline cancel-policy replay v1 (3 arms x 2 queue scenarios, causal orderi | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h23 | harness-h23 | 6eab526b5 | feat(execution): S365 family / week eligibility ledger -- as-of reads, invisible | 1 | pytest-of-neelj/  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h230 | harness-h230 | 4562037bf | S511: tick_silent paper-desk issue -- a new read-only check (paper_desk_issue_ti | 0 |  | no | 1 | S510 |
| C:/Users/neelj/nba-harness-h231 | harness-h231 | 53cf71ba5 | S560: whole-label orientation table -- exact multi-word Kalshi team labels (mlb  | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h232 | harness-h232 | c4bd924c4 | S561: books live window at the TRUE start -- TYPICAL_DURATION_SEC re-grounded on | 0 |  | no | 1 | S561 |
| C:/Users/neelj/nba-harness-h233 | harness-h233 | b0ea18da7 | S580: NBA season policy on the consumer path -- scoreboard_history_store.validat | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h24 | harness-h24 | a910e7de2 | feat(execution): S366 touch-queue fill sensitivity -- partial ladders authoritat | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h240 | harness-h240 | 2076a28a8 | S572: restore three execution test properties after intentional changes (capture | 0 |  | no | 1 | S570 |
| C:/Users/neelj/nba-harness-h241 | harness-h241 | 27fdd5c0e | S571: autonomy monitor tests isolated from live machine state (m5 heartbeat, orp | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h242 | harness-h242 | 5e5debd6d | S574: rung8 load_game_ticks follows the sidecar retention layout (resolve_game_p | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h243 | harness-h243 | 4125d25d4 | S573: qa smoke memory bound -- ask() top_n and entity residual paths stream stal | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h244 | harness-h244 | b7fad6d27 | S570: wall-clock pinned tests get deterministic clocks (card grader now=NOW_IN o | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h245 | harness-h245 | 1e78defa9 | S576: eight test files no longer depend on gitignored local state (tmp PIPELINE_ | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h246 | harness-h246 | c4a23c3d7 | S577: restore nine test files' properties against reviewed current behaviour (fl | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h247 | harness-h247 | 3591e3530 | S578: test files back under the per-file budget with identical collect counts an | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h248 | harness-h248 | 5215fc72d | S634: restore the lost d175933b3 producer hunk in mechanism_ledger_export (non-f | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h249 | harness-h249 | 07718a600 | S636: wall-clock pins round 2 (settle_sweep inventory pinned via monkeypatched m | 0 |  | no | 1 | S570 |
| C:/Users/neelj/nba-harness-h25 | harness-h25 | f1673252c | feat(ingame): S367 late-game cohort builder -- membership from observables at th | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h250 | harness-h250 | f3c480eb2 | S581: memo regenerated at landing (26 PASS / 8 DEFECT / 0 ERROR) | 0 |  | no | 16 | S570 |
| C:/Users/neelj/nba-harness-h251 | harness-h251 | 67529d35c | S581 fix r2: every pinned case runs in the landed layout; case 14 inputs copied  | 6 | scripts/platformkit/ops/paper_desk_issue_checks.py tests/platformkit/ops/test_paper_desk_issue_checks.py tests/platformkit/ops/test_system_fault_matrix.py  | no | 10 | S581 |
| C:/Users/neelj/nba-harness-h252 | harness-h252 | 67529d35c | S581 fix r2: every pinned case runs in the landed layout; case 14 inputs copied  | 8 | .gitattributes scripts/platformkit/ops/paper_desk_issue_capture.py tests/platformkit/ops/test_system_fault_matrix.py  | no | 10 | S581 |
| C:/Users/neelj/nba-harness-h253 | harness-h253 | 67529d35c | S581 fix r2: every pinned case runs in the landed layout; case 14 inputs copied  | 9 | scripts/platformkit/execution/live_shadow_fills.py scripts/platformkit/execution/live_shadow_fills_io.py scripts/platformkit/execution/live_shadow_io.py  | no | 10 | S581 |
| C:/Users/neelj/nba-harness-h254 | harness-h254 | 0357b0873 | S582: a legitimate zero-game day no longer raises d1_missing/schedule_missing P1 | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h255 | harness-h255 | 4768bc71d | S583: capture states that needed a human are no longer silent -- two new S510 is | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h256 | harness-h256 | adebfac08 | S584: live shadow receipts no longer lose rows at UTC midnight -- the recorder w | 0 |  | no | 1 | S581 |
| C:/Users/neelj/nba-harness-h257 | harness-h257 | 1efd9aac9 | spec: S588 AMENDMENT 1 (pre-build Opus critic: run-seam launch counting, capture | 4 | scripts/platformkit/ops/system_fault_matrix.py tests/platformkit/ops/test_system_fault_matrix.py scripts/platformkit/ops/system_fault_cases_c5.py  | yes | 0 | S588 |
| C:/Users/neelj/nba-harness-h258 | harness-h258 | ab76a6555 | triage memo TEST_SWEEP_TRIAGE_2026-09-29.md (776 files swept, 50 non-green, ever | 0 |  | yes | 0 | S581 |
| C:/Users/neelj/nba-harness-h259 | harness-h259 | e21c084da | spec: S596 (+S564) NBA pbp primary state + live enrichment (spec only, gated on  | 0 |  | yes | 0 | S581 |
| C:/Users/neelj/nba-harness-h26 | harness-h26 | b8e1d7879 | feat(execution): S368 coherence scanner -- Decimal fee boundary, exact sub-micro | 1 | pytest-of-neelj/  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h260 | harness-h260 | 609aea951 | spec: S591 AMENDMENT 1 (pre-build critique folded) | 12 | .gitattributes scripts/platformkit/execution/schedule_d1.py scripts/platformkit/ingame/capture_scheduler.py  | yes | 0 | S534 |
| C:/Users/neelj/nba-harness-h261 | harness-h261 | 609aea951 | spec: S591 AMENDMENT 1 (pre-build critique folded) | 12 | .gitattributes docs/evidence/forward/scoreboard/PREREG_2026-09-30_S490_DEPENDENCY_ADDENDUM.json scripts/platformkit/execution/cross_venue_link.py  | yes | 0 | S534 |
| C:/Users/neelj/nba-harness-h262 | harness-h262 | 295ee5c01 | S535: per-route wall-clock deadline in the ESPN/statsapi state client (local_sta | 0 |  | no | 1 | S535 |
| C:/Users/neelj/nba-harness-h263 | harness-h263 | f85716f3f | S621: same-day pre-first-pitch D1 revision (scripts/platformkit/execution/schedu | 0 |  | no | 1 | S535 |
| C:/Users/neelj/nba-harness-h264 | harness-h264 | e321cc303 | spec: S530 AMENDMENT 1 (pre-build Opus astra-role critic; buildable with amendme | 0 |  | yes | 0 | S530 |
| C:/Users/neelj/nba-harness-h27 | harness-h27 | 57a567d11 | fix(execution): S369 markout identity + units -- same-game marks only, earliest  | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h270 | harness-h270 | 25e74cba7 | S591: seal_provenance treats a git COPY record as an incarnation boundary (PRERE | 0 |  | no | 1 | S550 |
| C:/Users/neelj/nba-harness-h271 | harness-h271 | d80f68f9e | spec: S598 AMENDMENT 2 (build round: re-derived pointer test instants; ratified  | 19 | .gitattributes scripts/platformkit/ingame/capture_schedule_loader.py scripts/platformkit/ingame/capture_scheduler.py  | yes | 0 | S598 |
| C:/Users/neelj/nba-harness-h272 | harness-h272 | 52f4f69f1 | S592: state-source latency census (streaming, RSS-capped) + frozen 09-22..09-28  | 1 | docs/evidence/forward/latency/2026-09-22_2026-09-28_espn_wallclock_map.json  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h273 | harness-h273 | da5a1864c | S595: NFL/NCAAF play clock -- state.last_play_ts from the ESPN core single-play  | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h274 | harness-h274 | 7418c5b5d | S606: the state capture no longer re-reads yesterday's shards at UTC midnight -- | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h275 | harness-h275 | ee866fa4b | S599 part 1: the books capture's archive_tail streams the shard tail line by lin | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h276 | harness-h276 | 2ae6eef65 | S600 part A: the polymarket per-sport heartbeat_ts is stamped at WRITE time (new | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h28 | harness-h28 | aa8ecf17f | fix(execution): S370 fill simulator -- fee validated before any mutation, decrea | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h280 | harness-h280 | fbb553868 | S519: sealed-prereg module for the live shadow mid vs blend cumulative calibrati | 0 |  | no | 1 | S561 |
| C:/Users/neelj/nba-harness-h281 | harness-h281 | 22b05fb04 | S518: NBA slice of the live shadow recorder (PARKED on harness-h281; land after  | 0 |  | no | 1 | S518 |
| C:/Users/neelj/nba-harness-h29 | harness-h29 | fd82a37a4 | fix(execution): S371 position ledger durability + order-id uniqueness -- one imm | 1 | pytest-of-neelj/  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h295 | harness-h295 | 8bca3a90f | S638: restore three test files' properties (bestbets runner boot beat carries th | 0 |  | no | 1 | S570 |
| C:/Users/neelj/nba-harness-h3 | harness-h3 | 784d1e22e | feat(ingame): S348 capture-to-scoring coverage matrix census (codex build, Fable | 0 |  | no | 1 | S348 |
| C:/Users/neelj/nba-harness-h30 | harness-h30 | 168f95604 | feat(execution): S372 quote reservation boundary -- snapshot-bound room, stale s | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h300 | harness-h300 | 2aee65757 | S492 commit-B candidate: memo records the R1 verifier notes (prep only) | 0 |  | no | 2 | S492 |
| C:/Users/neelj/nba-harness-h301 | harness-h301 | 2d50e1b1b | S611: stream forward_schedule_writer._latest (keep only the first row at each ke | 0 |  | no | 1 | S611 |
| C:/Users/neelj/nba-harness-h302 | harness-h302 | a9930ed15 | S612: D1 writer resolves venue team codes per sport (MLB only): the aliased defa | 0 |  | no | 1 | S611 |
| C:/Users/neelj/nba-harness-h31 | harness-h31 | cf0041942 | feat(execution): S373 capture-book adapter -- production snapshot schema to quot | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h32 | harness-h32 | e0a317be8 | fix(ingame): S341 local capture integrity fixes 1b-1g -- multi-tick trade backfi | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h320 | harness-h320 | a1205d333 | S613 (PARKED candidate): nfl alias table WSH->WAS, JAX->JAC; S490 addendum re-se | 0 |  | no | 1 | S613 |
| C:/Users/neelj/nba-harness-h322 | harness-h322 | 5893deb5f | S625 fix r1: mid-before-hook case (adversarial M24), memo records verify r1 (con | 0 |  | no | 5 | S625 |
| C:/Users/neelj/nba-harness-h33 | harness-h33 | d99bc90d9 | feat(ops): S376 capture supervisor -- restart with backoff, free-space refusal,  | 1 | pytest-of-neelj/  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h34 | harness-h34 | 9632082e4 | feat(ingame): S377 NBA joined-corpus readiness census -- counts only, model-inde | 1 | pytest-of-neelj/  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h35 | harness-h35 | e9e8131d2 | feat(execution): S378 fee certification gate -- refuse fee-netted output while t | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h36 | harness-h36 | c2852908f | fix(nfl): S380 live situation verifier fixes 2a-2e -- status live, drive / serie | 0 |  | no | 2 | unknown |
| C:/Users/neelj/nba-harness-h37 | harness-h37 | 65bba1339 | feat(tennis): S381 point-level live source probe -- bounded, credential-free, bo | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h38 | harness-h38 | 4266fddbf | feat(ingame): S379 four-arm output auditor -- provenance, key / chronology and l | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h39 | harness-h39 | 60c82b57e | feat(execution): S362 forward replay harness REBUILD -- qualification only under | 1 | pytest-of-neelj/  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h4 | harness-h4 | 4cd01fcf0 | feat(execution): S344 tape-supported paper fills + explicit trade adapters (prep | 1 | docs/evidence/tracking/specs/S344_spec.md  | no | 1 | S344 |
| C:/Users/neelj/nba-harness-h40 | harness-h40 | a3433684a | fix(ingame): S374 trades written as pages drain -- append + fsync before cursor, | 0 |  | no | 1 | S374 |
| C:/Users/neelj/nba-harness-h41 | harness-h41 | 35c2887e9 | feat(ingame): S375 budgeted capture scheduler -- 45/35/10/5/5 split, sticky focu | 0 |  | no | 1 | S375 |
| C:/Users/neelj/nba-harness-h42 | harness-h42 | 4fe733e16 | docs(ingame): S382 NBA second-corpus prereg DRAFT r1 (unsealed) -- period-strati | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h43 | harness-h43 | 76bf05c3a | fix(ingame): S383 period-first primary exactly as the NBA draft declares; game-f | 0 |  | no | 2 | unknown |
| C:/Users/neelj/nba-harness-h44 | harness-h44 | 0bf28a37d | fix(execution): S384 markout quantity exact decimal path -- decimal-string field | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h45 | harness-h45 | d12652e6d | fix(ingame): S379 auditor fixes 2a + 2b -- outcome is a float label compared by  | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h46 | harness-h46 | bfeb34d84 | feat(execution): S386 prospective schedule writer -- live venue schedules, exact | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h47 | harness-h47 | 74cd4d772 | merge master into harness-h47 (S387 candidate): reconcile with S383 fix 2a and S | 0 |  | no | 2 | unknown |
| C:/Users/neelj/nba-harness-h48 | harness-h48 | 963028d8c | feat(ingame): S388 focus admission from the prospective schedule -- scheduled ga | 1 | pytest-of-neelj/  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h49 | harness-h49 | 2d8bf08df | feat(execution): S389 native capture-to-qualification bridge -- game_key linkage | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h5 | harness-h5 | b40563e0d | feat(ingame): S347 four-arm calibration baseline scorer + UNSEALED prereg draft  | 0 |  | no | 1 | S347 |
| C:/Users/neelj/nba-harness-h50 | harness-h50 | 2512426d3 | feat(ops): S391 owner ten-minute redeploy checklist + read-only capture deploy p | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h51 | harness-h51 | bd2ff8c7a | docs(ingame): S392 NBA exposure + provenance disposition -- identity-level inven | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h52 | harness-h52 | 5a42c84ed | fix(S405): source-size test measures LF-normalized bytes (master's CRLF checkout | 6 | scripts/platformkit/ingame/local_state_capture.py scripts/platformkit/ingame/local_state_capture_sources.py tests/platformkit/ingame/test_state_capture_io.py  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h53 | harness-h53 | 2df397247 | feat(ingame): S394 NBA charged-trial runner -- sibling of S359 with the period-f | 0 |  | yes | 0 | S394 |
| C:/Users/neelj/nba-harness-h54 | harness-h54 | 5a45d40a4 | feat(S395): NBA output auditor -- reconstructs the period-first primary and the  | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h55 | harness-h55 | 4339a935d | fix(ingame): S387 fix 2a -- the NBA outcome label is compared by VALUE (1.0 / 0. | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h56 | harness-h56 | a65299104 | feat(S390): daily score-blind qualification + completed-week report over the pro | 19 | .s362-weeks-166ht0gf/ .s362-weeks-1m12zzpe/ .s362-weeks-2n_xzp6x/  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h57 | harness-h57 | 4488d1e34 | feat(S396): sealed signal-family audit through the landed leak-free gate on exac | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h58 | harness-h58 | 33e61412d | feat(S397): Polymarket live capture for the forward archive -- CLOB book / trade | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h59 | harness-h59 | e90efef6c | feat(S398): cross-venue pairing + coherence scan (Kalshi x Polymarket): pairs li | 1 | .tmp-s398/  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h6 | harness-h6 | 7535ac502 | feat(execution): S351 maker-channel runbook, record-keeping scaffold and fail-cl | 0 |  | no | 1 | S351 |
| C:/Users/neelj/nba-harness-h60 | harness-h60 | 9afd67ab9 | feat(S399): Polymarket certification -- venue fee, tick, size and time semantics | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h61 | harness-h61 | b38d86ecf | feat(S400): paper sizing policy under calibration uncertainty -- unit counts fro | 1 | docs/evidence/tracking/specs/S400_spec.md  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h62 | harness-h62 | 2945026dd | fix(capture): S401 state capture recovers once per process start and once per da | 0 |  | no | 1 | S401 |
| C:/Users/neelj/nba-harness-h63 | harness-h63 | ec3290807 | feat(S402): NBA seal package -- reconciles the S377 readiness census with the S3 | 0 |  | no | 1 | S402 |
| C:/Users/neelj/nba-harness-h64 | harness-h64 | 02afe1320 | feat(forward): S403 the prospective schedule writer emits game_key per sport exa | 0 |  | no | 1 | S403 |
| C:/Users/neelj/nba-harness-h65 | harness-h65 | 57a3d5f83 | feat(S404): bridge exact-identity keyed linkage -- duplicate schedule identity i | 0 |  | no | 1 | S404 |
| C:/Users/neelj/nba-harness-h66 | harness-h66 | 579624ca3 | feat(S405): four-arm contrast over the landed S394 runner -- reported contrast e | 0 |  | no | 1 | S405 |
| C:/Users/neelj/nba-harness-h67 | harness-h67 | 19a8e6a1d | feat(S406): Kalshi archive decimal census -- counts-only text classes per produc | 1 | pytest-of-neelj/  | no | 1 | S406 |
| C:/Users/neelj/nba-harness-h68 | harness-h68 | 8011e63bc | feat(S410): focus-window admission audit -- per-game window status by --as-of (n | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h69 | harness-h69 | 5a42c84ed | fix(S405): source-size test measures LF-normalized bytes (master's CRLF checkout | 7 | scripts/platformkit/execution/forward_schedule_sources.py tests/platformkit/execution/test_forward_schedule_sources.py docs/evidence/harness/S416_forward_schedule_dates_2026-09-22.md  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h7 | harness-h7 | 65de58ac1 | docs(harness): specs + rows S352 local state capture, S353 Kalshi discovery stat | 2 | docs/evidence/harness/S353_series_scope_status_2026-09-21.md tests/platformkit/test_kalshi_series_scope_status.py  | yes | 0 | S353 |
| C:/Users/neelj/nba-harness-h72 | harness-h72 | 3371d7f8f | feat(S417): C-minus-B primary contrast + B_lag lagged-mid control arm in the per | 1 | .s417-1m-tmp/  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h73 | harness-h73 | 2a7e6d1e7 | feat(S413): NFL state ingest -- FEATURES['nfl'] declared (eight situation fields | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h74 | harness-h74 | c270e669e | feat(S416): forward schedule supply by UTC date -- the requested and the previou | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h75 | harness-h75 | ee3e97561 | feat(S421): qualification-cause report -- the four-cause decomposition (pre_adap | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h76 | harness-h76 | 3fcf1f0e2 | feat(S411): fill realism on the captured Kalshi books and trade tape, counts onl | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h77 | harness-h77 | a535e362d | feat(S409): schedule identity attestation -- a committed schedule's game_key ->  | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h78 | harness-h78 | 89f262a9f | feat(S422): Decimal fee chain -- venue_fees_decimal.py facade proven equal to th | 0 |  | no | 1 | S422 |
| C:/Users/neelj/nba-harness-h79 | (detached) | 22f80c370 | spec(S393) AMENDMENT 14 (round 16, both tiers): dedupe keys inside the isolation | 0 |  | yes | 0 | unknown |
| C:/Users/neelj/nba-harness-h8 | harness-h8 | d6dc6d4fe | fix(execution): S345 fix lane 1d (codex) -- spec AMENDMENT 2: reducing orders al | 1 | docs/evidence/tracking/specs/S345_spec.md  | no | 5 | unknown |
| C:/Users/neelj/nba-harness-h80 | harness-h80 | 6efea946a | feat(S423): pregame intelligence prior as a declared in-game feature block (PREP | 0 |  | no | 1 | S423 |
| C:/Users/neelj/nba-harness-h81 | harness-h81 | 19e8cf1bd | feat(S412): microstructure licence -- a sealed MATCH class beside S400's AHEAD l | 0 |  | no | 1 | S424 |
| C:/Users/neelj/nba-harness-h82 | harness-h82 | 11d96ed97 | feat(S425): NBA_TRIAL_JSON line producer -- the one launch line the S394 runner  | 0 |  | no | 1 | S425 |
| C:/Users/neelj/nba-harness-h83 | harness-h83 | d0d93ee5d | feat(S427): paper night runner -- one supervised command per UTC date runs the l | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h84 | harness-h84 | d881409ae | feat(S429): D+1 schedule automation -- one command writes tomorrow's prospective | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h85 | harness-h85 | b8c2b3cdd | feat(S428): weekly record page -- deterministic render of the family week ledger | 2 | docs/evidence/forward/WEEKLY_RECORD.md webapp/public/data/forward/  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h86 | harness-h86 | 267a2a6ed | feat(S434): receipt-causal microstructure feature block -- MICRO_FEATURES (touch | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h87 | harness-h87 | c2a844dd5 | feat(S430): NFL UTC-day schedule window -- opt-in --utc-day-window flag on the f | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h88 | harness-h88 | 40c2576c2 | feat(S432): MLB live-feed state block -- opt-in --mlb-live on the local state ca | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h89 | harness-h89 | a221a4a55 | feat(S433): NBA play-by-play state adapter -- nba_pbp_source.py (CDN play-by-pla | 0 |  | no | 1 | S433 |
| C:/Users/neelj/nba-harness-h9 | harness-h9 | bf2604948 | fix(platformkit): S346 rev3 -- verifier REJECT fixes per spec AMENDMENT 1 | 6 | docs/evidence/harness/S346_segmenter_rev3_2026-09-21.md scripts/platformkit/check_ingame_join_integrity_r3.py scripts/platformkit/segment_ingame_join_r3.py  | no | 3 | unknown |
| C:/Users/neelj/nba-harness-h90 | harness-h90 | 7f0c85f94 | feat(S435): event-response measurement, REPORT ONLY -- the mid move at 5 / 30 /  | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h91 | harness-h91 | a0527446e | feat(S431): event-level in-game latency census -- per served game, the time from | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h92 | harness-h92 | 61dd51811 | feat(S437): NFL state completeness census (measurement row; premise corrected: t | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h93 | harness-h93 | d065fbcec | feat(S438): schedule hand-off without restart -- an opt-in --schedule-pointer on | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h94 | harness-h94 | d1d4cc828 | feat(S439): nightly in-game scoreboard with a sealed preregistration -- integer- | 0 |  | no | 1 | S439 |
| C:/Users/neelj/nba-harness-h95 | harness-h95 | 67e14480f | feat(S440): settlement witness -- snapshot-only rules, trade-aware deduplication | 0 |  | no | 1 | S440 |
| C:/Users/neelj/nba-harness-h97 | harness-h97 | 305a23eff | feat(S442): Kalshi websocket orderbook capture, PREPARE ONLY -- a read-only clie | 0 |  | no | 1 | unknown |
| C:/Users/neelj/nba-harness-h98 | harness-h98 | 3d5de3ff9 | feat(S443): week fill accounting chain -- fill_receipts.py + week_fill_accountin | 0 |  | yes | 0 | S443 |
| C:/Users/neelj/nba-harness-h99 | harness-h99 | 9fb2a1e55 | feat(S446): late-play observation support census -- observation_support_census.p | 0 |  | no | 1 | S446 |
| C:/Users/neelj/nba-soccer-geometry-wt | codex/soccer-geometry-guard | 475903be1 | Fix soccer SynthCal broadcast camera geometry | 2 | findings.md task_plan.md  | no | 6 | unknown |
| C:/Users/neelj/nba-track-a1 | track-a1 | 20f307afc | G361 fix 1b: ALIGNED requires >= 30 distinct landmarks; collisions exclude unpar | 1 | docs/evidence/tracking/G361_VERIFY_2026-09-09.md  | no | 4 | unknown |
| C:/Users/neelj/nba-track-a10 | track-a10 | ca3a8de5e | G416 correction applied for real: memo line 20 repeats.json digest 221cab07...;  | 0 |  | no | 7 | unknown |
| C:/Users/neelj/nba-track-a11 | track-a11 | 8ea2910cd | G417: checkpoint reviewed bounded decoder preparation and regression evidence | 0 |  | no | 5 | unknown |
| C:/Users/neelj/nba-track-a12 | track-a12 | 7734d2b56 | G409 fix 1d (codex-sol REJECT x3, receipt vocabulary): control_route keeps the c | 12 | .g409_drive.sh .g409_drive2.sh .g409_jobs.json  | no | 6 | unknown |
| C:/Users/neelj/nba-track-a13 | track-a13 | 554754a8d | G410 fix 1c (codex-sol ACCEPT WITH CORRECTIONS): draw-overlap note 3/30 CLAMP, 2 | 7 | .g410_queue.tsv .g410_queue_rev.tsv .g410_replay/  | no | 5 | unknown |
| C:/Users/neelj/nba-track-a14 | track-a14 | 05eb2fb87 | Record G414 fixed-window local census and verified durability | 1 | docs/evidence/tracking/specs/G414_spec.md  | no | 2 | S187 |
| C:/Users/neelj/nba-track-a15 | track-a15 | b4cf9be71 | G365 fix 1c: candidate B REJECTED under the sealed bars; row CLOSED AT LIMIT; re | 1 | docs/evidence/tracking/G365_VERIFY_2026-09-09.md  | no | 7 | unknown |
| C:/Users/neelj/nba-track-a16 | track-a16 | b69633b37 | S329: lane work committed by lane_commit (sandbox denied index.lock) | 6 | docs/evidence/harness/S329_prospective_receipt_capture_2026-09-08/probe.csv docs/evidence/harness/S329_prospective_receipt_capture_2026-09-08/verification.csv scripts/platformkit/ingame/capture/receipt_capture.py  | no | 2 | unknown |
| C:/Users/neelj/nba-track-a17 | track-a17 | 012a05c09 | docs(harness): register S324 INSUFFICIENT 2026-09-08 e9d258666 (ACCEPT verified  | 0 |  | yes | 0 | unknown |
| C:/Users/neelj/nba-track-a18 | track-a18 | 6eaa61382 | G404 fix 1d (codex-sol REJECT x3, one field): run-level returncode restored to t | 1 | docs/evidence/tracking/G404_VERIFY_2026-09-11.md  | no | 7 | unknown |
| C:/Users/neelj/nba-track-a19 | track-a19 | f6d44027a | G411 fix 1e (codex-sol REJECT x4, B2 edge path): empty schedule returns the pare | 0 |  | no | 7 | unknown |
| C:/Users/neelj/nba-track-a2 | track-a2 | 259585da4 | G357 fix 1b: even-sampled reseal (31 of 61 eligible; PARTIAL) | 0 |  | no | 7 | unknown |
| C:/Users/neelj/nba-track-a20 | track-a20 | acf9f3182 | G382: apply the two codex-sol corrections in the memo (five decode-failure cards | 0 |  | no | 11 | unknown |
| C:/Users/neelj/nba-track-a21 | track-a21 | 9203d6be3 | G387: remaining control headline restated (13/30 admissible) | 0 |  | no | 9 | unknown |
| C:/Users/neelj/nba-track-a22 | track-a22 | 088c81d13 | G386: record codex-sol fix 1c ACCEPT verify memo (verbatim); ledger line | 0 |  | no | 17 | unknown |
| C:/Users/neelj/nba-track-a3 | track-a3 | 0e0c6cdee | G415: checkpoint verified local retry preparation and failure accounting | 2 | .pytest_tmp_g415c/ docs/evidence/tracking/G415_VERIFY_2026-09-11.md  | no | 7 | unknown |
| C:/Users/neelj/nba-track-a4 | track-a4 | decb187d1 | G362: measured -- PARTIAL: known-H recovery 1.6516 px vs the 1.0 px bar | 1 | docs/evidence/tracking/G362_VERIFY_2026-09-09.md  | no | 3 | unknown |
| C:/Users/neelj/nba-track-a5 | track-a5 | 91d80a74b | S321 attempt 2 fix 1d (sol): absent status/receipt falls through to the S309 rou | 3 | scripts/platformkit/ingame/s321_identity.py scripts/platformkit/ingame/s321_state_builder.py scripts/platformkit/ingame/s321_state_rules.py  | no | 7 | unknown |

NOTE (orchestrator 05:06Z): INCOMPLETE -- 281 of 295 worktrees rowed; disk measured for 67 of 295 (about 70 GB for those alone; the real total is higher). The O1 helper loops (inv.sh + du) were still finishing at 05:06Z and were left to complete on their own. Re-run the inventory when disk matters. Prune only from SAFE TO PRUNE, after the HOLDS UNLANDED WORK rows are landed or rejected.
