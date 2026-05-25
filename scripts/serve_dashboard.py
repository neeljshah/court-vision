"""serve_dashboard.py -- tier4-13 (loop 5). LAN HTTP server for the
generate_html_dashboard output.

Serves data/dashboard.html on the local LAN so the operator can open it
from their phone (e.g. http://192.168.1.42:8080/). A background thread
regenerates the HTML every --regenerate-sec seconds.

No external dependencies -- stdlib http.server only.

CLI:
    python scripts/serve_dashboard.py
    python scripts/serve_dashboard.py --port 8080 --regenerate-sec 60
"""
from __future__ import annotations

import argparse
import http.server
import os
import socket
import socketserver
import sys
import threading
import time
from datetime import date as _date

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from scripts.generate_html_dashboard import write_dashboard  # noqa: E402


def _lan_ip() -> str:
    """Best-effort LAN IP discovery for printing the connect URL."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def _regen_loop(output: str, date_iso: str, interval: int,
                stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            write_dashboard(output, date_iso, refresh_sec=interval)
        except Exception as exc:
            print(f"[warn] regen failed: {exc}")
        stop_event.wait(interval)


class _RootHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler that serves dashboard.html at /."""

    dashboard_path = ""   # set by main()

    def do_GET(self):  # noqa: N802
        if self.path in ("/", "/index.html", "/dashboard.html"):
            try:
                with open(self.dashboard_path, "rb") as fh:
                    body = fh.read()
            except OSError:
                self.send_error(503, "dashboard not yet generated")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def log_message(self, fmt, *args):  # noqa: A003
        # Quieter log than the default stderr spam.
        sys.stderr.write(f"[serve] {self.address_string()} {fmt % args}\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--regenerate-sec", type=int, default=60)
    ap.add_argument("--date", default=None)
    ap.add_argument("--output", default=os.path.join(
        PROJECT_DIR, "data", "dashboard.html"))
    args = ap.parse_args()

    date_iso = args.date or _date.today().isoformat()
    # Prime the file once before the server boots, so the first request
    # always sees a valid page.
    write_dashboard(args.output, date_iso, refresh_sec=args.regenerate_sec)

    stop_event = threading.Event()
    t = threading.Thread(
        target=_regen_loop,
        args=(args.output, date_iso, args.regenerate_sec, stop_event),
        daemon=True,
    )
    t.start()

    _RootHandler.dashboard_path = args.output
    ip = _lan_ip()
    print(f"[serve] http://{ip}:{args.port}/  (regen every {args.regenerate_sec}s)")
    print(f"[serve] serving {args.output}; ctrl-c to stop")

    httpd = socketserver.ThreadingTCPServer(("0.0.0.0", args.port), _RootHandler)
    httpd.allow_reuse_address = True
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[serve] shutting down")
    finally:
        stop_event.set()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
