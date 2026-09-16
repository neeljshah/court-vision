import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import LibraryExplorer from "./LibraryExplorer";
import type { LibraryEntry } from "@/lib/analytics/libraryTypes";

const kindLabels: Record<LibraryEntry["kind"], string> = { source: "Source module", derived: "Derived analysis", finding: "Finding", inspector: "Inspector", explainer: "Explainer", paper: "Paper" };
const entry = (id: string, title: string, sport: LibraryEntry["sport"], kind: LibraryEntry["kind"], keywords: string): LibraryEntry => ({ id, title, sport, kind, kindLabel: kindLabels[kind], keywords, description: `${title} description`, category: "Methods", status: "published", href: `/analytics/research/${id}/`, asOf: kind === "source" ? "2026-07-25" : null, rows: 4, fields: 2, preview: [1, 2], previewLabel: "Published values", sourceSummary: kind === "source" ? { asOf: "2026-07-25", scope: "42 observed games", measurements: [{ label: "Games", value: "42" }], availability: "partial", previewRows: [[{ label: "Team", value: "A" }]] } : undefined });
const entries: LibraryEntry[] = [
  { ...entry("nba-formula", "NBA Pace Formula", "nba", "derived", "pace formula possession"), asOf: "2026-07-24" },
  entry("mlb-source", "MLB Pitch Source", "mlb", "source", "velocity pitch"),
  entry("soccer-form", "Soccer Form", "soccer", "derived", "form goals"),
  entry("shared-check", "Calibration Check", "all", "source", "calibration formula"),
  entry("calibration-by-game-checkpoint", "Calibration checkpoints", "all", "derived", "checkpoint calibration"),
];

describe("LibraryExplorer", () => {
  beforeEach(() => window.history.replaceState(null, "", "/analytics/browse/"));

  it("combines search, sport, and collection filters and restores them from the URL", async () => {
    window.history.replaceState(null, "", "/analytics/browse/?sport=nba&kind=derived&q=pace%20formula");
    render(<LibraryExplorer entries={entries} />);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent('1 entry including checks used across sports matching "pace formula"'));
    expect(screen.getByRole("heading", { name: "NBA Pace Formula" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "MLB Pitch Source" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Basketball" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.change(screen.getByRole("combobox", { name: "Entry type" }), { target: { value: "source" } });
    expect(screen.getByRole("status")).toHaveTextContent("0 entries");
    fireEvent.click(screen.getByRole("button", { name: "All sports" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Entry type" }), { target: { value: "all" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Search analytics library" }), { target: { value: "" } });
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("5 entries"));
  });

  it("resets an empty result to the full collection", () => {
    render(<LibraryExplorer entries={entries} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Search analytics library" }), { target: { value: "no such metric" } });
    expect(screen.getByText(/No analytics match these filters/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(screen.getByRole("status")).toHaveTextContent("5 entries");
    expect(window.location.search).toBe("");
  });

  it("shows a source snapshot, evidence measures, and availability label", () => {
    render(<LibraryExplorer entries={entries} />);
    expect(screen.getAllByText("2026-07-25")).not.toHaveLength(0);
    expect(screen.getAllByText("42 observed games")).not.toHaveLength(0);
    expect(screen.getAllByText("partial")).not.toHaveLength(0);
    expect(screen.getAllByText("Team")).not.toHaveLength(0);
  });

  it("shows a derived analysis snapshot using the source-card date treatment", () => {
    render(<LibraryExplorer entries={entries} />);
    expect(screen.getByText("2026-07-24")).toBeInTheDocument();
  });

  it("uses the entry's explicit reading-kind label on its card", () => {
    render(<LibraryExplorer entries={[entry("finding", "Published finding", "nba", "finding", "finding")]} />);
    expect(screen.getByText("Finding")).toBeInTheDocument();
  });

  it.each(["finding", "inspector", "explainer"] as const)("filters %s readings from links and the type selector", async (kind) => {
    const readings = [...entries, ...(["finding", "inspector", "explainer"] as const).map(item =>
      entry(`reading-${item}`, `Published ${item}`, "nba", item, "reading"))];
    window.history.replaceState(null, "", `/analytics/browse/?kind=${kind}`);
    render(<LibraryExplorer entries={readings} />);
    const select = screen.getByRole("combobox", { name: "Entry type" });
    await waitFor(() => expect(select).toHaveValue(kind));
    expect(screen.getByRole("status")).toHaveTextContent("1 entry");
    expect(screen.getByRole("heading", { name: `Published ${kind}` })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "NBA Pace Formula" })).not.toBeInTheDocument();
    fireEvent.change(select, { target: { value: "all" } });
    expect(screen.getByRole("status")).toHaveTextContent("8 entries");
    fireEvent.change(select, { target: { value: kind } });
    expect(screen.getByRole("status")).toHaveTextContent("1 entry");
    expect(window.location.search).toBe(`?kind=${kind}`);
  });

  it("restores a question-led collection from the URL and keeps it after a search", async () => {
    window.history.replaceState(null, "", "/analytics/browse/?collection=forecast-calibration");
    render(<LibraryExplorer entries={entries} />);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("1 entry in this question"));
    fireEvent.change(screen.getByRole("textbox", { name: "Search analytics library" }), { target: { value: "checkpoint" } });
    expect(window.location.search).toContain("collection=forecast-calibration");
    window.history.replaceState(null, "", "/analytics/browse/?sport=nba&kind=derived&q=pace");
    window.dispatchEvent(new PopStateEvent("popstate"));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent('1 entry including checks used across sports matching "pace"'));
  });

  it("restores page two from the URL and shows page one for an invalid page", async () => {
    const paged = Array.from({ length: 13 }, (_, index) => entry(`paged-${index}`, `Paged entry ${index + 1}`, "nba", "derived", "paged"));
    window.history.replaceState(null, "", "/analytics/browse/?page=2");
    const { unmount } = render(<LibraryExplorer entries={paged} />);
    await waitFor(() => expect(screen.getByText("Page 2 of 2")).toBeInTheDocument());
    expect(screen.getByRole("heading", { name: "Paged entry 13" })).toBeInTheDocument();
    unmount();

    window.history.replaceState(null, "", "/analytics/browse/?page=not-a-page");
    render(<LibraryExplorer entries={paged} />);
    await waitFor(() => expect(screen.getByText("Page 1 of 2")).toBeInTheDocument());
    expect(window.location.search).toBe("?page=not-a-page");
  });
});
