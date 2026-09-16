import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { getDashboardData } from "@/lib/analytics/dashboardData";
import { Coverage } from "./Coverage";

const data = getDashboardData();
describe("dossier coverage panel", () => {
  it("renders the derived category median separately from the published score", () => {
    render(<Coverage data={data} sport="nba" />);
    const panel = screen.getByRole("heading", { name: "How complete are player dossiers?" }).closest("section")!;
    expect(within(panel).getByText((_, element) => element?.textContent === "median categories filled: 18 of 28 (64.3%)")).toBeInTheDocument();
    expect(within(panel).getByText((_, element) => element?.textContent === "published completeness score: 46.4%")).toBeInTheDocument();
  });

  it("states the artifact limitation and renders the published histogram", () => {
    render(<Coverage data={data} sport="nba" />);
    const histogram = screen.getByRole("img", { name: "Categories filled histogram" });
    expect(within(histogram).getByText("82 dossiers (6.6%)")).toBeInTheDocument();
    expect(screen.getByText("Pace Fit")).toBeInTheDocument();
    expect(screen.getByText("The artifact does not define how the published completeness score is derived.")).toBeInTheDocument();
  });
});
