import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { validationResearch } from "@/lib/analytics/researchValidation";
import { getBrierSkillScoresResearch } from "@/lib/analytics/researchBrierSkillScores";
import ResearchDetail from "./ResearchDetail";

const analysis = validationResearch().find(item => item.id === "answer-evidence-coverage")!;

beforeEach(() => window.history.replaceState(null, "", "/analytics/research/answer-evidence-coverage/"));

describe("published evidence without a comparable population", () => {
  it("opens directly on source-ordered rows while keeping denominators separate", () => {
    render(<ResearchDetail analysis={analysis} related={[]} />);
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("button", { name: /^Inspect / }).map(button => button.getAttribute("aria-label")))
      .toEqual(["Inspect Answerable stress prompts", "Inspect Regression-bank checks"]);
    expect(within(table).getByRole("cell", { name: "36.6%" })).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: "100%" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Order" })).toBeDisabled();
    expect(screen.queryByRole("region", { name: "Measurement summary" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Inspect Answerable stress prompts" }));
    const detail = screen.getByRole("region", { name: "Selected measurement" });
    expect(detail).toHaveTextContent("863");
    expect(detail).toHaveTextContent("547");
    expect(within(detail).queryByRole("region", { name: "Measurement context" })).not.toBeInTheDocument();
  });

  it("respects an explicit chart link and resets it to the usable evidence table", () => {
    window.history.replaceState(null, "", "?view=rank&utm_source=shared");
    render(<ResearchDetail analysis={analysis} related={[]} />);
    expect(screen.getByRole("button", { name: "Ranked bars" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByText(/Rankings, distributions, and relative positions require/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reset view" }));
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    expect(new URLSearchParams(window.location.search).get("view")).toBeNull();
    expect(new URLSearchParams(window.location.search).get("utm_source")).toBe("shared");
  });

  it("shows all source rows immediately when leaving a comparable sport", () => {
    render(<ResearchDetail analysis={getBrierSkillScoresResearch()[0]} related={[]} />);
    expect(screen.getByRole("button", { name: "Ranked bars" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("combobox", { name: "Population" })).toHaveValue("sport=soccer_intl");
    fireEvent.change(screen.getByRole("combobox", { name: "Population" }), { target: { value: "all" } });
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getAllByRole("table")).toHaveLength(2);
    expect(screen.getByRole("region", { name: "Whole-corpus estimates" })).toHaveTextContent("International soccer");
    expect(screen.queryByRole("region", { name: "Measurement summary" })).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Order" })).toBeDisabled();
    expect(new URLSearchParams(window.location.search).get("population")).toBe("all");
    fireEvent.change(screen.getByRole("combobox", { name: "Population" }), { target: { value: "sport=soccer_intl" } });
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("combobox", { name: "Order" })).toBeEnabled();
  });
});
