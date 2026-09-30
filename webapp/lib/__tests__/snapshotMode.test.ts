import { describe, it, expect, vi, afterEach } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { snapshotPath, isSnapshotMode } from "../fetchHonest";

const demoDir = join(process.cwd(), "public", "demo-data");

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

// ---------------------------------------------------------------------------
// Snapshot data mode -- static-demo build switch. snapshotPath is the pure
// slug (also used by the exporter to name files, kept in sync by convention);
// the module-level isSnapshotMode gate must default OFF (live mode unchanged)
// and, when ON, fetchHonest must redirect GET calls to the baked file instead
// of the live URL.
// ---------------------------------------------------------------------------

describe("snapshotPath", () => {
  it("slugs a path (INCLUDING query string -- sport is often query-only)", () => {
    expect(snapshotPath("/p5/api/report/nba")).toBe("/demo-data/api_report_nba.json");
    expect(snapshotPath("/api/board/slate?sport=nba")).toBe(
      "/demo-data/api_board_slate_sport_nba.json",
    );
  });

  it("different query strings on the same path never collide", () => {
    expect(snapshotPath("/p5/api/produce/status?sport=nba")).toBe(
      "/demo-data/api_produce_status_sport_nba.json",
    );
    expect(existsSync(join(demoDir, "api_produce_status_sport_nba.json"))).toBe(true);
    expect(snapshotPath("/api/produce/status?sport=nba")).not.toBe(
      snapshotPath("/api/produce/status?sport=mlb"),
    );
  });

  it("only removes the configured P5 base before /api/", async () => {
    expect(snapshotPath("/p5x/api/report/nba")).toBe("/demo-data/p5x_api_report_nba.json");
    expect(snapshotPath("/p5/apiary/report/nba")).toBe("/demo-data/p5_apiary_report_nba.json");
    expect(snapshotPath("/other/p5/api/report/nba")).toBe("/demo-data/other_p5_api_report_nba.json");
    vi.stubEnv("NEXT_PUBLIC_P5_BASE", "/custom/p5");
    vi.resetModules();
    const { snapshotPath: customPath } = await import("../fetchHonest");
    expect(customPath("/custom/p5/api/report/nba")).toBe("/demo-data/api_report_nba.json");
    expect(customPath("/p5/api/report/nba")).toBe("/demo-data/p5_api_report_nba.json");
    expect(customPath("/custom/p5x/api/report/nba")).toBe("/demo-data/custom_p5x_api_report_nba.json");
    vi.stubEnv("NEXT_PUBLIC_P5_BASE", "https://example.test/p5");
    vi.resetModules();
    const { snapshotPath: absolutePath } = await import("../fetchHonest");
    expect(absolutePath("https://example.test/p5/api/report/nba")).toBe("/demo-data/api_report_nba.json");
    expect(absolutePath("https://other.test/p5/api/report/nba")).toBe("/demo-data/https_other_test_p5_api_report_nba.json");
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
    expect(seen).toEqual(["/demo-data/api_report_nba.json"]);
  });

  it("loads the published MLB payload through api.getPredict and preserves NBA unavailability", async () => {
    vi.stubEnv("NEXT_PUBLIC_DATA_MODE", "snapshot");
    vi.stubEnv("NEXT_PUBLIC_BASE_PATH", "");
    vi.resetModules();
    const { api } = await import("../p5api");
    const mlbFile = join(demoDir, "api_predict_mlb.json");
    const nbaFile = join(demoDir, "api_predict_nba.json");
    expect(existsSync(mlbFile)).toBe(true);
    expect(existsSync(nbaFile)).toBe(true);
    const seen: string[] = [];
    global.fetch = vi.fn(async (url: string) => {
      seen.push(url);
      const file = join(demoDir, url.replace(/^\/demo-data\//, ""));
      return {
        ok: existsSync(file),
        status: existsSync(file) ? 200 : 404,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => JSON.parse(readFileSync(file, "utf8")),
      };
    }) as unknown as typeof fetch;
    const mlb = await api.getPredict("mlb");
    const nba = await api.getPredict("nba");
    const missing = await api.getPredict("unknown");
    expect(seen).toEqual([
      "/demo-data/api_predict_mlb.json",
      "/demo-data/api_predict_nba.json",
      "/demo-data/api_predict_unknown.json",
    ]);
    expect(mlb).toEqual(JSON.parse(readFileSync(mlbFile, "utf8")));
    expect(nba).toEqual(JSON.parse(readFileSync(nbaFile, "utf8")));
    expect(mlb.status).toBe("ok");
    expect(nba.status).toBe("unavailable");
    expect(missing).toEqual({ status: "unavailable", reason: "HTTP 404" });
  });

  it("leaves live P5 GETs on their original URL", async () => {
    vi.stubEnv("NEXT_PUBLIC_DATA_MODE", "live");
    vi.resetModules();
    const { api } = await import("../p5api");
    const seen: string[] = [];
    global.fetch = vi.fn(async (url: string) => {
      seen.push(url);
      return { ok: true, status: 200, headers: new Headers({ "content-type": "application/json" }), json: async () => ({ status: "ok" }) };
    }) as unknown as typeof fetch;
    await api.getPredict("mlb");
    expect(seen).toEqual(["/p5/api/predict/mlb"]);
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

  it("does not retry a failed snapshot-mode paper placement", async () => {
    vi.stubEnv("NEXT_PUBLIC_DATA_MODE", "snapshot");
    vi.resetModules();
    const { api } = await import("../p5api");
    global.fetch = vi.fn().mockRejectedValue(new Error("offline"));
    const result = await api.placePaper({} as Parameters<typeof api.placePaper>[0]);
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(global.fetch).toHaveBeenCalledWith(
      "/p5/api/paper/place",
      expect.objectContaining({ method: "POST" }),
    );
    expect(result.status).toBe("unavailable");
  });
});
