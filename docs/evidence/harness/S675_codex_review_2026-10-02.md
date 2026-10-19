**S675 - HOLD**

- **Constant decimal series can receive BETTER.** `scripts/platformkit/eval_gate/multiplicity_haircut.py:69` recognizes zero variance only through floating-point standard deviation. Equal values such as three `0.1` game means can acquire tiny positive variance from rounding, creating an enormous statistic and passing the combined checks at line 123. Fix: return raw p=1 when all game means are exactly equal, retaining the arm in K. Add `[0.1] * 3`; `scripts/platformkit/eval_gate/test_multiplicity_haircut.py:68` tests only `[0.2] * 40`. This finding is static numerical analysis, not an executed reproduction.
- **CRLF-sensitive provenance test.** `scripts/platformkit/eval_gate/test_multiplicity_haircut.py:99` hashes raw source CSV bytes against an LF digest. Fix: hash LF-normalized bytes and identify the digest accordingly.
- **Python 3.10 timestamp incompatibility.** `scripts/platformkit/eval_gate/multiplicity_haircut.py:156` passes terminal-`Z` timestamps directly to `datetime.fromisoformat`, which the specified laptop Python 3.10 does not accept. Fix: normalize terminal `Z` to `+00:00` and test equivalence.

No unlanded dependency found.

| S675 | HOLD | None | Constant series can receive BETTER | S |
Keep S675, S676, S671, S670, and S698 held pending correction and review. Once cleared, those first four are independent; S698 must follow corrected S670.
