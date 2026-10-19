# Pregame versus close data card: <CSV basename>

calibration readout, paper only, not a verdict

- Source: <provider, exact private input paths, market and outcome orientation>
- Licence ledger row: <docs/evidence/LICENCE_LEDGER.md row, status, scope checked>
- Devig method: <proportional or shin; applied before export>
- Exclusions: <join, missing values, chronological fit/holdout split, counts>
- SHA256 of the private source file: <path: sha256; repeat for every input>
- Row count: <exported holdout rows; one unique match_id per game>
- Generated-by command: <exact command, source revision and corpus override>

CSV columns, in order: date_utc, match_id, p_model, p_close_devig, devig_method, y.
The two probabilities and y must describe the same binary outcome. Dates retain
the source's date precision; a date alone does not establish an as-of timestamp.
Only devigged probabilities are exported. Keep full float precision. Record
reference clipping at [1e-6, 1-1e-6] and all excluded denominators above.

The scorer refuses the entire input on validation failures; reason counts can
overlap. Fewer than 500 rows reads INSUFFICIENT. MATCHES_CLOSE means only that
the interval includes zero. It does not establish equal calibration.

NOT VERIFIED: <licence scope, provenance, time ordering, or reproduction still pending>.
