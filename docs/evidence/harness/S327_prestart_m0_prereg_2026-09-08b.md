# S327 attempt-2 preregistration: pre-start M0

Purpose: descriptive availability census and output construction only; no calibration comparison is scored.

Kinds: select the latest eligible quote strictly before a known start as `PRE_START`; otherwise the earliest quote from start through 60 seconds as `AT_TIP`; otherwise the earliest later quote as `FIRST_INPLAY`; otherwise `NONE`. When an archive lacks start time, an explicitly labelled archive close source is a proxy only under these same labels.

Candidate generation: a quote can attach only after complete mapped HOME and AWAY agreement with a state event, on the same date when a stable shared event key is unavailable. TEAM AGREEMENT IS REQUIRED for every kind, including proxy kinds and stable-key candidates. The fix-1b single-team `by_date_team` fallback and NBA single-event same-date fallback are removed; neither is identity evidence.

Mapping: use `domains/cross_sport_market/prestart_m0_name_map.json`; retain every unmapped value with its count. Date plus a complete team pair generates a candidate and is never identity by itself.

Control: shuffle only event dates with seed 327, preserving all other fields; report any residual join as a finding.

Dedupe: count all archive-event rows, then retain the first occurrence of each event key for output and census.

Multi-candidate resolution: for a matching date and complete team pair, retain the lexically first event key and count every later candidate as unreachable; never average candidates.

Probability eligibility: explicit market probability fields in [0,1] only; ratings, p0, Elo, models, predictions, and forecasts are excluded.

Archive staging: NONE. Inputs are read locally in parquet row groups.
SEAL sha256 e4a062d52f9afa2d40fef6cd43546f9f1f2a2e462b186f161420f31f23a265d2
