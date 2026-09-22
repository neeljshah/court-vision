import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Receipt } from "./Receipt";

describe("Receipt", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("links a published artifact using the deployment base path", () => {
    vi.stubEnv("NEXT_PUBLIC_BASE_PATH", "/court-vision");
    render(<Receipt sourceArtifact="blowout_dynamics.json" asOf="2026-07-25" verdict="descriptive_only" />);
    fireEvent.click(screen.getByRole("button", { name: /receipt/i }));
    expect(screen.getByRole("link", { name: "blowout_dynamics.json" })).toHaveAttribute(
      "href",
      "/court-vision/data/showcase/blowout_dynamics.json"
    );
  });

  it("marks an artifact absent from the export instead of creating a dead link", () => {
    render(<Receipt sourceArtifact="private_measurement.json" verdict="descriptive_only" />);
    fireEvent.click(screen.getByRole("button", { name: /receipt/i }));
    expect(screen.getByText(/private_measurement\.json \(not published\)/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "private_measurement.json" })).not.toBeInTheDocument();
  });

  it("opens a published atlas source link and preserves its source-date label", () => {
    vi.stubEnv("NEXT_PUBLIC_BASE_PATH", "/court-vision");
    const source = "webapp/public/data/showcase/atlas_tennis_manifest.json";
    render(<Receipt sourceArtifact={source} asOf="2026-07-19" verdict="descriptive_only" />);
    const button = screen.getByRole("button", { name: /Source as of 2026-07-19/ });
    fireEvent.click(button);
    const link = screen.getByRole("link", { name: source, exact: true });
    expect(link).toHaveAttribute("href", "/court-vision/data/showcase/atlas_tennis_manifest.json");
    expect(link).toHaveAttribute("download");
    expect(screen.queryByText(/not published/)).not.toBeInTheDocument();
    expect(button).toHaveAttribute("aria-expanded", "true");
    fireEvent.keyDown(link, { key: "Escape" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("link", { name: source, exact: true })).not.toBeInTheDocument();
  });

  it("treats a placeholder snapshot date as absent", () => {
    render(<Receipt sourceArtifact="blowout_dynamics.json" asOf="Published snapshot" verdict="descriptive_only" />);
    fireEvent.click(screen.getByRole("button", { name: /receipt/i }));
    expect(screen.getByText("Date not published.")).toBeInTheDocument();
  });

  it("shows a published ISO date without accepting an arbitrary label", () => {
    render(<Receipt sourceArtifact="blowout_dynamics.json" asOf="2026-07-25" verdict="descriptive_only" />);
    const button = screen.getByRole("button", { name: /receipt/i });
    expect(within(button).getByText("Source as of 2026-07-25")).toBeInTheDocument();
  });

  it("retains explicit generation and observation-window labels", () => {
    const { rerender } = render(<Receipt sourceArtifact="blowout_dynamics.json" asOf="2026-07-25" dateKind="snapshot" verdict="descriptive_only" />);
    expect(screen.getByRole("button", { name: /Snapshot generated 2026-07-25/ })).toBeInTheDocument();
    rerender(<Receipt sourceArtifact="blowout_dynamics.json" asOf="2025-26 regular season" dateKind="window" verdict="descriptive_only" />);
    expect(screen.getByRole("button", { name: /Observation window 2025-26 regular season/ })).toBeInTheDocument();
  });

  it("marks its touch target for the shared receipt treatment", () => {
    render(<Receipt sourceArtifact="blowout_dynamics.json" verdict="descriptive_only" />);
    expect(screen.getByRole("button", { name: /receipt/i })).toHaveClass("receipt-trigger");
  });

  it.each([
    ["left", 20],
    ["middle", 160],
    ["right", 365],
  ])("keeps a %s phone-width receipt popover inside viewport gutters", (_position, left) => {
    vi.spyOn(window, "innerWidth", "get").mockReturnValue(390);
    vi.spyOn(window, "innerHeight", "get").mockReturnValue(844);
    render(<Receipt sourceArtifact="blowout_dynamics.json" verdict="descriptive_only" />);
    const button = screen.getByRole("button", { name: /receipt/i });
    const wrapper = button.parentElement as HTMLSpanElement;
    vi.spyOn(button, "getBoundingClientRect").mockReturnValue({ left, top: 100, bottom: 130 } as DOMRect);
    vi.spyOn(wrapper, "getBoundingClientRect").mockReturnValue({ left } as DOMRect);

    fireEvent.click(button);

    const popup = screen.getByRole("link", { name: "blowout_dynamics.json" }).parentElement as HTMLSpanElement;
    const viewportLeft = left + Number.parseFloat(popup.style.left);
    const popupWidth = Number.parseFloat(popup.style.width);
    expect(popupWidth).toBe(300);
    expect(viewportLeft).toBeGreaterThanOrEqual(12);
    expect(viewportLeft + popupWidth).toBeLessThanOrEqual(378);
  });

  it("uses the layout viewport width when a phone scrollbar takes space", () => {
    vi.spyOn(window, "innerWidth", "get").mockReturnValue(390);
    const original = Object.getOwnPropertyDescriptor(document.documentElement, "clientWidth");
    Object.defineProperty(document.documentElement, "clientWidth", { configurable: true, value: 375 });
    try {
      render(<Receipt sourceArtifact="blowout_dynamics.json" verdict="descriptive_only" />);
      const button = screen.getByRole("button", { name: /receipt/i });
      const wrapper = button.parentElement as HTMLSpanElement;
      vi.spyOn(button, "getBoundingClientRect").mockReturnValue({ left: 365, top: 100, bottom: 130 } as DOMRect);
      vi.spyOn(wrapper, "getBoundingClientRect").mockReturnValue({ left: 365 } as DOMRect);

      fireEvent.click(button);

      const popup = screen.getByRole("link", { name: "blowout_dynamics.json" }).parentElement as HTMLSpanElement;
      const viewportLeft = 365 + Number.parseFloat(popup.style.left);
      expect(viewportLeft).toBe(63);
      expect(viewportLeft + Number.parseFloat(popup.style.width)).toBe(363);
    } finally {
      if (original) Object.defineProperty(document.documentElement, "clientWidth", original);
      else delete (document.documentElement as { clientWidth?: number }).clientWidth;
    }
  });

  it("wraps a long receipt label inside its popover", () => {
    const label = "entries[entity=Novak Djokovic (ATP)].key_numbers.grass_wr_career";
    render(<Receipt sourceArtifact="blowout_dynamics.json" label={label} verdict="descriptive_only" />);
    fireEvent.click(screen.getByRole("button", { name: /receipt/i }));
    const heading = screen.getByText(label);
    expect(heading).toHaveStyle({ display: "block", overflowWrap: "anywhere" });
  });
});
