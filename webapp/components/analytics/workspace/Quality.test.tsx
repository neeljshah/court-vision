import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { getDashboardData } from "@/lib/analytics/dashboardData";
import { Quality } from "./Quality";

const data = getDashboardData();

describe("Quality", () => {
  it("renders the supplied monthly count and range", () => {
    render(<Quality data={data} sport="all" snapshot={{ ...data.snapshot, monthCount: 3, monthRange: "2030-01 to 2030-03" }} />);
    expect(screen.getByText(/Only the 3 published months are shown\./)).toBeInTheDocument();
    expect(screen.getByText(/2030-01 to 2030-03\. Changes in cohort composition/)).toBeInTheDocument();
  });

  it("gives an empty market score state a library route", () => {
    render(<Quality data={data} sport="tennis" snapshot={data.snapshot} />);
    expect(screen.getByRole("link", { name: "Open the Library." })).toHaveAttribute("href", expect.stringMatching(/^\/analytics\/browse\/?$/));
  });
});
