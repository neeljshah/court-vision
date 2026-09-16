import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PaperArticle } from "./PaperArticle";
import { publishedArtifacts } from "@/lib/analytics/papers.server";
import { validatePaper, type Paper } from "@/lib/analytics/papers";

const fixture: Paper = {
  slug: "fixture-paper",
  title: "A fixture paper",
  subtitle: "Every block type, rendered once",
  authors: ["CourtVision research"],
  date: "2026-09-16",
  sport: "mlb",
  keywords: ["calibration"],
  abstract: "A fixture abstract that names its artifact and its denominator, 186 games, so the renderer has something to show.",
  sections: [
    {
      id: "question",
      heading: "Question",
      blocks: [
        { type: "p", text: "A paragraph block." },
        { type: "list", items: ["First list item", "Second list item"] },
        { type: "callout", label: "Verdict", text: "A callout with a label." },
        { type: "math", text: "Brier = mean((p - y)^2)" },
      ],
    },
    {
      id: "results",
      heading: "Results",
      blocks: [
        {
          type: "table",
          caption: "A table caption",
          columns: ["Bin", "Ticks (n)", "Gap"],
          rows: [["0.5 to 0.6", "17,652", "-0.0818"]],
          note: "A table source note.",
        },
        { type: "figure", module: "calibration_stability", caption: "A published chart caption." },
        { type: "figure", module: "state_conditioned_calibration", caption: "A source without a chart." },
      ],
    },
  ],
  evidence: [
    {
      artifact: "calibration_stability.json",
      module: "calibration_stability",
      asOf: "2026-07-23",
      fields: ["sports.mlb.sides.model_prob.brier"],
    },
    {
      artifact: "state_conditioned_calibration.json",
      module: "state_conditioned_calibration",
      asOf: null,
      fields: ["sports.mlb.model_ece_n_weighted"],
    },
  ],
  limitations: ["The fixture is not a corpus.", "One row is not a trend."],
  related: [
    { kind: "inspector", id: "calibration" },
    { kind: "module", id: "calibration_stability" },
  ],
};

describe("PaperArticle", () => {
  it("keeps the fixture valid against the shared contract", () => {
    expect(validatePaper(fixture, publishedArtifacts())).toBeNull();
  });

  it("renders every block type in the fixture", () => {
    render(<PaperArticle paper={fixture} />);
    expect(screen.getByText("A paragraph block.")).toBeInTheDocument();
    expect(screen.getByText("First list item")).toBeInTheDocument();
    expect(screen.getAllByText("Verdict").length).toBeGreaterThan(0);
    expect(screen.getAllByText("A callout with a label.").length).toBeGreaterThan(0);
    expect(screen.getByText("Brier = mean((p - y)^2)")).toBeInTheDocument();
    expect(screen.getByText("A table caption")).toBeInTheDocument();
    expect(screen.getByText("A table source note.")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Ticks (n)" })).toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: "0.5 to 0.6" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Calibration Stability chart/ })).toBeInTheDocument();
    expect(screen.getByText("A published chart caption.")).toBeInTheDocument();
    expect(screen.getByText("A source without a chart.")).toBeInTheDocument();
  });

  it("links a chartless figure block to its module page", () => {
    render(<PaperArticle paper={fixture} />);
    const card = screen.getByText("A source without a chart.").closest("a");
    expect(card).toHaveAttribute("href", expect.stringMatching(/\/analytics\/m\/state_conditioned_calibration\/?$/));
  });

  it("uses published data rather than a disapproved chart image", () => {
    const paper = {
      ...fixture,
      sections: [{ id: "results", heading: "Results", blocks: [{ type: "figure" as const, module: "ctx_team_states", caption: "A reviewed data fallback." }]}],
    };
    render(<PaperArticle paper={paper} />);
    expect(screen.getByTestId("published-data-figure")).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /Ctx Team States chart/ })).not.toBeInTheDocument();
  });

  it("builds a table of contents that points at every section", () => {
    render(<PaperArticle paper={fixture} />);
    const toc = screen.getByRole("navigation", { name: "Sections" });
    const links = within(toc).getAllByRole("link");
    expect(links).toHaveLength(fixture.sections.length);
    expect(links.map(link => link.getAttribute("href"))).toEqual(fixture.sections.map(section => `#${section.id}`));
    fixture.sections.forEach(section => expect(document.getElementById(section.id)).not.toBeNull());
  });

  it("lists every evidence artifact with its date, fields and module link", () => {
    render(<PaperArticle paper={fixture} />);
    const box = screen.getByRole("region", { name: "Evidence" });
    expect(within(box).getAllByRole("listitem").length).toBeGreaterThanOrEqual(fixture.evidence.length);
    expect(within(box).getByText("calibration_stability.json")).toBeInTheDocument();
    expect(within(box).getByText("as_of 2026-07-23")).toBeInTheDocument();
    expect(within(box).getByText("date not published")).toBeInTheDocument();
    expect(within(box).getByText("sports.mlb.sides.model_prob.brier")).toBeInTheDocument();
    expect(within(box).getAllByRole("link")).toHaveLength(fixture.evidence.length);
  });

  it("keeps evidence fields behind a disclosure", () => {
    render(<PaperArticle paper={fixture} />);
    const box = screen.getByRole("region", { name: "Evidence" });
    const inventory = within(box).getAllByText("Evidence field inventory (1 path)")[0];
    expect(inventory.closest("details")).not.toHaveAttribute("open");
    fireEvent.click(inventory);
    expect(inventory.closest("details")).toHaveAttribute("open");
  });

  it("shows the limitations and the resolved related links", () => {
    render(<PaperArticle paper={fixture} />);
    const limits = screen.getByRole("region", { name: /Limitations/ });
    expect(within(limits).getAllByRole("listitem")).toHaveLength(fixture.limitations.length);
    const related = screen.getByRole("region", { name: "Related" });
    const links = within(related).getAllByRole("link");
    expect(links).toHaveLength(fixture.related.length);
    expect(links[0]).toHaveAttribute("href", expect.stringMatching(/\/analytics\/calibration\/?$/));
    expect(within(related).getByText("Source module")).toBeInTheDocument();
  });

  it("does not repeat the standalone limitations list when a limitations section exists", () => {
    const paper = { ...fixture, sections: [...fixture.sections, { id: "limitations", heading: "Limitations", blocks: [{ type: "p" as const, text: "The section owns its limitation." }] }] };
    render(<PaperArticle paper={paper} />);
    expect(screen.getAllByRole("region", { name: /Limitations/ })).toHaveLength(1);
  });

  it("distinguishes prose and numeric table cells", () => {
    render(<PaperArticle paper={fixture} />);
    expect(screen.getByRole("rowheader", { name: "0.5 to 0.6" })).toHaveClass("paper-cell-prose");
    expect(screen.getByText("17,652")).toHaveClass("paper-cell-numeric");
  });

  it("mounts the integrity notice only when paper evidence is affected", () => {
    const { rerender } = render(<PaperArticle paper={fixture} />);
    expect(screen.getAllByRole("complementary", { name: "Data integrity" })[0]).toHaveTextContent("state_conditioned_calibration");
    rerender(<PaperArticle paper={{ ...fixture, evidence: [{ ...fixture.evidence[0], module: "mlb_count_leverage" }] }} />);
    expect(screen.queryByRole("complementary", { name: "Data integrity" })).not.toBeInTheDocument();
  });
});
