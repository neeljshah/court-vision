# S276 erratum: preserve prior dated artifacts

The prior dated S276 memo and JSON are restored byte-for-byte to their HEAD
versions. Their git blob identifiers are respectively
`d5e4def7049835e17c3dcbc967ea6191af41f566` and
`91bc49e6529110e17af48e09c3400c3a2194a652`.

The attempted in-place changes are not evidence. S276 remains REJECT because
its five equal-date CPCV groups did not use the fixed six S86 tick-balanced
blocks. S294 is the separate, sealed, additive replay that applies the
six-block correction and writes new dated archives.

No ledger, register, data path, feature flag, or deployed pod tree was
modified by this erratum.
