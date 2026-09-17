import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getTennisAdaptationResearch } from "@/lib/analytics/researchTennisAdaptation";
import { getLibraryEntries } from "@/lib/analytics/libraryData";
import { loadScoutCorpus } from "@/lib/analytics/scoutCorpus.server";
import { resolveQuestion } from "@/lib/analytics/askSearch";
import ResearchDetail from "./ResearchDetail";
import * as table from "../lab/LabTable";

const analyses = getTennisAdaptationResearch();
beforeEach(() => window.history.replaceState(null, "", `/analytics/research/${analyses[0].id}/`));
afterEach(() => vi.restoreAllMocks());

describe("Published ATP gap comparisons", () => {
  it.each([
    [0, "Alexander Zverev", "0.38 pp", "5.98 pp", "5.6 pp"],
    [1, "Novak Djokovic", "-3.52 pp", "2.39 pp", "5.91 pp"],
  ] as const)("preserves both operands and scales analysis %i once", (index, player, delta, recent, corpus) => {
    render(<ResearchDetail analysis={analyses[index]} related={[]} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: player } });
    fireEvent.click(screen.getByRole("button", { name: new RegExp(`^Inspect ${player}`) }));
    const selected = screen.getByRole("region", { name: "Selected measurement" });
    for (const [label, value] of [["Recent minus corpus", delta], ["Recent gap", recent], ["Corpus gap", corpus]]) {
      const term = within(selected).getByText(label, { selector: "dt" });
      expect(within(term.parentElement!).getByText(value, { selector: "dd" })).toBeVisible();
    }
    expect(within(selected).getByRole("region", { name: "Calculation inputs" })).toBeVisible();
    expect(screen.getByText(analyses[index].caveat)).toBeVisible();
  });

  it("exports filtered raw fractions with the original scope and limits", () => {
    const exportCSV = vi.spyOn(table, "exportLabCSV").mockImplementation(() => undefined);
    render(<ResearchDetail analysis={analyses[0]} related={[]} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "Alexander Zverev" } });
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    const [dataset, rows] = exportCSV.mock.calls[0];
    expect(rows).toHaveLength(1);
    expect(rows[0].values.recent_minus_career).toBeCloseTo(.0038, 10);
    expect(rows[0].values).toMatchObject({ recent_gap: .0598, career_gap: .056 });
    const csv = table.buildLabCSV(dataset, rows);
    expect(csv).toContain("atlas_tennis_manifest");
    expect(csv).toContain("2015-2025");
    expect(csv).toContain("2023-01-01");
  });

  it("exposes both analyses in the library and cited Scout answers", () => {
    const library = getLibraryEntries();
    const scout = loadScoutCorpus();
    for (const analysis of analyses) {
      const path = `/analytics/research/${analysis.id}/`;
      expect(library.find(entry => entry.id === analysis.id)).toMatchObject({ kind: "derived", sport: "tennis", href: path, rows: analysis.rows.length, asOf: analysis.asOf });
      expect(resolveQuestion(`Explain the analysis: ${analysis.title}`, scout)).toMatchObject({
        kind: "direct", entry: { bucket: "public-derived-analysis", a: { explore_path: path, as_of: analysis.asOf, source_artifact: "webapp/public/data/showcase/atlas_tennis_manifest.json" } },
      });
    }
  });
});
