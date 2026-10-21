// quotedOn: a text quotes an artifact by its full basename with extension, or by an
// identifier-shaped stem as a whole word; a short bare-word stem never matches prose or substrings.
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { quotedOn, quotes, routeTexts } from "@/lib/quotedOn.server";

const BOOKMAKER = "scripts/platformkit/analytics_showcase/out/bookmaker_accuracy.json";
const LATEST = "docs/evidence/forward/latest.json";

describe("quotes(text, artifact)", () => {
  it("matches the full basename, or an identifier-shaped stem as a whole word", () => {
    expect(quotes('loadArtifact("bookmaker_accuracy")', BOOKMAKER)).toBe(true);
    expect(quotes("out/bookmaker_accuracy.json", BOOKMAKER)).toBe(true);
    expect(quotes("the `mlb-ingame-integrity` join audit", "webapp/public/data/audits/mlb-ingame-integrity.json")).toBe(true);
    expect(quotes("docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md", "docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md")).toBe(true);
    expect(quotes("calibration_stability.json", "calibration_stability.json")).toBe(true);
  });

  it("does not match a longer identifier, a different extension or an empty name", () => {
    expect(quotes("bookmaker_accuracy_v2", BOOKMAKER)).toBe(false);
    expect(quotes("pre_bookmaker_accuracy", BOOKMAKER)).toBe(false);
    expect(quotes("bookmaker_accuracy.jsonl", "out/bookmaker_accuracy.jsonl")).toBe(true);
    expect(quotes("anything", "")).toBe(false);
  });

  it("a short bare-word stem matches only with its extension, never as prose or a substring", () => {
    expect(quotes("the latest night is served", LATEST)).toBe(false);
    expect(quotes("latestNight = ...", LATEST)).toBe(false);
    expect(quotes("reads desk_latest.json", LATEST)).toBe(false);
    expect(quotes("reads latest.jsonl", LATEST)).toBe(false);
    expect(quotes('join(dir, "latest.json")', LATEST)).toBe(true);
    expect(quotes("docs/evidence/forward/latest.json", LATEST)).toBe(true);
    // a date-only stem is prose too
    expect(quotes("2026-10-16 was the last served night", "docs/evidence/forward/2026-10-16.json")).toBe(false);
    expect(quotes("ledger 2026-10-16.json", "docs/evidence/forward/2026-10-16.json")).toBe(true);
  });
});

describe("quotedOn(artifact)", () => {
  it("a short stem produces no false quoted-on entries across routes and papers", () => {
    const dir = mkdtempSync(join(tmpdir(), "quoted-on-"));
    writeFileSync(join(dir, "PROSE.md"), "# Prose\n\nThe latest night is read from the ledger.\n");
    writeFileSync(join(dir, "NAMES.md"), "# Names\n\nThe desk reads `latest.json` each night.\n");
    const hits = quotedOn(LATEST, dir);
    expect(hits.filter((q) => q.label.startsWith("docs/papers/")).map((q) => q.label)).toEqual(["docs/papers/NAMES.md"]);
    // Routes whose text carries the bare word "latest" but never the file name are the trap.
    const trap = routeTexts().filter((r) => /\blatest\b/.test(r.text) && !r.text.includes("latest.json")).map((r) => r.route);
    expect(trap.length).toBeGreaterThan(0);
    const routes = hits.map((q) => q.href);
    for (const route of trap) expect(routes).not.toContain(route);
    for (const route of routes.filter((h) => h.startsWith("/"))) {
      expect(routeTexts().find((r) => r.route === route)!.text).toContain("latest.json");
    }
  });

  it("keeps the known quotes: the bookmaker finding page and the papers that name the DM memo", () => {
    expect(quotedOn(BOOKMAKER).map((q) => q.href)).toContain("/analytics/findings/bookmaker-accuracy/");
    expect(quotedOn("docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md").map((q) => q.label)).toContain("docs/papers/PREGAME_VS_CLOSE_2026.md");
    expect(quotedOn("docs/evidence/CANONICAL_FIGURES.json").map((q) => q.href)).toEqual(expect.arrayContaining(["/", "/analytics/calibration/"]));
  });
});
