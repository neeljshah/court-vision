G405 fix 1b -- DISCARDED probe attempt A (retained unmodified, used by nothing).
The first fix-1b probe pass crashed on a null -J metadata payload after 7 listings
and 6 metadata requests. No receipt file had been flushed, so the partial outputs
could not be bound to argv/timing/returncodes and the whole pass was discarded; the
helper was fixed (null payload guard plus receipts written after every probe) and the
pass restarted from draw_j=0. Every landed number comes from the restarted pass in
../raw_formats, ../metadata and ../runtime_receipts/probe_receipts.json.
No error was erased: ../common_receipts/attempt_a_vs_b.txt recomputes these 7 sources
from these bytes and gets the identical classification 7/7, including the inaccessible
source mAl_gEPhp3s, which was UNKNOWN in both passes.
