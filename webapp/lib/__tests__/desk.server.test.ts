import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { fmt, loadDesk, parseDesk, refusalsFor, type Desk } from "../desk.server";

const base = {
  schema: "desk_export_v1", date: "2026-10-06", header: "PAPER DESK -- paper only", generated_at_utc: "x",
  record: null, scoreboard: null, coverage: null, ingame: null, execution: null, models: null, health: null,
  sources: [], retracted_token_hits: [],
  refusals: [{ section: "ingame", reason: "missing" }, { section: "execution.markouts", reason: "empty" },
    { section: "ingamex", reason: "other" }],
};

describe("desk.server", () => {
  it("loads a staged export and rejects a wrong schema", () => {
    const dir = mkdtempSync(join(tmpdir(), "desk-"));
    const f = join(dir, "latest.json");
    writeFileSync(f, JSON.stringify(base));
    expect(loadDesk(f)?.date).toBe("2026-10-06");
    expect(parseDesk(JSON.stringify({ ...base, schema: "other" }))).toBeNull();
    expect(parseDesk("{not json")).toBeNull();
    expect(loadDesk(join(dir, "absent.json"))).toBeNull();
  });

  it("refusalsFor matches a section and its children only", () => {
    const d = base as unknown as Desk;
    expect(refusalsFor(d, "ingame").map((r) => r.reason)).toEqual(["missing"]);
    expect(refusalsFor(d, "execution")).toHaveLength(1);
    expect(refusalsFor(null, "record")[0].reason).toMatch(/not staged/);
  });

  it("fmt renders null as a dash, never a zero", () => {
    expect(fmt(null)).toBe("-");
    expect(fmt(0.12345)).toBe("0.1235");
  });
});
