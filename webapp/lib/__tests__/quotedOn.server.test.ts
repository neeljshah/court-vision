// quotedOn.server.test.ts -- the "quoted on" match is a whole-token match (an identifier
// that merely contains the stem never counts), a stem under 8 characters is refused, and
// the papers corpus is read once per build.
import { describe, expect, it } from "vitest";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { MIN_STEM, quotedOn, stemMatcher } from "../quotedOn.server";

describe("stemMatcher", () => {
  it("matches the stem only as a whole token", () => {
    const re = stemMatcher("bookmaker_accuracy");
    expect(re.test('loadArtifact("bookmaker_accuracy")')).toBe(true);
    expect(re.test("out/bookmaker_accuracy.json")).toBe(true);
    expect(re.test("bookmaker_accuracy")).toBe(true);
    expect(re.test("bookmaker_accuracy_v2")).toBe(false);
    expect(re.test("old_bookmaker_accuracy")).toBe(false);
    expect(stemMatcher("DM_RECOMPUTE_2026-09-24").test("see docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md")).toBe(true);
  });
});

describe("quotedOn", () => {
  it("refuses a stem under the minimum instead of matching by accident", () => {
    expect(MIN_STEM).toBe(8);
    expect(() => quotedOn("scripts/x/out/ess.json")).toThrow(/"ess" of scripts\/x\/out\/ess\.json is under 8 characters/);
    expect(() => quotedOn("out/ess_ledger.json")).not.toThrow();
  });

  it("lists the finding page for a staged artifact and reads the papers corpus once", () => {
    const papersDir = mkdtempSync(join(tmpdir(), "papers-"));
    writeFileSync(join(papersDir, "a.md"), "cites `bookmaker_accuracy.json` here");
    writeFileSync(join(papersDir, "b.md"), "mentions bookmaker_accuracy_v2 only");
    const first = quotedOn("scripts/platformkit/analytics_showcase/out/bookmaker_accuracy.json", papersDir);
    expect(first.some((q) => q.href === "/analytics/findings/bookmaker-accuracy/")).toBe(true);
    expect(first.filter((q) => q.label.startsWith("docs/papers/")).map((q) => q.label)).toEqual(["docs/papers/a.md"]);
    writeFileSync(join(papersDir, "c.md"), "bookmaker_accuracy again"); // not re-read: computed once per build
    const again = quotedOn("bookmaker_accuracy.json", papersDir);
    expect(again.filter((q) => q.label.startsWith("docs/papers/")).map((q) => q.label)).toEqual(["docs/papers/a.md"]);
  });
});
