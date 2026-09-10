# G369 PREREG AMENDMENT 2 - required deterministic artifacts

This amendment is sealed before any G369 live-ledger count, PIN, alignment, export, or
comparison. It adds only commands to emit the spec-required `summary.json` and
`SHA256SUMS.txt`; original preregistration and Amendment 1 rules remain in force unchanged.

After the two export commands in the original preregistration, the finisher also runs:

    $M summary --sources $OUT/sources.csv --attempts $OUT/attempts.csv \
      --manifests $OUT/manifests.json --alignment $OUT/alignment.csv --out $OUT
    $M hashes --out $OUT

`summary.json` is the same deterministic export summary. `SHA256SUMS.txt` lists every
already-produced evidence file except itself. These commands add required artifacts; they do
not compute a comparison or alter a bar, threshold, sampling rule, or source-binding field.

SEAL RULE: the hex on the last line is the SHA-256 of every byte above that line, after
normalising CRLF to LF, including the newline ending the preceding line.
SEAL sha256 9fb3fa36292ba398ad3744c759a29010fd15d579f329d852e99bda3f7335227c
