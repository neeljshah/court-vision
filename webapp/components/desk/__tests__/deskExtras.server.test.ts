// deskExtras.server.test.ts -- the desk receipts fail loudly instead of silently: a
// FAIL/other check row or an undated report throws, uptime numerics are validated and
// the as-of comes from the receipt's file name, and the hand-typed census causes must
// sum to the canonical forward_window_counts figure.
import { describe, expect, it } from "vitest";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, relative } from "node:path";
import { FIGURES } from "@/lib/figures";
import { CENSUS, UPTIME_RE, UPTIME_SRC, loadChecks, loadUptime } from "../deskExtras.server";

const REPO = join(process.cwd(), "..");
const tmp = mkdtempSync(join(tmpdir(), "desk-extras-"));
/** Write a fixture and return its path relative to the repo root (what the loaders take). */
function fixture(name: string, body: unknown): string {
  const file = join(tmp, name);
  writeFileSync(file, typeof body === "string" ? body : JSON.stringify(body));
  return relative(REPO, file).replace(/\\/g, "/");
}

const asOf = "2026-10-20T15:15:11.913917+00:00";

describe("loadChecks", () => {
  it("counts FAIL/ERROR/unknown rows as other and throws so they cannot vanish from the sentence", () => {
    const rel = fixture("fail.json", [
      { module: "a.py", status: "PASS", as_of: asOf }, { module: "b.py", status: "FAIL", as_of: asOf },
      { module: "c.py", status: "NO_CHECK", as_of: asOf }, { module: "d.py", as_of: asOf },
    ]);
    expect(() => loadChecks(rel)).toThrow(/2 of 4 module self-checks are FAIL\/other: b\.py=FAIL, d\.py=missing/);
  });

  it("throws when no row carries an as_of, instead of printing 'report as of '", () => {
    const rel = fixture("undated.json", [{ module: "a.py", status: "PASS" }, { module: "b.py", status: "NO_CHECK" }]);
    expect(() => loadChecks(rel)).toThrow(/no row carries an as_of/);
  });

  it("returns pass, noCheck, other=0 and the newest as_of day; a missing report is null", () => {
    const rel = fixture("clean.json", [
      { module: "a.py", status: "PASS", as_of: "2026-10-19T01:00:00+00:00" },
      { module: "b.py", status: "PASS", as_of: asOf }, { module: "c.py", status: "NO_CHECK", as_of: asOf },
    ]);
    expect(loadChecks(rel)).toEqual({ pass: 2, noCheck: 1, other: 0, total: 3, asOf: "2026-10-20" });
    expect(loadChecks(relative(REPO, join(tmp, "missing.json")))).toBeNull();
    const real = loadChecks();
    expect(real).not.toBeNull();
    expect(real!.other).toBe(0);
    expect(real!.pass + real!.noCheck).toBe(real!.total);
    expect(real!.asOf).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});

describe("loadUptime", () => {
  const good = {
    days: 2, scheduled: 2, served: 5, scored: 2, scored_complete: 1, scored_partial: 1, scored_share: 1,
    no_receipt_days: 0, partial_reasons: { ceiling_exceeded: 1 },
    table: [
      { date: "2026-09-24", scheduled: true, served: 4, night: "PARTIAL", reasons: ["ceiling_exceeded"], attempt_file: false },
      { date: "2026-09-25", scheduled: true, served: 1, night: "COMPLETE", reasons: [], attempt_file: false },
    ],
  };

  it("derives the as-of from the file name and validates every numeric with Number.isFinite", () => {
    const ok = loadUptime(fixture("DESK_UPTIME_2026-09-25.json", good));
    expect(ok).toMatchObject({ asOf: "2026-09-25", window: "2026-09-24 to 2026-09-25", days: 2, share: 1, complete: 1 });
    expect(() => loadUptime(fixture("DESK_UPTIME_2026-09-26.json", { ...good, scored_share: "0.76" })))
      .toThrow(/"scored_share" must be a finite number, got "0.76"/);
    expect(() => loadUptime(fixture("DESK_UPTIME_2026-09-27.json", { ...good, table: [] }))).toThrow(/non-empty array of days/);
    expect(() => loadUptime(fixture("uptime.json", good))).toThrow(/DESK_UPTIME_<YYYY-MM-DD>\.json/);
    expect(() => loadUptime(fixture("DESK_UPTIME_2026-09-28.json", "{not json"))).toThrow(/not valid JSON/);
    expect(loadUptime("docs/evidence/DESK_UPTIME_1999-01-01.json")).toBeNull();
  });

  it("reads the newest committed receipt, whose name carries its as-of", () => {
    const name = UPTIME_SRC.split("/").pop()!;
    expect(name).toMatch(UPTIME_RE);
    const real = loadUptime();
    expect(real).not.toBeNull();
    expect(real!.asOf).toBe(UPTIME_RE.exec(name)![1]);
    for (const k of ["days", "scheduled", "served", "scored", "complete", "partial", "share", "noReceipt"] as const) {
      expect(Number.isFinite(real![k]), k).toBe(true);
    }
  });
});

describe("CENSUS", () => {
  it("takes its served total from forward_window_counts and its causes sum to it", () => {
    const fwd = FIGURES.forward_window_counts;
    expect(CENSUS.served).toBe(fwd.games_served);
    expect(CENSUS.causes.reduce((a, c) => a + c.n, 0)).toBe(fwd.games_served);
    expect(CENSUS.pass).toBe(Number(fwd.qualified_of_judged.split(" of ")[0]));
    expect(CENSUS.window).toBe(`2026-10-06 to ${fwd.window_end}`);
    expect(CENSUS.asOf).toBe("2026-10-20");
  });
});
