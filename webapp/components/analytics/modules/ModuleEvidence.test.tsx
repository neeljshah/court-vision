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
    expect(screen.queryByLabelText("Rest asymmetry panels")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Starter rest absorption panels")).not.toBeInTheDocument();
  });
  it("mounts the overreaction operands for the market movement module", () => {
    render(<ModuleEvidence moduleId="market_overreaction" evidence={{ availability: "published", missingInputs: [], coverage: [], analyses: [] }} />);
    expect(screen.getByLabelText("Market overreaction operands")).toBeInTheDocument();
  });
  it("mounts the rest-asymmetry panels for the module whose artifact publishes panels", () => {
    render(<ModuleEvidence moduleId="novel_rest_asymmetry" evidence={{ availability: "published", missingInputs: [], coverage: [], analyses: [] }} />);
    const panel = screen.getByLabelText("Rest asymmetry panels");
    expect(panel).toHaveTextContent("Schedule population: 4,793 games");
    expect(panel).toHaveTextContent("Priced population: 1,103 games");
  });
  it("mounts starter-rest panels without replacing the rest-asymmetry panels", () => {
    const evidence = { availability: "published" as const, missingInputs: [], coverage: [], analyses: [] };
    const { rerender } = render(<ModuleEvidence moduleId="novel_starter_rest_absorption" evidence={evidence} />);
    expect(screen.getByLabelText("Starter rest absorption panels")).toBeInTheDocument();
    expect(screen.queryByLabelText("Rest asymmetry panels")).not.toBeInTheDocument();
    rerender(<ModuleEvidence moduleId="novel_rest_asymmetry" evidence={evidence} />);
    expect(screen.getByLabelText("Rest asymmetry panels")).toBeInTheDocument();
    expect(screen.queryByLabelText("Starter rest absorption panels")).not.toBeInTheDocument();
  });
  it("mounts the absorption operands for the time-to-close module", () => {
    render(<ModuleEvidence moduleId="micro_absorption" evidence={{ availability: "published", missingInputs: [], coverage: [], analyses: [] }} />);
    expect(screen.getByLabelText("Micro absorption operands")).toBeInTheDocument();
  });
});
