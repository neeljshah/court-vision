import { getResearchAnalyses } from "@/lib/analytics/researchData";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { getDashboardData } from "@/lib/analytics/dashboardData";
import Workspace from "./Workspace";

const data = getDashboardData();
const launchCounts = { paperCount: data.paperCount, novelCount: data.novelCount, findingCount: data.findingCount };
describe("analytics workspace interactions", () => {
  it("switches quality metrics and preserves the unscorable state", () => {
    render(<Workspace data={data} calibrationExample={null} {...launchCounts} />);
    expect(screen.getByRole("group", { name: "Filter analytics by sport" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Quality metric" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "ECE" }));
    expect(screen.getByRole("table", { name: "Mlb monthly ece measurements" })).toHaveTextContent("0.1265");
    expect(screen.getByText("Not scored")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Tennis" }));
    expect(screen.getByText(/No market-type scores published/)).toBeInTheDocument();
    expect(screen.queryByText("0.1668")).not.toBeInTheDocument();
  });
  it("combines sport, search and verdict filters in the ledger", () => {
    render(<Workspace data={data} calibrationExample={null} {...launchCounts} />);
    fireEvent.click(screen.getByRole("button", { name: "Tennis" }));
    fireEvent.click(screen.getByRole("button", { name: "Research ledger" }));
    fireEvent.change(screen.getByLabelText("Search research"), { target: { value: "surface" } });
    expect(screen.getByRole("status")).toHaveTextContent("9 matching records");
    fireEvent.change(screen.getByLabelText("Research verdict"), { target: { value: "not_testable" } });
    expect(screen.getByRole("status")).toHaveTextContent("3 matching records");
  });
  it("finds a real entity and builds its published route", () => {
    render(<Workspace data={data} calibrationExample={null} {...launchCounts} />);
    fireEvent.click(screen.getByRole("button", { name: "Entity atlas" }));
    fireEvent.change(screen.getByLabelText("Search entities"), { target: { value: "Jokic" } });
    expect(screen.getByRole("status")).toHaveTextContent("1 matching profiles");
    expect(screen.getByRole("link", { name: /Nikola Jokic/ })).toHaveAttribute("href", expect.stringContaining("/analytics/players/nba_players/nikola_jokic/"));
  });
  it("resets module pagination after a search and shows an empty state", () => {
    render(<Workspace data={data} calibrationExample={null} {...launchCounts} />);
    fireEvent.click(screen.getByRole("button", { name: "All analytics" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Page 2 / 7")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Search analytics modules"), { target: { value: "calibration" } });
    expect(screen.getByText("Page 1 / 1")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("7 matching modules");
    fireEvent.change(screen.getByLabelText("Search analytics modules"), { target: { value: "zzzznomatch" } });
    expect(screen.getByText(/No matching modules/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });
  it("changes pitch measurements without mixing denominators", () => {
    render(<Workspace data={data} calibrationExample={null} {...launchCounts} />);
    fireEvent.click(screen.getByRole("button", { name: "Inspect Changeup" }));
    const panel = screen.getByRole("heading", { name: "Inside the pitch corpus" }).closest("section")!;
    expect(within(panel).getByText("71,270 pitches in mix")).toBeInTheDocument();
    expect(within(panel).getByText("86.3")).toBeInTheDocument();
  });
  it("shows the derived analysis count and six latest published analyses", () => {
    render(<Workspace data={data} calibrationExample={null} {...launchCounts} />);
    expect(screen.getByRole("button", { name: /Derived analyses/ })).toHaveTextContent(String(getResearchAnalyses().length));
    const recent = screen.getByRole("heading", { name: "Recently added analyses" }).closest("section")!;
    const links = within(recent).getAllByRole("link");
    expect(links).toHaveLength(6);
    expect(links.every(link => link.getAttribute("href")?.startsWith("/analytics/research/") ?? false)).toBe(true);
  });
  it("keeps the nine primary destinations without duplicate launch links", () => {
    render(<Workspace data={data} calibrationExample={null} {...launchCounts} />);
    const launch = screen.getByRole("navigation", { name: "Explore published sports and research" });
    expect(within(launch).getAllByRole("link")).toHaveLength(9);
    expect(screen.queryByRole("link", { name: /open the library/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /source records/i })).not.toBeInTheDocument();
  });
});
