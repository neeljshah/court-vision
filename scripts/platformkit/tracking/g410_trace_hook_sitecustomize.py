"""G410 observer-only import hook (the producer never imports this file).

Placed on PYTHONPATH so CPython site initialisation loads it before any
producer module exists.  It wraps the detector entry point that the pipeline
actually calls and records, for ONE invocation, the two matrices that the
archived code multiplies, the frame and court-map extents, and every slot's
stored box and stored court position immediately before and after the call.

Nothing here changes a tracking decision: the wrapper calls the real method and
returns its value unchanged.  Rows (ASCII, LF, one per line):

  M,<tick>,<m00..m22>,<n00..n22>,<frame_w>,<frame_h>,<map_w>,<map_h>
  B,<tick>,<slot>,<pid>,<team>,<y1>,<x1>,<y2>,<x2>,<px>,<py>   pre-call state
  P,<tick>,<slot>,<pid>,<team>,<y1>,<x1>,<y2>,<x2>,<px>,<py>   post-call state
"""
import atexit
import builtins
import os

_PATH = os.environ.get("G410_TRACE")

if _PATH:
    _rows = []

    def _mat(matrix):
        try:
            flat = [float(v) for row in matrix for v in row]
        except TypeError:
            return ",".join(["nan"] * 9)
        return ",".join("%.12g" % v for v in flat[:9])

    def _state(tag, tick, players):
        for slot, p in enumerate(players):
            box = getattr(p, "previous_bb", None)
            pos = getattr(p, "positions", {}).get(int(tick))
            box_s = (",".join("%.6g" % float(v) for v in tuple(box)[:4])
                     if box is not None else ",,,")
            pos_s = (",".join("%.6g" % float(v) for v in tuple(pos)[:2])
                     if pos is not None else ",")
            _rows.append("%s,%d,%d,%s,%s,%s,%s" % (
                tag, int(tick), slot, getattr(p, "ID", ""),
                getattr(p, "team", ""), box_s, pos_s))

    def _install(module):
        module._g410_traced = True
        real = module.AdvancedFeetDetector.get_players_pos

        def wrapped(self, M, M1, frame, timestamp, map_2d, *args, **kwargs):
            _state("B", timestamp, self.players)
            out = real(self, M, M1, frame, timestamp, map_2d, *args, **kwargs)
            _rows.append("M,%d,%s,%s,%d,%d,%d,%d" % (
                int(timestamp), _mat(M), _mat(M1),
                frame.shape[1], frame.shape[0],
                map_2d.shape[1], map_2d.shape[0]))
            _state("P", timestamp, self.players)
            return out

        module.AdvancedFeetDetector.get_players_pos = wrapped

    def _dump():
        try:
            with open(_PATH, "w", encoding="ascii") as handle:
                handle.write("\n".join(_rows) + "\n")
        except OSError:
            pass

    _real_import = builtins.__import__

    def _hooked(name, globals=None, locals=None, fromlist=(), level=0):
        module = _real_import(name, globals, locals, fromlist, level)
        target = module if getattr(module, "AdvancedFeetDetector", None) is not None \
            else getattr(module, "advanced_tracker", None)
        if target is not None and getattr(target, "AdvancedFeetDetector", None) is not None \
                and not getattr(target, "_g410_traced", False):
            _install(target)
        return module

    builtins.__import__ = _hooked
    atexit.register(_dump)
