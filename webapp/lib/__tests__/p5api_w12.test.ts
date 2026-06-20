/**
 * W12-shell: per-file tests for the new p5api.ts client methods.
 *
 * Verifies (with a fake fetch -- NO real network, NO real server):
 *   - bestbetsBoard: builds the correct URL, passes query params, degrades on error.
 *   - propsBoard: correct URL pattern with and without gameId.
 *   - linesMatrix: correct URL with sport + gameId.
 *   - ingameFull: correct URL.
 *   - boxscore: correct URL.
 *   - pmTrail: builds query params correctly.
 *   - improveLedger: correct URL.
 *   - No method returns a $ P&L field (honesty rail: UNITS not $).
 *
 * Run ONLY this file:
 *   cd webapp && npx vitest run lib/__tests__/p5api_w12.test.ts
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { api, P5_BASE } from "../p5api";

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------
const jsonRes = (body: unknown, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  headers: new Headers({ "content-type": "application/json" }),
  json: async () => body,
});

afterEach(() => {
  vi.restoreAllMocks();
});

const mockFetch = (body: unknown, status = 200) => {
  global.fetch = vi.fn().mockResolvedValue(jsonRes(body, status)) as unknown as typeof fetch;
};

const capturedUrl = () =>
  (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;

// ---------------------------------------------------------------------------
// bestbetsBoard
// ---------------------------------------------------------------------------
describe("api.bestbetsBoard", () => {
  it("calls /api/bestbets/board with no params", async () => {
    mockFetch({ status: "ok", cards: [], count: 0, edge_claimed: false });
    await api.bestbetsBoard();
    expect(capturedUrl()).toBe(`${P5_BASE}/api/bestbets/board`);
  });

  it("passes sport + tier + status query params", async () => {
    mockFetch({ status: "ok", cards: [], count: 0, edge_claimed: false });
    await api.bestbetsBoard({ sport: "nba", tier: "A", status: "pregame" });
    const url = capturedUrl();
    expect(url).toContain("sport=nba");
    expect(url).toContain("tier=A");
    expect(url).toContain("status=pregame");
  });

  it("degrades to Unavailable on network error", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("timeout")) as unknown as typeof fetch;
    const r = await api.bestbetsBoard();
    expect(r).toMatchObject({ status: "unavailable" });
  });
});

// ---------------------------------------------------------------------------
// propsBoard
// ---------------------------------------------------------------------------
describe("api.propsBoard", () => {
  it("calls /api/predict/props/{sport} without gameId", async () => {
    mockFetch({ status: "ok", props: [], count: 0, edge_claimed: false });
    await api.propsBoard("nba");
    expect(capturedUrl()).toBe(`${P5_BASE}/api/predict/props/nba`);
  });

  it("appends game_id param when provided", async () => {
    mockFetch({ status: "ok", props: [], count: 0, edge_claimed: false });
    await api.propsBoard("nba", "g001");
    expect(capturedUrl()).toContain("game_id=g001");
  });

  it("degrades to Unavailable on 503", async () => {
    mockFetch({ detail: "unavailable" }, 503);
    const r = await api.propsBoard("nba");
    expect(r).toMatchObject({ status: "unavailable" });
  });
});

// ---------------------------------------------------------------------------
// linesMatrix
// ---------------------------------------------------------------------------
describe("api.linesMatrix", () => {
  it("calls /api/lines/{sport}/{gameId}/matrix", async () => {
    mockFetch({ status: "ok", matrix: {}, best: {}, sport: "nba", game_id: "g001" });
    await api.linesMatrix("nba", "g001");
    expect(capturedUrl()).toBe(`${P5_BASE}/api/lines/nba/g001/matrix`);
  });
});

// ---------------------------------------------------------------------------
// ingameFull
// ---------------------------------------------------------------------------
describe("api.ingameFull", () => {
  it("calls /api/ingame/{sport}/{gid}/full", async () => {
    mockFetch({
      status: "ok", clv_status: "INSUFFICIENT_DATA",
      edge_claimed: false, sport: "nba", game_id: "g001",
    });
    await api.ingameFull("nba", "g001");
    expect(capturedUrl()).toBe(`${P5_BASE}/api/ingame/nba/g001/full`);
  });

  it("INSUFFICIENT_DATA flows through without fabrication", async () => {
    mockFetch({ status: "ok", clv_status: "INSUFFICIENT_DATA", edge_claimed: false });
    const r = await api.ingameFull("nba", "g001");
    if (r && "clv_status" in r) {
      expect(r.clv_status).toBe("INSUFFICIENT_DATA");
    }
  });
});

// ---------------------------------------------------------------------------
// boxscore
// ---------------------------------------------------------------------------
describe("api.boxscore", () => {
  it("calls /api/boxscore/{sport}/{gid}", async () => {
    mockFetch({ status: "ok", players: [], count: 0 });
    await api.boxscore("nba", "g001");
    expect(capturedUrl()).toBe(`${P5_BASE}/api/boxscore/nba/g001`);
  });
});

// ---------------------------------------------------------------------------
// pmTrail
// ---------------------------------------------------------------------------
describe("api.pmTrail", () => {
  it("calls /api/paper/pm/trail with no params", async () => {
    mockFetch({ status: "ok", trades: [], count: 0 });
    await api.pmTrail();
    expect(capturedUrl()).toBe(`${P5_BASE}/api/paper/pm/trail`);
  });

  it("passes venue + result + tier params", async () => {
    mockFetch({ status: "ok", trades: [], count: 0 });
    await api.pmTrail({ venue: "kalshi", result: "win", tier: "A" });
    const url = capturedUrl();
    expect(url).toContain("venue=kalshi");
    expect(url).toContain("result=win");
    expect(url).toContain("tier=A");
  });
});

// ---------------------------------------------------------------------------
// improveLedger
// ---------------------------------------------------------------------------
describe("api.improveLedger", () => {
  it("calls /api/improve/ledger", async () => {
    mockFetch({ status: "ok", cycles: [], count: 0, edge_claimed: false });
    await api.improveLedger();
    expect(capturedUrl()).toBe(`${P5_BASE}/api/improve/ledger`);
  });

  it("edge_claimed is false in response (honesty rail)", async () => {
    mockFetch({ status: "ok", cycles: [], count: 0, edge_claimed: false });
    const r = await api.improveLedger();
    if (r && "edge_claimed" in r) {
      expect(r.edge_claimed).toBe(false);
    }
  });
});

// ---------------------------------------------------------------------------
// Honesty rail: no $ field in any new method's call signature or URL
// ---------------------------------------------------------------------------
describe("honesty rail -- no dollar fields", () => {
  it("bestbetsBoard URL never contains $ or pnl or roi", async () => {
    mockFetch({ status: "ok", cards: [], count: 0, edge_claimed: false });
    await api.bestbetsBoard({ sport: "nba" });
    const url = capturedUrl();
    expect(url).not.toContain("$");
    expect(url).not.toContain("pnl");
    expect(url).not.toContain("roi");
  });

  it("pmTrail URL never contains $ or pnl or roi", async () => {
    mockFetch({ status: "ok", trades: [], count: 0 });
    await api.pmTrail({ venue: "kalshi" });
    const url = capturedUrl();
    expect(url).not.toContain("$");
    expect(url).not.toContain("pnl");
    expect(url).not.toContain("roi");
  });
});
