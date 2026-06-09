"""verify_routes.py — quick smoke test for all CourtVision routes."""
import sys, time
sys.path.insert(0, ".")
from fastapi.testclient import TestClient
from api.live_v2_app import app

c = TestClient(app)
urls = ['/', '/odds', '/game/34201426', '/parlays', '/arbs', '/tonight', '/help']
fail = False
for url in urls:
    t0 = time.time()
    try:
        r = c.get(url)
        ms = int((time.time() - t0) * 1000)
        status = "OK" if r.status_code == 200 else "FAIL"
        print(f"{status}  {url}: HTTP {r.status_code} {len(r.content)}B {ms}ms")
        if r.status_code != 200 or ms > 500:
            fail = True
    except Exception as e:
        print(f"FAIL {url}: ERROR {e}")
        fail = True
sys.exit(1 if fail else 0)
