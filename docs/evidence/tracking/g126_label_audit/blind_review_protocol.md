# G126 blind source review protocol

This protocol was applied before opening the selected G111 frame-label rows or
their committed G111 renders. The selected identities come from the fixed G111
manifest. The selection is label-stratified by the helper but its individual
G111 counts are withheld from this file and the reviewer.

For each `audit_id`, the reviewer viewed only the JPEG decoded read-only from
the named source clip at the manifest `source_frame`. A paint corner counts
only where the two boundary lines visibly meet at a physical paint-rectangle
corner. Guessed intersections and line continuations do not count. The output
is the number of source-visible paint corners: 0, 2, or 4.

The resulting `blind_source_judgements.csv` is committed before any join to
G111 labels or committed renders.
