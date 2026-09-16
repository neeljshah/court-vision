import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ModuleEvidence } from "./ModuleEvidence";
describe("ModuleEvidence", () => {
  it("states an unavailable finding and its missing input", () => {
    render(<ModuleEvidence evidence={{ availability: "unavailable", headline: "This measurement cannot be published because ages are absent.", missingInputs: ["Age Source Found"], coverage: [], analyses: [] }} />);
    expect(screen.getByLabelText("Published evidence status")).toHaveTextContent("cannot be published");
    expect(screen.getByText(/Age Source Found/)).toBeInTheDocument();
  });
  it("renders coverage rows for a partial artifact", () => {
    render(<ModuleEvidence evidence={{ availability: "partial", missingInputs: [], analyses: [], coverage: [{ population: "NBA", status: "ok", nGamesTotal: 12, nBucketsUsable: 2 }, { population: "TENNIS", status: "not_buildable", reason: "no map" }] }} />);
    expect(screen.getByText("NBA")).toBeInTheDocument();
    expect(screen.getByText("no map")).toBeInTheDocument();
  });
  it("links to a source module's interactive analysis", () => {
    render(<ModuleEvidence evidence={{ availability: "published", missingInputs: [], coverage: [], analyses: [{ id: "tennis-surface-support", title: "Surface Evidence Support" }] }} />);
    expect(screen.getByRole("link", { name: /Open the interactive analysis/ })).toHaveAttribute("href", "/analytics/research/tennis-surface-support");
  });
  it("links the Murphy source module to its interactive inspector", () => {
    render(<ModuleEvidence moduleId="murphy_decomposition" evidence={{ availability: "published", missingInputs: [], coverage: [], analyses: [] }} />);
    expect(screen.getByRole("link", { name: /Open the interactive inspector/ })).toHaveAttribute("href", "/analytics/score-decomposition");
  });
  it("does not offer an inspector for a module without one", () => {
    render(<ModuleEvidence moduleId="tennis_showcase" evidence={{ availability: "published", missingInputs: [], coverage: [], analyses: [{ id: "tennis-surface-support", title: "Surface Evidence Support" }] }} />);
    expect(screen.queryByRole("link", { name: /Open the interactive inspector/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Market overreaction operands")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Micro absorption operands")).not.toBeInTheDocument();
  });
  it("mounts the overreaction operands for the market movement module", () => {
    render(<ModuleEvidence moduleId="market_overreaction" evidence={{ availability: "published", missingInputs: [], coverage: [], analyses: [] }} />);
    expect(screen.getByLabelText("Market overreaction operands")).toBeInTheDocument();
  });
  it("mounts the absorption operands for the time-to-close module", () => {
    render(<ModuleEvidence moduleId="micro_absorption" evidence={{ availability: "published", missingInputs: [], coverage: [], analyses: [] }} />);
    expect(screen.getByLabelText("Micro absorption operands")).toBeInTheDocument();
  });
});
