# S197 system-ledger SHA annotation

Verdict: ACCEPT. Every row flagged by the S191 audit now ends in a resolvable
`landed:<sha>` token. No flagged row required an `uncommitted:` label.

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.

## Premise and result

The S191 utility was run before editing. The denominator had grown from the
spec's 390 data lines to 397, while the untraceable set remained the same 66
physical lines. Concurrent S177 and S179 lanes appended two data rows during
S197, so the final reproduction denominator is 399. Those rows were not edited.

| Metric | Spec | Before S197 | After S197 |
|---|---:|---:|---:|
| Data lines | 390 | 397 | 399 |
| Untraceable data lines | 66 | 66 | 0 |
| Final field resolves | 284 | 286 | 352 |
| Hook rows resolving | 199/199 | 201/201 | 201/201 |
| `uncommitted:` labels appended | n/a | n/a | 0 |

Before line numbers: 219, 225, 226, 230, 231, 232, 233, 234, 235, 236,
238, 239, 242, 243, 245, 248, 249, 252, 255, 257, 258, 259, 261, 264,
266, 267, 268, 271, 275, 278, 280, 282, 285, 288, 289, 292, 294, 297,
298, 301, 303, 306, 307, 312, 314, 316, 317, 320, 322, 325, 326, 328,
331, 334, 335, 339, 340, 345, 346, 353, 354, 356, 361, 362, 364, 370.

After line numbers: none.

## Tokens appended

The named-memo method selected the commit that added the memo named by the
row. A subject candidate was retained only when the commit also touched the
ledger. Otherwise, the fallback used `git log -S` with a distinctive phrase
from the row; every fallback commit touches the ledger.

