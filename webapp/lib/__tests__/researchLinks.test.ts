import { describe, expect, it } from "vitest";
import { join } from "node:path";
import { loadWorkingPapers, parseWorkingPaper } from "@/lib/analytics/workingPapers.server";
import { quotedOn, routeFor } from "@/lib/quotedOn.server";
import { BANNED_COPY, RETRACTED_TOKENS } from "@/lib/packetVerdicts";

describe("working papers (docs/papers/*.md)", () => {
  it("parses title, date and a three-sentence abstract", () => {
    const p = parseWorkingPaper("X.md", "# A title\n\nNeel Shah. Drafted 2026-10-20.\n\n**Summary.** One. Two here. Three now. Four never.\n")!;
    expect(p).toMatchObject({ title: "A title", date: "2026-10-20", abstract: "One. Two here. Three now.", file: "docs/papers/X.md" });
    expect(parseWorkingPaper("Y.md", "no heading")).toBeNull();
  });

  it("loads the three readouts with abstracts free of banned copy and retracted figures", () => {
    const papers = loadWorkingPapers();
    expect(papers.length).toBe(3);
    for (const p of papers) {
      expect(p.abstract.length).toBeGreaterThan(40);
      expect(BANNED_COPY.test(p.abstract), p.abstract).toBe(false);
      for (const t of RETRACTED_TOKENS) expect(p.abstract).not.toContain(t);
    }
  });
});

describe("quoted-on generator", () => {
  it("maps page files to routes with route groups dropped", () => {
    expect(routeFor(join(process.cwd(), "app", "(analytics)", "analytics", "calibration", "page.tsx"))).toBe("/analytics/calibration/");
    expect(routeFor(join(process.cwd(), "app", "(terminal)", "page.tsx"))).toBe("/");
  });

  it("lists the home and calibration pages for the canonical figures file, and the pregame paper for the DM memo", () => {
    const canon = quotedOn("docs/evidence/CANONICAL_FIGURES.json").map((q) => q.href);
    expect(canon).toEqual(expect.arrayContaining(["/", "/analytics/calibration/"]));
    const dm = quotedOn("docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md").map((q) => q.label);
    expect(dm).toContain("docs/papers/PREGAME_VS_CLOSE_2026.md");
  });
});
