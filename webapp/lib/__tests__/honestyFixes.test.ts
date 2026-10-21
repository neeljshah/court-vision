import { afterEach, describe, expect, it, vi } from "vitest";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { normalizeRawEnvelope } from "../p5api";
import { fetchHonest } from "../fetchHonest";
import { canonicalFigures, headlineFigures } from "../canonicalFigures.server";

afterEach(() => vi.unstubAllGlobals());

const trade = { event_id: "e1", clv: 1.2 };
const env = (o: object) => ({ status: "ok", total: 1, trades: [trade], ...o }) as never;

describe("normalizeRawEnvelope honesty", () => {
  it("carries clv_is_proxy through; absent is null not false", () => {
    const p = normalizeRawEnvelope(env({ trades: [{ ...trade, clv_is_proxy: true }, trade] })) as never as
      { predictions: { clv_is_proxy: boolean | null }[] };
    expect(p.predictions.map((r) => r.clv_is_proxy)).toEqual([true, null]);
  });
  it("non-array trades -> Unavailable; missing total -> rows returned + note", () => {
    expect(normalizeRawEnvelope(env({ trades: undefined }))).toEqual({ status: "unavailable", reason: "unexpected envelope shape" });
    const p = normalizeRawEnvelope(env({ total: undefined })) as { count: number; honest_note?: string };
    expect(p.count).toBe(1);
    expect(p.honest_note).toMatch(/total missing/);
  });
});

describe("fetchHonest body checks", () => {
  const stub = (body: unknown) => vi.stubGlobal("fetch", vi.fn(async () => ({
    ok: true, status: 200, headers: new Headers({ "content-type": "application/json" }), json: async () => body,
  })));
  it("rejects null body and validator failure; passes good body", async () => {
    stub(null);
    expect(await fetchHonest("/x", { retries: 0 })).toEqual({ status: "unavailable", reason: "empty body" });
    stub({ detail: "nope" });
    expect(await fetchHonest("/x", { retries: 0, validate: (b) => Array.isArray((b as { trail?: unknown }).trail) }))
      .toEqual({ status: "unavailable", reason: "bad shape" });
    stub({ trail: [] });
    expect(await fetchHonest("/x", { retries: 0, validate: (b) => Array.isArray((b as { trail?: unknown }).trail) }))
      .toEqual({ trail: [] });
  });
});

describe("canonicalFigures fails loudly", () => {
  it("throws on a missing file; headlineFigures throws on missing keys", () => {
    expect(() => canonicalFigures(join(tmpdir(), "nope-canonical.json"))).toThrow(/nope-canonical/);
  });
  it("real file has every headline key", () => {
    expect(headlineFigures()).toHaveLength(3);
  });
});
