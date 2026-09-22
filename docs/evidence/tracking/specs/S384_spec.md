GAP S384 | sport all (maker channel) | worktree harness-h44 (master-based) | log cx_s384_markout_quantity_decimal
# Markout quantity stays an exact decimal string on a new result path (verifier NOTE on row S369)

SINGLE PROBLEM: scripts/platformkit/execution/markout_causal.py converts the fill quantity through a float on one result path
(the S369 verifier's reproduction: qty "1e-999" -> remaining_inventory_qty 0.0). Every other quantity in the chain is Decimal end
to end (rows S345 / S357 / S370 / S371); this is the last float quantity between a fill and a fee-netted markout.

BINDING BEFORE-CONDITION: run `python -c "from scripts.platformkit.execution import markout_causal as m; import inspect;
print(inspect.getsource(m))" | grep -n "float(" ` and quote every float conversion of a quantity, fee or size with its line.
The S343 / S354 / S356 / S369 test files pass on master (quote the four pass counts).

CHANGE (owned files: markout_causal.py, NEW tests/platformkit/execution/test_markout_quantity_decimal.py, the memo; edit no other
module; the legacy float field is kept for existing readers):
1. Every quantity, size and fee the module reads is parsed with Decimal(str(x)) or refused (bool, non-finite, negative, empty);
   arithmetic on them is Decimal only; a NEW result field `remaining_inventory_qty_dec` (decimal STRING, exact) is written beside
   the legacy `remaining_inventory_qty` float, and the legacy float is now derived from the Decimal at the very end
   (float(dec)), never the other way round; a quantity that cannot be represented exactly as a float sets a counted
   `float_field_lossy` flag on the result instead of silently rounding. No mark, window, ordering or identity logic changes.
2. Tests: "1e-999" stays exact in the decimal field and flags the float field lossy; "200.47" fractional sizes round-trip; a sum
   of fractional fills equals the exact total; bool / NaN / inf / negative / "" refused with a counted reason; every S343 / S354 /
   S356 / S369 test still passes unchanged (run each file).
3. Memo docs/evidence/harness/S384_markout_quantity_decimal_2026-09-21.md.

CONTROLS: construct tests only, no real archive, no network, no measured markout. ACCEPTANCE: the new test file and the four
landed markout test files pass one at a time; <= 300 LOC; ASCII; contract Q6 vocabulary; the memo ends with a NOT VERIFIED list.

AMENDMENT 1 (2026-09-21; binding; ruling on the conflict the build lane raised). In THIS module fee_units is an INPUT carried from
a recorded fill (ledger data), not a fee the module computes; a recorded maker fill can legitimately carry a fee of exactly zero.
Therefore: a zero fee is ACCEPTED here (the landed S369 test that scores fee_units="0" stays unchanged), while a negative,
non-finite, boolean or unparseable fee is refused with a counted reason. The generic build-prompt sentence "a zero fee is refused"
applies to fees RETURNED BY THE FEE MODULE (rows S370 / S378), not to recorded fill inputs. Everything else in the spec stands.

