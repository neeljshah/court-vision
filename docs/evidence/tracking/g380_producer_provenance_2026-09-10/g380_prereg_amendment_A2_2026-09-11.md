# G380 preregistration amendment A2 -- restore the sealed overlay bar, 2026-09-11

The sealed preregistration (`prereg.md`, SEAL
d04ee2c4873c621944a2596131d0603dd32d9e3533fbe0fc41274d6e76471c95) is NOT edited by this
amendment, and neither is amendment A1 (SEAL
903dabcb737d97860bb9fdaa094bdd8293a958e87a90c2fe10a0e661c60da282). A sealed file is never
edited; a correction is a new sealed file. This amendment MOVES NO BAR. It RESTORES one.

## What A1 got wrong

A1 restated the sealed bars in its section "Bars, restated verbatim and unmoved" and, in the
last clause of line 52, wrote `30 evenly spaced source-coloured overlays including HELD and
CLAMP where they occur`. The three words `where they occur` are not in the sealed text. They
turn an unconditional eye-check bar into a conditional one, which is exactly the relaxation
contract clause Q3 forbids and clause B10 rejects. The codex-sol verification of attempt 1
caught this and rejected on B10 and Q3. The finding is correct and is accepted here.

## The withdrawal

The clause ` where they occur` in amendment A1 line 52 is WITHDRAWN. It never had effect: no
number in this row was ever scored against the weakened form, and the eye check is reported
against the sealed form below.

The sealed eye-check bar, restored verbatim from `prereg.md` line 50:

    The 30 source-coloured overlays must be evenly spaced and include HELD and CLAMP.

The remaining sealed bars, restored verbatim from `prereg.md` lines 47-49:

    Bars are unchanged: trace-label agreement 1.000000; receipt-trace agreement
    1.000000; unchanged-field differences 0; paired median seconds ratio at most 1.10
    on n >= 30; and live receipt coverage 1.000 on at least 30 sections from 10
    videos.

An unmet bar is reported unmet -- PARTIAL, NOT VALIDATED, or CLOSED AT LIMIT with the measured
reason -- and is never lowered to fit the measurement.

## What of A1 still stands

A1's ONLY other content is its amended SAMPLING FRAME: sections are drawn from the pod footage
corpus as it rotates instead of from a frozen name list, because the quota guard deleted 22 of
30 sealed names mid-run. That change stands unaltered, together with A1's record of the
hyphen-leading `game_id` defect. Nothing else in A1 is withdrawn, and A1's own seal still
verifies over A1's unedited bytes.
SEAL sha256 8a331a042b61f87743f08ff1bb328bedd8bac3fdebbf937f5fddd4fa726cf571
