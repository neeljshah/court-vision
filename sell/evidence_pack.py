"""sell.evidence_pack -- the one-command buyer due-diligence pack.

build_pack(out_dir) assembles, into data/frontend/sell/evidence_pack/ :
  * track_record.signed.json -- the signed CLV + calibration track record (REUSES
    sell.track_record; CLV is never recomputed; honesty-linted before write).
  * reproduce.json           -- the HONEST verdicts of every buyer-checkable proof
    (governance 0/1, eval-gate leak-free walk-forward, the in-game proof with
    vs_close UNPROVEN, the track-record signature). Never upgraded.
  * manifest.json            -- a stable sha256 manifest over the packed artifacts
    so any tampering is detectable (sell.pack_manifest).
  * methodology.json         -- the binding honesty framing (what is / is NOT
    claimed) carried alongside the evidence.

The whole pack is honesty-linted before any file is written: a banned $-edge key
or a retracted number RAISES and nothing is written. Files are written atomically
(tmp + os.replace). `python -m sell.evidence_pack` builds the pack.

HONESTY: no dollar / ROI / P&L field anywhere; edge_claimed pinned False; every
surfaced number is real (from the vetted scoreboard / proofs) or labelled
unavailable. The methodology note explicitly states the NON-claims (no $-edge,
in-game vs-close UNPROVEN, markets efficient pregame).

INVARIANTS: build only under sell/; <=300 LOC; ASCII only; no secrets in code;
never writes data/registry/; never pushes origin; no network.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from governance import honesty_linter as _linter

from sell import pack_manifest as _manifest
from sell.reproduce import REPRODUCE_COMMAND, reproduce_all
from sell.track_record import build_track_record, sign_track_record
from sell.trackrecord_schema import DEFAULT_METHODOLOGY_NOTE

EVIDENCE_PACK_VERSION = "sell.evidence_pack.v1"

_HERE = Path(__file__).resolve().parent
DEFAULT_PACK_DIR = (
    _HERE.parent / "data" / "frontend" / "sell" / "evidence_pack")

#: Artifact relative names inside the pack (manifest keys + on-disk filenames).
TRACK_RECORD_NAME = "track_record.signed.json"
REPRODUCE_NAME = "reproduce.json"
METHODOLOGY_NAME = "methodology.json"
MANIFEST_NAME = "manifest.json"

#: The explicit NON-claims that make this an honest buyer-facing pack.
NOT_CLAIMED = [
    "No dollar ROI / P&L / edge is claimed anywhere (no $-edge field by design).",
    "In-game gain is CALIBRATION vs a base-rate prior; vs the close it is UNPROVEN "
    "(no in-play odds captured) -- not a realized market edge.",
    "Pregame team-strength markets are efficient: the model MATCHES the devigged "
    "close within noise; an honest MATCHES_CLOSE / BEHIND is a success, not a fail.",
]
CLAIMED = [
    "Out-of-sample calibration (Brier / ECE) under a leak-free, walk-forward, "
    "truncation-invariant, reproducible methodology.",
    "Closing-line-value discipline: a true-close-graded CLV ledger; positive "
    "mean_clv_pct means bets were recorded at a better number than the close.",
    "A signed, tamper-evident track record and a one-command reproducibility pack.",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_OPAQUE = "REDACTED_OPAQUE_HASH"


def _redact_signature(tr: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of a signed track record with the opaque MAC value redacted."""
    out = dict(tr)
    sig = out.get("signature")
    if isinstance(sig, dict):
        sig = dict(sig)
        sig["value"] = _OPAQUE if sig.get("value") else None
        out["signature"] = sig
    return out


