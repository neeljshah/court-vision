# G386 preregistration amendment A1: retaining re-measurement

This amendment changes only the re-measurement retention and receipt sequence.
The Claude finisher, not this fix lane, will run the re-measurement after this
amendment is sealed. The sealed 30-section even draw rule from the original
preregistration remains binding, including preservation of every failed attempt.

For every full_replay_source row, the off-pod PC receiver retains the complete
replay object it reads back at
C:/Users/neelj/nba-ai-system/data/pod_backup_2026-09-10/g386_objects/.
That path is never committed. The receiver receipt records that retained path
and the complete object's SHA-256 so required reader objects retained can be
measured as N/30 off-pod while pod scratch remains below 2 GB.

The order for each attempt is pin, copy, receiver readback digest, receiver
decode of the requested interior frame, then receipt. CAPTURED requires all
four operations to succeed: pin, copy, matching receiver readback digest, and
successful receiver decode of the requested frame before acknowledgement.
Matching bytes that cannot decode receive COPY_UNDECODABLE and are not
CAPTURED. Everything else in the original preregistration remains unchanged.
SEAL sha256 3c092fc62c2af32a6665e53c8348357c3aad3e989646740049d74b4e4d7504a7
