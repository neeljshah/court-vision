import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { RecordsClvSeries } from "../RecordsClvSeries";
import { CLV_UNAVAILABLE } from "@/lib/clvUnavailable";

// RecordsClvSeries draws no CLV curve; it renders the site-wide sentence.
describe("RecordsClvSeries", () => {
  it("renders the CLV sentence and no chart", () => {
    const { container } = render(<RecordsClvSeries clvSeries={null} loading={false} />);
    expect(screen.getByTestId("records-clv-series")).toHaveTextContent(CLV_UNAVAILABLE);
    expect(container.querySelector("svg")).toBeNull();
    expect(container.textContent ?? "").not.toMatch(/cum\. CLV|\$\s?\d/);
  });
});