| Line | S-id | Token appended | How found |
|---:|---|---|---|
| 219 | S16b | `landed:054eea081a34af5d8fde0396d334f8e3a5d3869a` | named memo add commit |
| 225 | S75 | `landed:0fa623edb3a5bbfd614aa4d8f15934dac3609e41` | named memo add commit |
| 226 | S75 | `landed:96f40bda9412eb6a9122bc7cb2d4b6de3514e36c` | S-id/verdict subject; commit touches ledger |
| 230 | S80 | `landed:8fafd86474267a427479e229eb671b74f131a89a` | named memo add commit |
| 231 | S79 | `landed:72fa65c7006201d9d03b81902044ac9c1c9fdc2c` | named memo add commit |
| 232 | S83 | `landed:14e3e78a1b201be7e47592087a25e3d76cea73bf` | named memo add commit |
| 233 | S84 | `landed:9739463dd4b49a311f7ddd8af87da0b55a84b5e0` | named memo add commit |
| 234 | S87 | `landed:71a477e415558d6d83c82b064a77d0efcfc5b709` | named memo add commit |
| 235 | S82 | `landed:e391e3f4ed89285da6d8413efef5dd15c7f355a4` | named memo add commit |
| 236 | S86 | `landed:c05e8a06707de466d19f600f522db0dbf89dc3f4` | named memo add commit |
| 238 | S89 | `landed:bd58bad130e29022e451dd4f80f747ec2adc8e31` | named memo add commit |
| 239 | S89 | `landed:b4feb155c8038fdf03ab59daae4484456e4decbd` | distinctive phrase via `git log -S`; commit touches ledger |
| 242 | S87b | `landed:c67a5851a5827cde7601a81cd5f505afbdeacaec` | named memo add commit |
| 243 | S93 | `landed:a5e2e7f45ae2dd4b4c3146453a849c63ebc267c3` | named memo add commit |
| 245 | S94 | `landed:d47b22162279efdd50cd927682bc8a3192d27d59` | named memo add commit |
| 248 | S95 | `landed:42b4f78e382777516925682b20f1544a05d3949d` | named memo add commit |
| 249 | S97 | `landed:3236654fbdec703f015e9265b33b766bd03abea3` | named memo add commit |
| 252 | S96 | `landed:e8cca60c1d1b57bded4d5fd48206d687cfc88937` | named memo add commit |
| 255 | S98 | `landed:f517fbb9bc4a17c87c969c8f3a0e0751494e5ece` | named memo add commit |
| 257 | S101 | `landed:7c7991b4ed53b2876b01b71bd26f2f64b547767d` | named memo add commit |
| 258 | S103 | `landed:be4abcb1726d7a2e1d19f41b2ccb93dbf6949555` | named memo add commit |
| 259 | S99 | `landed:a6c246a2f7040a0a4bc76c4b64f9828ce5cadd2c` | named memo add commit |
| 261 | S100 | `landed:c8acbd78c148b7f1c979f46508a0f4e0f056d310` | named memo add commit |
| 264 | S104 | `landed:470ae3d13d72f09c50dec87223bfb93e31d787f7` | named memo add commit |
| 266 | S102 | `landed:875e43541d73daf4112fbe4487e914b0fa47b267` | named memo add commit |
| 267 | S105 | `landed:a325e870a5260c9906a846cefe0ff15539ec725b` | named memo add commit |
| 268 | S106 | `landed:34c90bc9930ba74156d27287f2c0048fbf5bee7d` | named memo add commit |
| 271 | S107 | `landed:5863d3bb44efe29b587267f57ef5391f613cde9d` | distinctive phrase via `git log -S`; commit touches ledger |
| 275 | S85 | `landed:3ce89e092deaa798479f975b29b64b966a047f36` | named memo add commit |
| 278 | S81 | `landed:80fce7b4108687af83d699115a75495afef20de5` | named memo add commit |
| 280 | S85 | `landed:637af56dd34a4a080e4a665823943bec00b42c63` | distinctive phrase via `git log -S`; commit touches ledger |
| 282 | S112 | `landed:a58c90f4cdad724066070b24a496508c9a361fd3` | named memo add commit |
| 285 | S111 | `landed:41d2a4c62dcbed900e8afc245d6d231c7810ad2d` | named memo add commit |
| 288 | S115 | `landed:d37b6c4bad259468ebc950ec95cca9c8cca0e8d5` | S-id/verdict subject; commit touches ledger |
| 289 | S115 | `landed:fc8014d3c8ebd33b82284693a4ae98c78737be2a` | named memo add commit |
| 292 | S113 | `landed:0dae6fc4010b7276a401f6f7a29e695a70aa407d` | named memo add commit |
| 294 | S116 | `landed:3c4aca8711cc12f047c9d1ac6446c24d8a9cb274` | distinctive phrase via `git log -S`; commit touches ledger |
| 297 | S113 | `landed:21b12b15ee043078266187633529b20ceabd8f01` | distinctive phrase via `git log -S`; commit touches ledger |
| 298 | S117 | `landed:aafe17759154745914ac29a41b9a1f1e41461979` | named memo add commit |
| 301 | S119 | `landed:d6efd2f36165f56bf4fe4dabf4d6bd2cb71f0fec` | S-id/verdict subject; commit touches ledger |
| 303 | S114 | `landed:575a4d5c9c8767d35ea64ed7d9e26741c0f21810` | named memo add commit |
| 306 | S92 | `landed:464f5e150bf427a77bf447ce8557823e386e7177` | named memo add commit |
| 307 | S120 | `landed:464f5e150bf427a77bf447ce8557823e386e7177` | distinctive phrase via `git log -S`; commit touches ledger |
| 312 | S121 | `landed:d71f411fbb03356e05209b4d6e22050a4b44c4ee` | named memo add commit |
| 314 | S123 | `landed:9daca0460ca6844069934ad6c7994be8d980a954` | named memo add commit |
| 316 | S134+S135+S130 | `landed:e870ee6001636900e8b4e604d436053ae00e23b8` | named memo add commit |
| 317 | S122 | `landed:3b0a7f3215a15e86e874c22e9420359d1b42dafc` | named memo add commit |
| 320 | S134 | `landed:85f6c038c0c23acd3ccfcd6b9bef978f0012f95d` | distinctive phrase via `git log -S`; commit touches ledger |
| 322 | S132+S133 | `landed:4928b337b044d11a2b3613bf5460e2469937415f` | named memo add commit |
| 325 | S132 | `landed:594fa7970e1e3293d39d98e4991394d44736c5d3` | distinctive phrase via `git log -S`; commit touches ledger |
| 326 | S124+S125+S126+S131 | `landed:0c9b9d8d761669648fd56ab10bcacc12cb5e76b0` | named memo add commit |
| 328 | S136 | `landed:60757655c84580a19e36e7811995d7c68973d484` | named memo add commit |
| 331 | S128+S129 | `landed:689a2ecf8519bf328526f99c6799a814a19a7798` | named memo add commit |
| 334 | S136b | `landed:cb9c82dc7c2ac53a0240c3d239915c6fbaef092c` | distinctive phrase via `git log -S`; commit touches ledger |
| 335 | S126+S124 | `landed:857d87e8f847b4dd99e2b0d2bc60842f6cc8e8a6` | named memo add commit |
| 339 | S137 | `landed:9bd7e0552555678948049a19ad479113b578ce7e` | named memo add commit |
| 340 | S78 | `landed:04f115b71f78047c30dcd0b8e1a79aecb27381af` | distinctive phrase via `git log -S`; commit touches ledger |
| 345 | S143 | `landed:bc778706be492ced65ed9e2845e9418ba1bc6337` | named memo add commit |
| 346 | S142 | `landed:663bb104f51e56472179138dfc69a1a13cc03c45` | named memo add commit |
| 353 | n/a (POD) | `landed:382b5f8f8d2e6f301882f54943a0d3796e4600ee` | distinctive phrase via `git log -S`; commit touches ledger |
| 354 | S148 | `landed:d0fff4010a5f9a16e38287f61c8ebfb7ca66859d` | named memo add commit |
| 356 | n/a (POD) | `landed:b7a858f029a78417b50e21d18cc74e98b33144b7` | distinctive phrase via `git log -S`; commit touches ledger |
| 361 | n/a (CLOSE) | `landed:5e882b8811f0e1620f7d19d19f8deb5deef59446` | distinctive phrase via `git log -S`; commit touches ledger |
| 362 | S153 | `landed:35ae9d3271e99ed68b45cec5a764299b1afb2f61` | named memo add commit |
| 364 | S19+S55 | `landed:6b0fd938af9af0797717fa294b7fc40cdb838c26` | distinctive phrase via `git log -S`; commit touches ledger |
| 370 | S35 | `landed:1ea46df786e964c8794891825ca280cc08446da8` | S-id/verdict subject; commit touches ledger |

