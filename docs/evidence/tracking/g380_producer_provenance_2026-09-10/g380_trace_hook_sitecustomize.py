"""G380 independent import-time trace hook (never imported by the producer).

Placed on PYTHONPATH so CPython's site initialisation imports it before any
producer module exists.  It wraps the provenance module the moment it is first
imported, so the trace is produced by code the patch does not know about and can
be diffed row by row against the labels the producer stamped into its CSV.

  A,<tick>                           the producer evaluated one attempt (A3: before
                                     any row filter, so a tick that emits no row is here)
  S,<slot>,<tick>,<label>,<branch>,<event>   a branch wrote a position
  L,<slot>,<tick>,<label>,<branch>,<event>   an emitted row asked for its label
  R,<in_label>,<out_label>,<moved>   that row's final label after the subpixel test
"""
import atexit
import builtins
import os

_PATH = os.environ.get("G380_TRACE")

if _PATH:
    _rows = []

    def _install(module):
        module._g380_traced = True
        real_stamp, real_label = module.stamp, module.label_for
        real_resolve = module.resolve_emitted
        real_drop = module.drop

        def stamp(store, slot, timestamp, label, branch, matched_event=""):
            _rows.append("S,%d,%d,%s,%s,%s"
                         % (int(slot), int(timestamp), label, branch, matched_event))
            return real_stamp(store, slot, timestamp, label, branch, matched_event)

        def label_for(store, slot, timestamp):
            out = real_label(store, slot, timestamp)
            _rows.append("L,%d,%d,%s,%s,%s"
                         % (int(slot), int(timestamp), out[0], out[1], out[2]))
            return out

        def resolve_emitted(label, branch, prev_int, cur_int):
            out = real_resolve(label, branch, prev_int, cur_int)
            _rows.append("R,%s,%s,%d" % (label, out[0], int(prev_int != cur_int)))
            return out

        def drop(store, slot, timestamp):
            _rows.append("D,%d,%d" % (int(slot), int(timestamp)))
            return real_drop(store, slot, timestamp)

        real_attempt = getattr(module, "note_attempt", None)

        def note_attempt(store, timestamp):
            _rows.append("A,%d" % int(timestamp))
            return real_attempt(store, timestamp)

        if real_attempt is not None:
            module.note_attempt = note_attempt
        module.drop = drop
        module.stamp, module.label_for = stamp, label_for
        module.resolve_emitted = resolve_emitted

    def _dump():
        try:
            with open(_PATH, "w", encoding="ascii") as handle:
                handle.write("\n".join(_rows) + "\n")
        except OSError:
            pass

    _real_import = builtins.__import__

    def _hooked(name, globals=None, locals=None, fromlist=(), level=0):
        module = _real_import(name, globals, locals, fromlist, level)
        target = getattr(module, "g380_provenance", None) \
            if name.endswith("tracking") else (module if name.endswith("g380_provenance") else None)
        if target is not None and getattr(target, "POSITION_SOURCES", None) is not None \
                and not getattr(target, "_g380_traced", False):
            _install(target)
        return module

    builtins.__import__ = _hooked
    atexit.register(_dump)
