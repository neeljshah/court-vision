# S809 adversarial verifier (tier 2) on 6993eeade -- 2026-10-09 (PAPER ONLY)

Verdict: ACCEPT. 13 of 13 meaningful mutants killed by tests/platformkit/execution/test_live_shadow_fit.py (14 passed at the commit).
The verifier restored the file after each mutant, and `git diff --stat` was empty at the end.

## Mutation table
| mutant | result | killed by |
|---|---|---|
| M1 lookback back to plain int (7) | killed | s809_fit_expects |
| M2 EMBARGO_DAYS = 2 | killed | embargo_three_days, reader_rejects, cli_fits, s809_fit_expects |
| M3 EMBARGO_DAYS = 4 | killed | reader_rejects, cli_fits, s809_fit_expects |
| M4 prereg sha from prereg_e | killed | history_refuses_unmanifested, both s809 tests |
| M5 prereg sha from the budget json | killed | s809_fit_expects |
| M6 incomplete count dropped | killed | s809_incomplete |
| M7 count complete nights instead | killed | s809_incomplete |
| M8 cumulative lookback + 1 | killed | s809_fit_expects |
| M9 history_incomplete refusal re-added | killed | s809_incomplete |
| M10 lookback / embargo args swapped | killed | s809_fit_expects |
| M11 cumulative lookback on day-1 | killed | s809_fit_expects |
| M12 count hard-coded 0 | killed | s809_incomplete |
| M13 expected config None | killed | s809_fit_expects |

Not counted as meaningful: a literal 3 for the embargo, and hashing POLICY_PATH instead of producer_args.prereg. Both have the same value today.

## Findings
1. The fit and night configs match term for term. The test captures both configs and asserts they are equal.
2. A pair missing its newest night (N-4) is also consumed now. It is counted in `history_nights_incomplete`, not silent, and the night consumes it the same way. A newest-night guard would be a policy change for both sides, outside S809.
3. Latent, not live: contract reader `embargo_days != 3` literal (live_shadow_fit_contract.py:76); doc policy_sha256 from POLICY_PATH vs history check on producer_args.prereg (same file today); an absent prereg fails the fit closed (FileNotFoundError), while the night only refuses its history.
4. `sources` has no schema check in the contract, so the new key cannot make the reader reject a fit doc.
