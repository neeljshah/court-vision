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

describe("fetchHonest -- snapshot file whitelist", () => {
  const realFetch = global.fetch;
  afterEach(() => {
    global.fetch = realFetch;
    vi.restoreAllMocks();
  });

  it("skips the network for a GET whose baked file was never exported", async () => {
    vi.stubEnv("NEXT_PUBLIC_DATA_MODE", "snapshot");
    vi.stubEnv("NEXT_PUBLIC_SNAPSHOT_FILES", JSON.stringify(["api_report_nba.json"]));
    vi.resetModules();
    const mod = await import("../fetchHonest");
    const seen: string[] = [];
    global.fetch = vi.fn((url: string) => {
      seen.push(url);
      return Promise.resolve({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: () => Promise.resolve({ ok: true }),
      } as unknown as Response);
    }) as unknown as typeof fetch;
    expect(mod.snapshotHas("/p5/api/report/nba")).toBe(true);
    expect(mod.snapshotHas("/api/bestbets/nba")).toBe(false);
    const missing = await mod.fetchHonest<{ ok: boolean }>("/api/bestbets/nba");
    expect(missing).toEqual({ status: "unavailable", reason: "not in the published snapshot" });
    expect(seen).toEqual([]);
    const present = await mod.fetchHonest<{ ok: boolean }>("/p5/api/report/nba");
    expect(present).toEqual({ ok: true });
    expect(seen).toEqual(["/demo-data/api_report_nba.json"]);
  });

  it("filters nothing when no file list was inlined", async () => {
    vi.stubEnv("NEXT_PUBLIC_DATA_MODE", "snapshot");
    vi.stubEnv("NEXT_PUBLIC_SNAPSHOT_FILES", "");
    vi.resetModules();
    const mod = await import("../fetchHonest");
    expect(mod.snapshotHas("/api/anything")).toBe(true);
  });
});

describe("snapshotHasGame -- baked detail pages", () => {
  it("links only the games the export contains, and everything when live", async () => {
    vi.stubEnv("NEXT_PUBLIC_DATA_MODE", "snapshot");
    vi.stubEnv("NEXT_PUBLIC_SNAPSHOT_GAMES", JSON.stringify(["mlb/KXMLBGAME-1", "soccer/9"]));
    vi.resetModules();
    const snap = await import("../fetchHonest");
    expect(snap.snapshotHasGame("mlb", "KXMLBGAME-1")).toBe(true);
    expect(snap.snapshotHasGame("mlb", "fd:35816158")).toBe(false);
    vi.stubEnv("NEXT_PUBLIC_DATA_MODE", "");
    vi.resetModules();
    const live = await import("../fetchHonest");
    expect(live.snapshotHasGame("mlb", "fd:35816158")).toBe(true);
  });
});

describe("snapshotHasBet -- baked paper detail pages", () => {
  it("links only the bet ids the export contains, and everything when live", async () => {
    vi.stubEnv("NEXT_PUBLIC_DATA_MODE", "snapshot");
    vi.stubEnv("NEXT_PUBLIC_SNAPSHOT_BETS", JSON.stringify(["mlb%7Cmlb%7CA%7C2026%7Cmoneyline%7Chome%7Ckalshi"]));
    vi.resetModules();
    const snap = await import("../fetchHonest");
    expect(snap.snapshotHasBet("mlb%7Cmlb%7CA%7C2026%7Cmoneyline%7Chome%7Ckalshi")).toBe(true);
    expect(snap.snapshotHasBet("mlb%7Cmlb%7CB%7C2026%7Cmoneyline%7Chome%7Ckalshi")).toBe(false);
    vi.stubEnv("NEXT_PUBLIC_DATA_MODE", "");
    vi.resetModules();
    const live = await import("../fetchHonest");
    expect(live.snapshotHasBet("anything")).toBe(true);
  });
});

describe("systemApi.artifacts in snapshot mode", () => {
  it("fetches the exported route under the base path (no dead demo-data slug)", async () => {
    vi.stubEnv("NEXT_PUBLIC_DATA_MODE", "snapshot");
    vi.stubEnv("NEXT_PUBLIC_BASE_PATH", "/court-vision");
    vi.resetModules();
    const f = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: "ok" }) });
    vi.stubGlobal("fetch", f);
    const { systemApi } = await import("../../components/system/systemApi");
    await systemApi.artifacts();
    expect(f.mock.calls[0][0]).toBe("/court-vision/system/funnel-artifacts");
    vi.unstubAllGlobals();
  });
});
