import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EvidenceGallery } from "./EvidenceGallery";

const charts = [
  { id: "alpha", title: "Alpha Archive", description: "Published calibration record.", status: "published" as const, asOf: "2026-07-01", imageSrc: "/alpha.png", sourceUrl: "https://example.com/source", evidenceUrl: null },
  { id: "beta", title: "Beta Archive", description: "Partial documentation.", status: "partial" as const, asOf: null, imageSrc: "/beta.png", sourceUrl: "https://example.com/source", evidenceUrl: "https://example.com/evidence" },
  { id: "novel_load_bearing_index", title: "Novel Load Bearing Index", description: "A descriptive coverage window.", status: "published" as const, asOf: "2024-25 (Elo end-of-season) x 2024_25 on/off slice", imageSrc: "/load.png", sourceUrl: "https://example.com/source", evidenceUrl: null },
];

describe("EvidenceGallery", () => {
  it("combines text and documentation-status filters", () => {
    render(<EvidenceGallery charts={charts} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Search published charts" }), { target: { value: "beta" } });
    expect(screen.getByRole("status")).toHaveTextContent("1 published chart shown");
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "published" } });
    expect(screen.getByRole("status")).toHaveTextContent("0 published charts shown");
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
    fireEvent.change(screen.getByRole("textbox", { name: "Search published charts" }), { target: { value: "Load-Bearing" } });
    expect(screen.getByRole("status")).toHaveTextContent("1 published chart shown");
    expect(screen.getByText("Novel Load Bearing Index")).toBeInTheDocument();
  });
});
