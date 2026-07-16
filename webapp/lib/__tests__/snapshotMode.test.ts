import { describe, it, expect, vi, afterEach } from "vitest";
import { snapshotPath, fetchHonest, isSnapshotMode } from "../fetchHonest";

// ---------------------------------------------------------------------------
// Snapshot data mode -- static-demo build switch. snapshotPath is the pure
// slug (also used by the exporter to name files, kept in sync by convention);
// the module-level isSnapshotMode gate must default OFF (live mode unchanged)
// and, when ON, fetchHonest must redirect GET calls to the baked file instead
// of the live URL.
// ---------------------------------------------------------------------------

describe("snapshotPath", () => {
  it("slugs a path (INCLUDING query string -- sport is often query-only)", () => {
    expect(snapshotPath("/p5/api/report/nba")).toBe("/demo-data/p5_api_report_nba.json");
    expect(snapshotPath("/api/board/slate?sport=nba")).toBe(
      "/demo-data/api_board_slate_sport_nba.json",
    );
  });

  it("different query strings on the same path never collide", () => {
    expect(snapshotPath("/api/produce/status?sport=nba")).not.toBe(
      snapshotPath("/api/produce/status?sport=mlb"),
    );
  });
});

describe("isSnapshotMode default", () => {
  it("is off in the normal test/live build", () => {
    expect(isSnapshotMode).toBe(false);
  });
});

describe("fetchHonest -- snapshot mode redirect", () => {
  const realFetch = global.fetch;
  afterEach(() => {
    global.fetch = realFetch;
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("routes a GET to the demo-data file when NEXT_PUBLIC_DATA_MODE=snapshot", async () => {
    vi.stubEnv("NEXT_PUBLIC_DATA_MODE", "snapshot");
    vi.resetModules();
    const mod = await import("../fetchHonest");
    const seen: string[] = [];
    global.fetch = vi.fn((url: string) => {
      seen.push(url);
      return Promise.resolve({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ ok: true }),
      });
    }) as unknown as typeof fetch;

    expect(mod.isSnapshotMode).toBe(true);
    const r = await mod.fetchHonest("/p5/api/report/nba");
    expect(r).toEqual({ ok: true });
    expect(seen).toEqual(["/demo-data/p5_api_report_nba.json"]);
  });

  it("still hits the live URL for a POST (no snapshot equivalent)", async () => {
    vi.stubEnv("NEXT_PUBLIC_DATA_MODE", "snapshot");
    vi.resetModules();
    const mod = await import("../fetchHonest");
    const seen: string[] = [];
    global.fetch = vi.fn((url: string) => {
      seen.push(url);
      return Promise.resolve({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ ok: true }),
      });
    }) as unknown as typeof fetch;

    await mod.fetchHonest("/p5/api/paper/place", { body: { x: 1 }, retries: 0 });
    expect(seen).toEqual(["/p5/api/paper/place"]);
  });
});
