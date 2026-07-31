"""scripts.go_live.site_live -- on-demand "make my site live" switch.

Backend fleet (paper trading) always runs, supervised, untouched by this
module. The FRONTEND (Next.js on :3100) is off by default; this script is the
only thing that turns it public, via a cloudflared quick tunnel (no account,
random *.trycloudflare.com URL per session -- fine for on-demand sharing).

Commands:
    python scripts/go_live/site_live.py up [--rebuild]
    python scripts/go_live/site_live.py down
    python scripts/go_live/site_live.py status

Stdlib only except the repo's own quiet_subprocess helper (avoids a console
flash on Windows for every child process).
"""
from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WEBAPP_DIR = REPO_ROOT / "webapp"
CACHE_DIR = REPO_ROOT / "data" / "cache" / "go_live"
STATE_FILE = CACHE_DIR / "state.json"
NEXT_LOG = CACHE_DIR / "next_server.log"
TUNNEL_LOG = CACHE_DIR / "cloudflared.log"
PORT = 3100
CLOUDFLARED = Path.home() / "bin" / "cloudflared.exe"
TUNNEL_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

sys.path.insert(0, str(REPO_ROOT))
try:
    from scripts.platformkit.ops.quiet_subprocess import popen as _quiet_popen
except ImportError:  # pragma: no cover - only hit if run outside the repo layout
    def _quiet_popen(cmd, **kwargs):
        return subprocess.Popen(cmd, **kwargs)


