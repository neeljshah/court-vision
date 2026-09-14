import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import LibraryExplorer from "./LibraryExplorer";
import type { LibraryEntry } from "@/lib/analytics/libraryTypes";

const entry = (id: string, title: string, sport: LibraryEntry["sport"], kind: LibraryEntry["kind"], keywords: string): LibraryEntry => ({ id, title, sport, kind, keywords, description: `${title} description`, category: "Methods", status: "published", href: `/analytics/research/${id}/`, asOf: null, rows: 4, fields: 2, preview: [1, 2], previewLabel: "Published values" });
const entries: LibraryEntry[] = [
  entry("nba-formula", "NBA Pace Formula", "nba", "derived", "pace formula possession"),
  entry("mlb-source", "MLB Pitch Source", "mlb", "source", "velocity pitch"),
  entry("soccer-form", "Soccer Form", "soccer", "derived", "form goals"),
  entry("shared-check", "Calibration Check", "all", "source", "calibration formula"),
];

describe("LibraryExplorer", () => {
  beforeEach(() => window.history.replaceState(null, "", "/analytics/browse/"));

  it("combines search, sport, and collection filters and restores them from the URL", async () => {
    window.history.replaceState(null, "", "/analytics/browse/?sport=nba&kind=derived&q=pace%20formula");
    render(<LibraryExplorer entries={entries} />);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent('1 entry including shared diagnostics matching "pace formula"'));
    expect(screen.getByRole("heading", { name: "NBA Pace Formula" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "MLB Pitch Source" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Basketball" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.change(screen.getByRole("combobox", { name: "Collection" }), { target: { value: "source" } });
    expect(screen.getByRole("status")).toHaveTextContent("0 entries");
    fireEvent.click(screen.getByRole("button", { name: "All sports" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Collection" }), { target: { value: "all" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Search analytics library" }), { target: { value: "" } });
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("4 entries"));
  });

  it("resets an empty result to the full collection", () => {
    render(<LibraryExplorer entries={entries} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Search analytics library" }), { target: { value: "no such metric" } });
    expect(screen.getByText(/No analytics match these filters/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(screen.getByRole("status")).toHaveTextContent("4 entries");
    expect(window.location.search).toBe("");
  });
});
