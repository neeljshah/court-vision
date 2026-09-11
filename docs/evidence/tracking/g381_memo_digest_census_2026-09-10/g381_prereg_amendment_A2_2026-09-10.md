# G381 preregistration amendment A2 (sealed alone, before run 4)

Run 3 (A1 rules; artifacts kept under `run3_pre_A2/`, memo `memo_run3.md`) classified 1,671 of 2,000 tokens UNRESOLVED.
A spot check of the G372 memo shows two RESOLVER gaps, not memo defects: (i) a memo that names a sealed prereg or amendment
file and prints its SEAL digest (the SHA-256 of that file's bytes ABOVE its `SEAL sha256` line) was UNRESOLVED because rule (d)
only hashed the memo's own bytes above a seal; (ii) an artifact cited by bare basename outside the memo's evidence tree
(`track_daemon.py` = scripts/platformkit/track_daemon.py) was UNRESOLVED because name resolution stopped at the evidence tree.
This amendment adds those two rules and caps the candidates field; token grammar, enumeration, classes, order of the
existing rules and the bar are unchanged.

## Additions to the resolution order

Name resolution gains step (5): the basename searched across the WHOLE landing-commit tree (`git ls-tree -r`), unique match
required; two or more matches = UNRESOLVED (prefix ambiguous is a separate sub-reason; this one is `basename ambiguous`).
Rule (a) gains a seal form, tried immediately after the plain digest at the same commit: if the resolved artifact contains a
line starting `SEAL sha256`, compare the token with the SHA-256 of the bytes above that line, raw and CRLF-normalised
(class IDENTIFIES_AT_LANDING with `form=seal`); the same at HEAD for rule (b).
Rule (d) (ARTIFACT_UNNAMED) also tries the seal form for every sealed file in the evidence tree.
The `candidates` field in unresolved.csv lists at most 10 candidates (path plus first 12 hex of each digest tried).
Run 4 executes the full order (A1 + A2) over the same enumeration at the same merge-base; the second run must diff
byte-identical; run 3 is disclosed in the memo as superseded, never deleted.
SEAL sha256 6e35de55800cc325ecdd57bf6d94015d2d2021477a52fbb6bb5c229286eb7b06
