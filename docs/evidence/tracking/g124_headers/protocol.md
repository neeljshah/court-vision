# G124 preregistered selection and cause vocabulary

Written before opening any G124-selected tracking CSV, adapter log, or source-video frame.

## Population and selection

The population is every readable current ledger row whose `status` is `thin`
and whose sport is not in the daemon's `CLIP_SPORTS`, using the daemon's
adapter-registry routing rule. Ledger line order is the only time proxy; no
row count, CSV contents, log text, source presence, or source appearance may
affect selection.

For each sport stratum, retain only rows with a currently readable canonical
`data/tracking/<game_id>/tracking_data.csv`, so that every selected case can
actually be opened. Within each stratum, order by ledger line number and take
the evenly spaced ranks `ceil(i*(m+1)/(k+1))`, where `m` is the number of
eligible rows, `i = 1..k`, and `k` is 3 for baseball and football, 2 for KBO
and MLB, and 1 for every other sport with an eligible row. This is a
content-blind, time-spread selection with a target of at least 12 opened
outputs; if a stratum lacks enough eligible rows, record the shortfall rather
than substituting on contents.

## Mutually exclusive cause vocabulary

1. `non_game_footage`: an eye-checked source frame is predominantly studio,
   statistics, advert, graphic, warm-up, or other non-contest programming;
   the video is readable.
2. `decode_failure_after_open`: the source exists but the adapter log records
   a decoder/open/read failure before usable frames are processed.
3. `adapter_exception_after_header`: the canonical CSV has a header and no
   data rows, and the adapter log records an exception after output creation.
4. `detector_no_observations_on_usable_game`: readable eye-checked contest
   footage, no logged decoder or adapter exception, and no emitted rows.
5. `source_corrupt_or_truncated`: source bytes exist but a decoder cannot
   read a representative interior frame, or the log identifies a corrupt or
   truncated source.
6. `source_missing_or_historically_unattributable`: the source is absent, or
   a current output/log cannot be tied to the historic thin attempt; this is
   not evidence that the adapter failed on usable footage.
7. `insufficient_retained_evidence`: source and relevant historical log are
   absent while the available current material cannot discriminate among the
   preceding causes.

For `non_game_footage`, `detector_no_observations_on_usable_game`, and
`source_corrupt_or_truncated`, G124 will retain an eye-check frame and a
plain-language observation. Each selected outcome receives exactly one label;
the last two categories preserve an explicit unknown rather than inferring a
cause from a header alone.
