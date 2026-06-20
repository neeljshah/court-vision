import { describe, it, expect, vi, afterEach } from "vitest";
import { fetchHonest } from "../fetchHonest";

// ---------------------------------------------------------------------------
// fetchHonest -- the hardened transport primitive. These tests gate the three
// robustness rails: NEVER-THROWS, bounded TIMEOUT -> honest degrade, and bounded
// RETRY on transient failures only (a server 4xx/5xx degrades immediately).
// ---------------------------------------------------------------------------

const realFetch = global.fetch;
afterEach(() => {
  global.fetch = realFetch;
  vi.restoreAllMocks();
});

const jsonRes = (body: unknown, status = 200, ok = true) => ({
  ok,
  status,
  headers: new Headers({ "content-type": "application/json" }),
  json: async () => body,
});

describe("fetchHonest -- success path", () => {
  it("returns the parsed JSON body on a 200", async () => {
    global.fetch = vi.fn().mockResolvedValue(jsonRes({ value: 42 })) as unknown as typeof fetch;
    const r = await fetchHonest<{ value: number }>("http://x/ok");
    expect(r).toEqual({ value: 42 });
  });
});

describe("fetchHonest -- never throws, degrades to Unavailable", () => {
  it("a 500 degrades to the Unavailable sentinel (no throw)", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValue(jsonRes({ err: "x" }, 500, false)) as unknown as typeof fetch;
    const r = await fetchHonest("http://x/500");
    expect(r).toEqual({ status: "unavailable", reason: "HTTP 500" });
  });

  it("a non-JSON body degrades to Unavailable", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "text/html" }),
      json: async () => {
        throw new Error("not json");
      },
    }) as unknown as typeof fetch;
    const r = (await fetchHonest("http://x/html")) as { status: string };
    expect(r.status).toBe("unavailable");
  });

  it("a thrown network error degrades to Unavailable (never throws)", async () => {
    global.fetch = vi.fn().mockRejectedValue(new TypeError("network down")) as unknown as typeof fetch;
    const r = (await fetchHonest("http://x/net", { retries: 0 })) as {
      status: string;
      reason?: string;
    };
    expect(r.status).toBe("unavailable");
    expect(r.reason).toContain("fetch failed");
  });
});

describe("fetchHonest -- bounded timeout -> degraded", () => {
  it("a hung fetch resolves to Unavailable after the timeout (never hangs)", async () => {
    // fetch that respects the abort signal (as the platform fetch does).
    global.fetch = vi.fn((_url: string, init?: RequestInit) => {
      return new Promise((_res, rej) => {
        init?.signal?.addEventListener("abort", () =>
          rej(Object.assign(new Error("aborted"), { name: "AbortError" })),
        );
      });
    }) as unknown as typeof fetch;
    const r = (await fetchHonest("http://x/hang", {
      timeoutMs: 20,
      retries: 0,
    })) as { status: string; reason?: string };
    expect(r.status).toBe("unavailable");
    expect(r.reason).toContain("timeout");
  });
});

describe("fetchHonest -- bounded retry on transient failures", () => {
  it("retries a transient network error then succeeds", async () => {
    let n = 0;
    global.fetch = vi.fn(() => {
      n += 1;
      if (n < 3) return Promise.reject(new TypeError("blip"));
      return Promise.resolve(jsonRes({ ok: true }));
    }) as unknown as typeof fetch;
    const r = await fetchHonest<{ ok: boolean }>("http://x/retry", {
      retries: 3,
      backoffMs: 1,
      backoffCapMs: 2,
    });
    expect(r).toEqual({ ok: true });
    expect(n).toBe(3);
  });

  it("does NOT retry a server 4xx (degrades immediately, single call)", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonRes({ err: "bad" }, 404, false));
    global.fetch = fetchMock as unknown as typeof fetch;
    const r = (await fetchHonest("http://x/404", {
      retries: 3,
      backoffMs: 1,
    })) as { status: string };
    expect(r.status).toBe("unavailable");
    expect(fetchMock).toHaveBeenCalledTimes(1); // teeth: NOT retried
  });

  it("exhausts retries and degrades to Unavailable", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("always down"));
    global.fetch = fetchMock as unknown as typeof fetch;
    const r = (await fetchHonest("http://x/dead", {
      retries: 2,
      backoffMs: 1,
      backoffCapMs: 2,
    })) as { status: string };
    expect(r.status).toBe("unavailable");
    expect(fetchMock).toHaveBeenCalledTimes(3); // 1 + 2 retries
  });
});

describe("fetchHonest -- POST surfaces JSON rejection body", () => {
  it("returns a 422 JSON body (the rejection reason) instead of a sentinel", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValue(jsonRes({ accepted: false, reason: "below floor" }, 422, false)) as unknown as typeof fetch;
    const r = await fetchHonest<{ accepted: boolean; reason: string }>("http://x/place", {
      body: { side: "over" },
      retries: 0,
    });
    expect(r).toEqual({ accepted: false, reason: "below floor" });
  });
});
