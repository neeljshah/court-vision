import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Receipt } from "./Receipt";

describe("Receipt", () => {
  afterEach(() => vi.unstubAllEnvs());

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
});
