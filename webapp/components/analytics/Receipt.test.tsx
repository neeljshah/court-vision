import { fireEvent, render, screen } from "@testing-library/react";
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
    fireEvent.click(screen.getByRole("button", { name: /date not published/i }));
    expect(screen.getAllByText("Date not published.")).toHaveLength(2);
  });
});
