import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EvidenceGallery } from "./EvidenceGallery";

const charts = [
  { id: "alpha", title: "Alpha Archive", description: "Published calibration record.", status: "published" as const, asOf: "2026-07-01", imageSrc: "/alpha.png", sourceUrl: "https://example.com/source", evidenceUrl: null },
  { id: "beta", title: "Beta Archive", description: "Partial documentation.", status: "partial" as const, asOf: null, imageSrc: "/beta.png", sourceUrl: "https://example.com/source", evidenceUrl: "https://example.com/evidence" },
  { id: "novel_load_bearing_index", title: "Novel Load Bearing Index", description: "A descriptive coverage window.", status: "published" as const, asOf: "2024-25 (Elo end-of-season) x 2024_25 on/off slice", imageSrc: "/load.png", sourceUrl: "https://example.com/source", evidenceUrl: null },
  { id: "novel_schedule_fatigue_tax", title: "Novel Schedule Fatigue Tax", description: "Under review: the ORtg tax uses a scoring-margin receipt. Back-to-back counts remain descriptive.", status: "under-review" as const, asOf: null, imageSrc: "/fatigue.png", sourceUrl: "https://example.com/fatigue-source", evidenceUrl: null },
];

describe("EvidenceGallery", () => {
  it("combines text and documentation-status filters", () => {
    render(<EvidenceGallery charts={charts} />);
    expect(screen.getAllByText("Partial documentation").some((el) => el.tagName !== "OPTION" && el.className.includes("partial"))).toBe(true);
    fireEvent.change(screen.getByRole("textbox", { name: "Search charts" }), { target: { value: "beta" } });
    expect(screen.getByRole("status")).toHaveTextContent("1 chart shown");
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "published" } });
    expect(screen.getByRole("status")).toHaveTextContent("0 charts shown");
    expect(screen.getByText(/No charts match that search/)).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "partial" } });
    expect(screen.getByRole("status")).toHaveTextContent("1 chart shown");
    expect(screen.getByText("Beta Archive")).toBeInTheDocument();
  });

  it("opens an accessible larger chart view and closes on Escape", async () => {
    render(<EvidenceGallery charts={charts} />);
    const trigger = screen.getByRole("button", { name: "Open larger view of Alpha Archive" });
    trigger.focus();
    fireEvent.click(trigger);
    expect(screen.getByRole("dialog", { name: "Alpha Archive" })).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("preserves descriptive coverage stamps and normalizes punctuation in searches", () => {
    render(<EvidenceGallery charts={charts} />);
    expect(screen.getByText("As of 2024-25 (Elo end-of-season) x 2024_25 on/off slice")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Search charts" }), { target: { value: "Load-Bearing" } });
    expect(screen.getByRole("status")).toHaveTextContent("1 chart shown");
    expect(screen.getByText("Novel Load Bearing Index")).toBeInTheDocument();
  });

  it("uses a data figure for an unapproved PNG", () => {
    render(<EvidenceGallery charts={[{ id: "ctx_team_states", title: "Team states", description: "Published team measurements.", status: "published", asOf: "2026-05-21", imageSrc: "/ctx_team_states.png", sourceUrl: "https://example.com/source", evidenceUrl: null }]} />);
    const card = screen.getByRole("article");
    expect(within(card).getByTestId("published-data-figure")).toHaveTextContent("Published team measurements.");
    expect(within(card).queryByRole("img")).not.toBeInTheDocument();
    fireEvent.click(within(card).getByRole("button", { name: "Open larger view of Team states" }));
    expect(screen.getByRole("dialog", { name: "Team states" })).toHaveTextContent("Published team measurements.");
    expect(screen.getByRole("dialog").querySelector("img")).toBeNull();
  });

  it("separates an under-review card from Published and preserves its source-backed preview", () => {
    render(<EvidenceGallery charts={charts} />);
    const selector = screen.getByRole("combobox", { name: "Documentation status" });
    expect(within(selector).getByRole("option", { name: "Under review" })).toBeInTheDocument();
    const reviewCard = screen.getByRole("heading", { name: "Novel Schedule Fatigue Tax" }).closest("article")!;
    expect(within(reviewCard).getByText("Under review")).toBeVisible();
    expect(within(reviewCard).getByTestId("published-data-figure")).toHaveTextContent("Under-review data preview");
    expect(within(reviewCard).queryByRole("img")).not.toBeInTheDocument();
    expect(within(reviewCard).getByText("As-of not stamped")).toBeInTheDocument();
    fireEvent.change(selector, { target: { value: "published" } });
    expect(screen.queryByRole("heading", { name: "Novel Schedule Fatigue Tax" })).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("2 charts shown");
    fireEvent.change(selector, { target: { value: "under-review" } });
    expect(screen.getByRole("status")).toHaveTextContent("1 chart shown");
    fireEvent.click(screen.getByRole("button", { name: "Open larger view of Novel Schedule Fatigue Tax" }));
    const dialog = screen.getByRole("dialog", { name: "Novel Schedule Fatigue Tax" });
    expect(within(dialog).getByText("Under review")).toBeVisible();
    expect(within(dialog).getByText("As-of not stamped")).toBeInTheDocument();
    expect(dialog).toHaveTextContent("Derived effects are under review");
    expect(within(dialog).getByRole("link", { name: "Source module" })).toHaveAttribute("href", "https://example.com/fatigue-source");
    expect(within(dialog).queryByRole("img")).not.toBeInTheDocument();
  });
});
