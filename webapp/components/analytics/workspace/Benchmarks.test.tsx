import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { getDashboardData } from "@/lib/analytics/dashboardData";
import { Benchmarks } from "./Benchmarks";

const data = getDashboardData();

describe("Benchmarks", () => {
  it("renders the supplied benchmark artifact date", () => {
    render(<Benchmarks data={data} sport="all" snapshot={{ ...data.snapshot, benchmarkAsOf: "2030-04-05" }} />);
    expect(screen.getByText(/2030-04-05\. Delta direction follows the original artifact/)).toBeInTheDocument();
  });
});