Recovery split: 48 named memo add commits, 4 S-id/verdict subject commits
that touch the ledger, 14 distinctive-phrase ledger commits, and 0
`uncommitted:` labels.

## Reproduction and invariants

Run in the main repository:

```text
python scripts/platformkit/tracking/ledger_sha_audit.py
python -m pytest scripts/platformkit/tracking/test_ledger_sha_audit.py -q -p no:cacheprovider
```

The focused test passed: `1 passed in 3.59s`.

An exact line comparison against `HEAD` after the concurrent S177 and S179
rows were isolated found 66 suffix-only target edits, 340 byte-identical
non-target lines, 406 physical lines, and 0 unresolvable SHAs. The audit's
final run found 0 untraceable rows out of 399 data rows and 201 of 201 hook rows
resolving. No threshold, register row, FWER ledger row, or file under `data/`
was changed by S197.

The audit utility's `--fix` mode emits a bare SHA suffix. S197 added the
required literal `landed:` prefix to each of those newly appended suffixes;
the final ledger diff contains only the required ` | landed:<sha>` additions.

## Contract self-check

- B1 and Q7: all 398 dated rows are enumerated; no sample or exclusion exists.
- B2-B6: no schema, reader, gate, claim lifecycle, deploy, import, or module changed.
- B7-B9: there are no renders, fitted residuals, or recycled units.
- B10 and Q3: the zero-untraceable bar and all thresholds are unchanged.
- Q1, Q2, Q4, Q5, and Q9: no scored comparison, charged trial, OOS model,
  AHEAD verdict, or paired-loss claim exists.
- Q6: calibration language only; no performance claim is made.
- Q8: the premise was re-measured before editing and confirmed at 66/397.

## NOT VERIFIED

- The verifier's eight-token spot check remains verifier work.
- No pod operation, deployment, register edit, or commit was performed by S197.
