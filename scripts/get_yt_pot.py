"""
get_yt_pot.py -- Fetch a YouTube PO token from the running bgutil server and
print the extractor-args string that yt-dlp needs.

Usage:
    python3.11 scripts/get_yt_pot.py <video_id>

Output (stdout):
    web.gvs+<poToken>;<visitor_data>
    (suitable for --extractor-args "youtube:po_token=...")
"""
from __future__ import annotations
import json, sys, urllib.request

BGUTIL_URL = "http://127.0.0.1:4416"

def main():
    video_id = sys.argv[1] if len(sys.argv) > 1 else "dQw4w9WgXcQ"

    # Fetch PO token from bgutil server
    payload = json.dumps({
        "videoId": video_id,
        "visitor_data": "",
        "data_sync_id": "",
    }).encode()
    req = urllib.request.Request(
        f"{BGUTIL_URL}/get_pot",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=20)
    data = json.load(resp)
    if "error" in data:
        print(f"ERROR: {data['error']}", file=sys.stderr)
        sys.exit(1)

    po_token = data["poToken"]
    # contentBinding is the visitor_data equivalent for web.gvs context
    content_binding = data.get("contentBinding", "")
    print(f"web.gvs+{po_token}", flush=True)

if __name__ == "__main__":
    main()