def read_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def write_state(state: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def clear_state() -> None:
    if STATE_FILE.exists():
        STATE_FILE.unlink()


def port_serving(port: int, path: str = "/", timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as resp:
            return resp.status < 500
    except urllib.error.HTTPError as exc:
        return exc.code < 500
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def _resolve_via_powershell(host: str) -> str | None:
    """Fallback A-record lookup for boxes where a VPN's DNS filter breaks the
    normal getaddrinfo() path for random subdomains (seen on this box's
    NordLynx setup: PowerShell's own resolver still gets a real A record).
    """
    # The VPN resolver sometimes NXDOMAINs brand-new tunnel subdomains outright,
    # so after the system path fails, ask Cloudflare's 1.1.1.1 directly.
    for server_arg in ("", " -Server 1.1.1.1"):
        try:
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command",
                 f"(Resolve-DnsName {host} -Type A{server_arg} -ErrorAction Stop | Select-Object -First 1).IPAddress"],
                text=True, timeout=10, stderr=subprocess.DEVNULL,
            ).strip()
            if out:
                return out
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            continue
    # Last resort: DNS-over-HTTPS straight to the literal IP 1.1.1.1 -- immune
    # to the VPN's port-53 interception (which NXDOMAINs fresh tunnel names
    # even when told to ask 1.1.1.1 directly).
    try:
        req = urllib.request.Request(
            f"https://1.1.1.1/dns-query?name={host}&type=A",
            headers={"accept": "application/dns-json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            answers = json.loads(resp.read()).get("Answer") or []
        for a in answers:
            if a.get("type") == 1 and a.get("data"):
                return a["data"]
    except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError):
        pass
    return None


def probe_url(url: str, path: str = "/paper", timeout: float = 3.0) -> tuple[bool, int | None]:
    full = f"{url}{path}"
    try:
        with urllib.request.urlopen(full, timeout=timeout) as resp:
            return True, resp.status
    except urllib.error.HTTPError as exc:
        return exc.code < 500, exc.code
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        if "getaddrinfo failed" not in str(exc):
            return False, None
        # ponytail: getaddrinfo-only DNS fallback via resolved IP; SNI/host header
        # still use the real hostname, only the socket connect target changes.
        host = urllib.parse.urlsplit(url).hostname
        ip = _resolve_via_powershell(host) if host else None
        if not ip:
            return False, None
        original_getaddrinfo = socket.getaddrinfo
        socket.getaddrinfo = lambda h, *a, **k: original_getaddrinfo(ip if h == host else h, *a, **k)
        try:
            with urllib.request.urlopen(full, timeout=timeout) as resp:
                return True, resp.status
        except urllib.error.HTTPError as exc2:
            return exc2.code < 500, exc2.code
        except (urllib.error.URLError, OSError, TimeoutError):
            return False, None
        finally:
            socket.getaddrinfo = original_getaddrinfo


def pid_cmdline(pid: int) -> str:
    """Return the Windows CommandLine for a pid via wmic, or "" if not found/alive."""
    try:
        out = subprocess.check_output(
            ["wmic", "process", "where", f"ProcessId={pid}", "get", "CommandLine", "/FORMAT:LIST"],
            text=True, stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return ""
    for line in out.splitlines():
        if line.startswith("CommandLine="):
            return line[len("CommandLine="):].strip()
    return ""


def pid_matches(pid: int, needle: str) -> bool:
    cmdline = pid_cmdline(pid)
    return bool(cmdline) and needle.lower() in cmdline.lower()


def kill_tracked_pid(pid: int, needle: str) -> bool:
    """Kill pid only if its live commandline still matches what we started -- never kill blind."""
    if not pid_matches(pid, needle):
        return False
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    return True


def ensure_build(rebuild: bool = False) -> None:
    build_id = WEBAPP_DIR / ".next" / "BUILD_ID"
    if build_id.exists() and not rebuild:
        return
    print("[go_live] no prod build found (or --rebuild) -- running `npm run build` in webapp/ ...")
    result = subprocess.run(
        ["npm", "run", "build"], cwd=WEBAPP_DIR, shell=True,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(result.stdout[-4000:])
        print(result.stderr[-4000:])
        raise SystemExit(f"[go_live] webapp build FAILED (exit {result.returncode})")
    if not build_id.exists():
        raise SystemExit("[go_live] build reported success but BUILD_ID still missing -- aborting")
    print("[go_live] build OK")


def start_next() -> int:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    log_fh = open(NEXT_LOG, "w")
    proc = _quiet_popen(
        ["npx", "next", "start", "-p", str(PORT)], cwd=str(WEBAPP_DIR), shell=True,
        stdout=log_fh, stderr=subprocess.STDOUT,
    )
    return proc.pid


def start_cloudflared() -> int:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    TUNNEL_LOG.write_text("")
    log_fh = open(TUNNEL_LOG, "w")
    proc = _quiet_popen(
        [str(CLOUDFLARED), "tunnel", "--url", f"http://127.0.0.1:{PORT}", "--no-autoupdate"],
        stdout=log_fh, stderr=subprocess.STDOUT,
    )
    return proc.pid


def parse_tunnel_url(timeout: float = 30.0) -> str | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if TUNNEL_LOG.exists():
            match = TUNNEL_URL_RE.search(TUNNEL_LOG.read_text(errors="ignore"))
            if match:
                return match.group(0)
        time.sleep(1)
    return None


def cmd_up(args: argparse.Namespace) -> int:
    state = read_state()
    if state.get("url") and port_serving(PORT) and probe_url(state["url"])[0]:
        print(f"[go_live] already live: {state['url']}")
        return 0

    ensure_build(rebuild=args.rebuild)

    next_pid = state.get("next_pid")
    if not (next_pid and pid_matches(next_pid, "next") and port_serving(PORT)):
        next_pid = start_next()
        print(f"[go_live] next server starting (pid {next_pid}), waiting for :{PORT} ...")
        deadline = time.time() + 60
        while time.time() < deadline and not port_serving(PORT):
            time.sleep(2)
        if not port_serving(PORT):
            raise SystemExit(f"[go_live] :{PORT} never came up -- see {NEXT_LOG}")

    tunnel_pid = state.get("tunnel_pid")
    url = state.get("url")
    if not (tunnel_pid and pid_matches(tunnel_pid, "cloudflared") and url):
        tunnel_pid = start_cloudflared()
        print(f"[go_live] cloudflared tunnel starting (pid {tunnel_pid}) ...")
        url = parse_tunnel_url()
        if not url:
            raise SystemExit(f"[go_live] tunnel URL never appeared -- see {TUNNEL_LOG}")

    ok, status = False, None
    deadline = time.time() + 60
    while time.time() < deadline:
        ok, status = probe_url(url)
        if ok:
            break
        time.sleep(3)
    if not ok:
        raise SystemExit(f"[go_live] public URL {url}/paper never returned <500 (last status={status})")

    write_state({
        "next_pid": next_pid, "tunnel_pid": tunnel_pid, "url": url,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    print(f"[go_live] LIVE: {url}  (probe /paper -> {status})")
    print("[go_live] known limitation: quick-tunnel URL is random per session")
    return 0


def cmd_down(args: argparse.Namespace) -> int:
    state = read_state()
    if not state:
        print("[go_live] already down (no state)")
        return 0
    killed = []
    if state.get("tunnel_pid"):
        if kill_tracked_pid(state["tunnel_pid"], "cloudflared"):
            killed.append(f"cloudflared pid {state['tunnel_pid']}")
    if state.get("next_pid"):
        if kill_tracked_pid(state["next_pid"], "next"):
            killed.append(f"next pid {state['next_pid']}")
    clear_state()
    time.sleep(2)
    still_up = port_serving(PORT)
    print(f"[go_live] down. killed: {killed or 'none (already dead)'}")
    print(f"[go_live] :{PORT} still serving: {still_up}")
    return 1 if still_up else 0


def cmd_status(args: argparse.Namespace) -> int:
    state = read_state()
    local_up = port_serving(PORT)
    print(f"local :{PORT} serving: {local_up}")
    if state.get("url"):
        ok, status = probe_url(state["url"])
        print(f"public url: {state['url']} (reachable={ok}, status={status})")
        print(f"started_at: {state.get('started_at')}")
    else:
        print("public url: none (not live)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    up = sub.add_parser("up", help="build if needed, start next+tunnel, print public URL")
    up.add_argument("--rebuild", action="store_true", help="force `npm run build` first")
    sub.add_parser("down", help="tear down tunnel + next server; fleet untouched")
    sub.add_parser("status", help="show current state + live probe")
    args = parser.parse_args()
    return {"up": cmd_up, "down": cmd_down, "status": cmd_status}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