def _redact_manifest(man: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of a manifest with every opaque sha256 digest redacted."""
    out = dict(man)
    if out.get("manifest_sha256"):
        out["manifest_sha256"] = _OPAQUE
    arts = out.get("artifacts")
    if isinstance(arts, list):
        red = []
        for e in arts:
            if isinstance(e, dict):
                e = dict(e)
                if e.get("sha256"):
                    e["sha256"] = _OPAQUE
            red.append(e)
        out["artifacts"] = red
    return out


def _lint_view(pack: Dict[str, Any]) -> Dict[str, Any]:
    """A copy of *pack* with every opaque cryptographic digest redacted.

    The signed track record's HMAC value and the manifest's sha256 digests are
    cryptographic hashes, not presented results; their hex can incidentally
    contain a banned-number substring (e.g. "54" flanked by hex letters) and
    false-positive the honesty linter. We redact ONLY those opaque digests --
    every claim, number, key, and verdict stays intact -- so honesty is fully
    enforced on content without random digest false fails.
    """
    if not isinstance(pack, dict):
        return pack
    view = dict(pack)
    tr = view.get(TRACK_RECORD_NAME)
    if isinstance(tr, dict):
        view[TRACK_RECORD_NAME] = _redact_signature(tr)
    man = view.get(MANIFEST_NAME)
    if isinstance(man, dict):
        view[MANIFEST_NAME] = _redact_manifest(man)
    return view


def _atomic_write_text(dest: Path, payload: str) -> None:
    """Write *payload* to *dest* atomically via tmp file + os.replace."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(dest.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp_name, str(dest))
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _methodology_obj() -> Dict[str, Any]:
    """The binding honesty framing carried alongside the evidence."""
    return {
        "version": EVIDENCE_PACK_VERSION,
        "note": DEFAULT_METHODOLOGY_NOTE,
        "claimed": list(CLAIMED),
        "not_claimed": list(NOT_CLAIMED),
        "reproduce_command": REPRODUCE_COMMAND,
        "edge_claimed": False,
    }


def assemble_pack(*, secret: Optional[str] = None,
                  track_record_path: Optional[Path] = None,
                  governance_kwargs: Optional[Dict[str, Any]] = None,
                  track_record: Optional[Dict[str, Any]] = None,
                  ) -> Dict[str, Any]:
    """Build the in-memory pack objects + manifest. No disk writes. Honesty-linted.

    Returns the dict of named artifact objects PLUS the manifest, all keyed by
    their pack-relative name. RAISES (honesty_linter.assert_clean) before returning
    if any artifact carries a banned $-edge key or a retracted number.
    An already-signed *track_record* may be passed so a caller (docs_gen) that
    also renders the record uses ONE object -- otherwise a second build here
    gets a different generated_at/signature than the one rendered.
    """
    # Signed CLV track record (REUSES the vetted scoreboard; CLV not recomputed;
    # sign_track_record honesty-lints it and raises on any violation).
    if track_record is not None:
        signed_tr = track_record
    else:
        tr = build_track_record()
        signed_tr = sign_track_record(tr, secret=secret)

    # Verify the pack's OWN freshly-signed track record (not a stale on-disk one).
    verdicts = reproduce_all(
        secret=secret, track_record_path=track_record_path,
        track_record=signed_tr, governance_kwargs=governance_kwargs)
    methodology = _methodology_obj()

    objects: Dict[str, Any] = {
        TRACK_RECORD_NAME: signed_tr,
        REPRODUCE_NAME: verdicts,
        METHODOLOGY_NAME: methodology,
    }
    # Hash the exact canonical bytes that will be written -> manifest agrees with
    # the on-disk files. The manifest itself is added (without self-reference).
    manifest = _manifest.manifest_for_objects(objects)
    manifest = dict(manifest)
    manifest["generated_at"] = _now_iso()
    manifest["pack_version"] = EVIDENCE_PACK_VERSION

    pack = dict(objects)
    pack[MANIFEST_NAME] = manifest

    # Whole-pack honesty gate: nothing dishonest ships. Raises on a violation.
    # The opaque MAC hex inside the signed track record is redacted before the
    # lint (a cryptographic digest is not a presented result number and can
    # randomly contain a banned-number substring); all content is still linted.
    _linter.assert_clean(_lint_view(pack))
    return pack


def build_pack(out_dir: Optional[Path] = None, *,
               secret: Optional[str] = None,
               track_record_path: Optional[Path] = None,
               governance_kwargs: Optional[Dict[str, Any]] = None,
               ) -> Dict[str, Path]:
    """Assemble + atomically write the evidence pack to *out_dir*.

    Returns a map of artifact name -> written path. The pack is honesty-linted in
    assemble_pack BEFORE any file is written, so a dishonest pack never reaches
    disk. CLV is never recomputed here; verdicts are surfaced unmodified.
    """
    dest_dir = Path(out_dir) if out_dir is not None else DEFAULT_PACK_DIR
    pack = assemble_pack(secret=secret, track_record_path=track_record_path,
                         governance_kwargs=governance_kwargs)
    written: Dict[str, Path] = {}
    # Stable order: manifest last so a reader can hash the others against it.
    for name in [TRACK_RECORD_NAME, REPRODUCE_NAME, METHODOLOGY_NAME,
                 MANIFEST_NAME]:
        dest = dest_dir / name
        payload = json.dumps(pack[name], indent=2, sort_keys=True,
                             default=str) + "\n"
        _atomic_write_text(dest, payload)
        written[name] = dest
    return written


def main(argv: Optional[list] = None) -> int:
    """CLI entry: build the pack to DEFAULT_PACK_DIR. Returns a process exit code."""
    written = build_pack()
    sys.stderr.write("wrote evidence pack (%d artifacts) -> %s\n"
                     % (len(written), DEFAULT_PACK_DIR))
    for name, path in sorted(written.items()):
        sys.stderr.write("  %-28s %s\n" % (name, path))
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())


__all__ = [
    "EVIDENCE_PACK_VERSION",
    "DEFAULT_PACK_DIR",
    "TRACK_RECORD_NAME",
    "REPRODUCE_NAME",
    "METHODOLOGY_NAME",
    "MANIFEST_NAME",
    "CLAIMED",
    "NOT_CLAIMED",
    "assemble_pack",
    "build_pack",
    "main",
]
