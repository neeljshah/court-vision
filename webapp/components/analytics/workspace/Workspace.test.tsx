import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { getDashboardData } from "@/lib/analytics/dashboardData";
import Workspace from "./Workspace";

const data = getDashboardData();
describe("analytics workspace interactions", () => {
  it("switches quality metrics and preserves the unscorable state", () => {
    render(<Workspace data={data} />);
    fireEvent.click(screen.getByRole("button", { name: "ECE", exact: true }));
    expect(screen.getByRole("table", { name: "Mlb monthly ece measurements" })).toHaveTextContent("0.1165");
    expect(screen.getByText("Not scored")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Tennis", exact: true }));
    expect(screen.getByText(/No market-type scores published/)).toBeInTheDocument();
    expect(screen.queryByText("0.2377")).not.toBeInTheDocument();
  });
  it("combines sport, search and verdict filters in the ledger", () => {
    render(<Workspace data={data} />);
    fireEvent.click(screen.getByRole("button", { name: "Tennis", exact: true }));
    fireEvent.click(screen.getByRole("button", { name: "Research ledger", exact: true }));
    fireEvent.change(screen.getByLabelText("Search research"), { target: { value: "surface" } });
    expect(screen.getByRole("status")).toHaveTextContent("9 matching records");
    fireEvent.change(screen.getByLabelText("Research verdict"), { target: { value: "not_testable" } });
    expect(screen.getByRole("status")).toHaveTextContent("3 matching records");
  });
  it("finds a real entity and builds its published route", () => {
    render(<Workspace data={data} />);
    fireEvent.click(screen.getByRole("button", { name: "Entity atlas", exact: true }));
    fireEvent.change(screen.getByLabelText("Search entities"), { target: { value: "Jokic" } });
    expect(screen.getByRole("status")).toHaveTextContent("1 matching profiles");
    expect(screen.getByRole("link", { name: /Nikola Jokic/ })).toHaveAttribute("href", expect.stringContaining("/analytics/players/nba_players/nikola_jokic/"));
  });
  it("resets module pagination after a search and shows an empty state", () => {
    render(<Workspace data={data} />);
    fireEvent.click(screen.getByRole("button", { name: "All analytics", exact: true }));
    fireEvent.click(screen.getByRole("button", { name: "Next", exact: true }));
    expect(screen.getByText("Page 2 / 7")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Search analytics modules"), { target: { value: "calibration" } });
    expect(screen.getByText("Page 1 / 1")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("6 matching modules");
    fireEvent.change(screen.getByLabelText("Search analytics modules"), { target: { value: "zzzznomatch" } });
    expect(screen.getByText(/No matching modules/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next", exact: true })).toBeDisabled();
  });
  it("changes pitch measurements without mixing denominators", () => {
    render(<Workspace data={data} />);
    fireEvent.click(screen.getByRole("button", { name: "Inspect Changeup" }));
    const panel = screen.getByRole("heading", { name: "Inside the pitch corpus" }).closest("section")!;
    expect(within(panel).getByText("71,270 pitches in mix")).toBeInTheDocument();
    expect(within(panel).getByText("86.3")).toBeInTheDocument();
  });
});
