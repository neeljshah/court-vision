# G403 preregistration amendment A1

Status: AMENDMENT, sealed alone. It does not edit `prereg.md` (seal
`fc0b4f458c6fe7bf0661fdfb930ae95da082641f6837b98c3592562e55a1b205`, unchanged). It records the
updated before-condition that the sealed protocol requires before any G403 metric, because one
bound input digest no longer matches the landed bytes.

## The original clause, quoted verbatim from `prereg.md`

> - Required immutable files and expected SHA-256 values: `ratings.csv`
> `3a746f5976cc44f9b86990c97edffcb1191454984f16d153dd2933f14bd20181`; `kappa.csv`
> `808d26134409926c178e7ec628df7f4fad028d7220003bde059c31e7826f96e4`.

> - The finisher may create G403 diagnostic evidence only after the binding before-condition
> passes. Missing audit trail is `PARTIAL`; changed verified bytes require recording the updated
> before-condition and stopping for a new seal.

## What changed and why

G400 landed on master at `ad85fd187` after the lane object `6b1a7601a` that the preregistration
bound. The landing carried G400's own "fix 1c" correction. Measured:

- `ratings.csv` is byte-identical at `6b1a7601a` and at the landed `ad85fd187`:
  `3a746f5976cc44f9b86990c97edffcb1191454984f16d153dd2933f14bd20181`. Unchanged, as sealed.
- `kappa.csv` at `6b1a7601a` is `808d26134409926c178e7ec628df7f4fad028d7220003bde059c31e7826f96e4`
  (the sealed value). At the landed `ad85fd187` it is
  `0c99b667ad7adabe76fe0f7a8ff9bacb30cb332f0f53d89593383073e85b9199`.
- The complete difference between those two objects is two verdict strings:
  row `1,29,0.7568,0.8621,0.6,...` changed `PASS` to `INCOMPLETE`, and row
  `POOLED,299,0.7505,0.8562,0.6,...` changed `PASS` to `INCOMPLETE`. Every `paired_n`, `kappa`,
  `observed_agreement`, `bar` and missingness field is byte-identical in both objects.
- `dev_boxes_v3.csv` matches its sealed value
  `e151f932c3b4bffe84c89aa8fde18f08c346a1e3a6e65d27ed4b36f095b7b4fa` over LF-normalized bytes.
  The working copy carries CRLF only because `core.autocrlf` is `true` in this checkout.

## The amended before-condition

The bound G400 handoff object for G403 is the LANDED `ad85fd187` tree, with
`kappa.csv` = `0c99b667ad7adabe76fe0f7a8ff9bacb30cb332f0f53d89593383073e85b9199`. Every numeric
before-condition the preregistration and the G403 spec name is unchanged and must still reproduce
exactly: 300 sealed keys, 600 archived answers over 20 archives, 299 paired observations, pooled
kappa 0.750519, round 8 n = 30 with kappa 0.360465, round 1 n = 29, 125 both-VISIBLE centre pairs
with median gap 24.021 px, and 288 valid VISIBLE diameter observations. No input was edited to make
it match; the changed bytes are recorded here, not absorbed.

## Scope

This amendment changes one digest and nothing else. Every method, bar, category, control-package
and verdict clause of `prereg.md` stands as sealed.
SEAL sha256 bebc0605404ab1ee958b0bed49de5c0d828c6c7ab42c393574678ca7f3bb44c3