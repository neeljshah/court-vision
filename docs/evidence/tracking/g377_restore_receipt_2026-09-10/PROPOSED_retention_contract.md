# PROPOSED retention contract -- identity before prune

PROPOSAL ONLY. Nothing here is wired, enabled or scheduled. No prune runs, no lifecycle changes,
no flag moves, no `src/` hook, no register write. G377 measured what follows; it authorises nothing.
Section order and content are fixed by `g377_prereg_2026-09-10.md` section 7, sealed before the
measurement, so the proposal cannot be shaped by what the measurement happened to find.

What G377 measured, and why each clause exists, is stated beside the clause. The three failures the
seed review cited (G369 lost 20 of 55 sources at pin time, G368 lost 53 of 59 sections with the six
survivors DIFFERING, G370 saw 25 of 118 pinned tables mutate under the live daemon) share one
shape: a byte was released, moved or overwritten before any receiver could prove it held a copy.

## 1. Identity before prune

A file becomes a PRUNE CANDIDATE by age, quota or any other producer-side rule. A prune candidate
becomes ELIGIBLE only when a RECEIVER ACKNOWLEDGEMENT (section 2) exists for its exact content
identity. No acknowledgement, no eligibility. The gate FAILS CLOSED: an unknown, unreadable or
absent acknowledgement is not eligibility, and a missing acknowledgement record is never read as a
pass (contract B3 -- missing is not bad, and it is certainly not permission).

Eligibility is a property of BYTES, never of a path. A path whose content changed since its
acknowledgement is a new identity (section 4) and is not eligible under the old one.

Measured basis: G377 restored 1,378 of 1,391 named files off-pod, and 1,377 verified byte-exact.
Every one of the 13 that could not be restored was a path with no off-pod acknowledgement of any
kind -- a pod scratch root, a pod worktree, or a per-section table basename with no single identity.
The rule that would have saved them is the rule that they be acknowledged before release.

## 2. Receiver acknowledgement

The record a receiver writes, per file, before that file may be considered held:

    path                the producer-side path, verbatim
    bytes               size at read time
    sha256              digest of the exact bytes read back FROM THE RECEIVER's copy, not from the producer
    source              which store the copy came from
    readback_verdict    VERIFIED only when the digest of the receiver's re-read copy equals the source digest
    utc                 when the readback completed

A digest recorded by the PRODUCER is not an acknowledgement. G377's V2 check is deliberately a
READBACK: bytes are written to the receiver and then read off the receiver's disk again before the
digest is taken. A producer-side digest proves the producer could read its own file, which is the
one thing never in doubt.

## 3. Reader leases for sealed sets

A sealed set (a reference, a rated corpus, a pinned source manifest) declares its READERS. While a
lease is open, no member of the set is eligible, at any age, under any quota pressure. A lease is
released explicitly by the row that opened it, never by a timer.

Measured basis: G377's manifest is exactly this reader list, computed mechanically from what each
memo names and each reader module opens. Two lease defects it found and named:

    - G367's 56 committed `sheets/*.jpg` appear in NO reader lease: neither its memo nor any literal
      in its five modules names them, so the sealed manifest draw for the eye check found no
      restorable native pixel for that closure at all. Pixels a row depends on but never names are
      exactly the pixels an age rule deletes first.
    - G370's `tracking_data.csv` and `ball_tracking.csv` are opened by `g370_manifest.py:42-43`,
      `g370_premise.py:26` and `g370_scorer.py:138` as BASENAMES. A basename is not an identity, so
      no lease can bind to it and no acknowledgement can cover it. The 118 tables those names stood
      for are pinned with digests inside `fresh_sections.csv` -- which restored and verified -- but
      the reader itself names nothing a retention rule can protect.

## 4. Versioned identities

A source that is moved, re-supplied, re-fetched or appended to gets a NEW version. It never inherits
the old identity, and the old identity is never marked satisfied by the new bytes. A re-fetch is a
new identity by construction: it is a different read of a possibly different upstream object.

Measured basis, directly observed by this row and not quoted from another: the single path
`/workspace/data/tracking/track_daemon_ledger.jsonl` answered with THREE different sha256 values
inside one session -- `4333934b...` (the synced 2026-09-10 receiver copy at 1,510,452 bytes,
1,281 lines), `4a22a981...` and `fc766205...` (the pod's live file, 1,523,029 bytes, 1,293 lines at
the last read). The receiver's own copy also changed between two G377 runs as the sync advanced. An
append-only file under a running producer has no stable identity, so a retention rule keyed to its
path can neither acknowledge it nor protect it. It must be versioned by content, or by an explicit
sealed checkpoint, before any rule may reason about it.

A second, quieter case: three digests in the landed G367 memo -- `g367_premise.json`,
`g367_search.json`, `summary.json` -- do not match the bytes committed under those names, while the
two CSV digests in the same table do. A recorded digest that no longer identifies its file is an
acknowledgement that has silently expired, and only a versioned identity makes that visible.

## 5. Byte ledger

An allowance, not a licence to delete. Derived from the two measured quantities available today: the
roughly 41 GB pod volume quota and the roughly 1.8 GB per hour of table growth the tracking store
produces while the daemon runs. At that rate a full volume is reached in under a day of unbounded
intake, which is why the first lever is INTAKE, not evidence:

    reserved_evidence   bytes under an open reader lease, plus every unacknowledged byte. Never spendable.
    working_headroom    the remainder. When it falls below one hour of growth (about 1.8 GB), the
                        producer's INTAKE is bounded -- fewer concurrent sections, or a paused feeder --
                        and evidence is not touched.
    receipt_cost        G377's whole four-closure restore is 177,007,159 bytes for 1,378 files, about
                        0.43 pct of the quota. Holding the receipt is cheap; the growth is the problem.

At quota pressure the contract bounds writes and intake. It never destroys evidence to make room.
This is contract D2 stated as an allowance rather than as a prohibition.

## 6. What this proposal does NOT do

It authorises no deletion, no prune, no retirement and no lifecycle change. It is not a claim that
anything already lost is recoverable -- G377 restored nothing that was gone, it only proved which
named bytes are still held and which are not. It makes no tracking-quality claim, and adopting it
would not by itself improve any measured number. It is a rule about when a byte may be released,
and its only promise is that a byte released under it was provably held somewhere else first.
