import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { RecordsClvSeries } from "../RecordsClvSeries";
import { CLV_UNAVAILABLE } from "@/lib/clvUnavailable";

// The July snapshot's cumulative mean CLV (+12.99%) must never render.
describe("RecordsClvSeries percent values", () => {
  it("never prints a cumulative mean CLV percentage", () => {
    const series = { status: "ok", count: 1, series: [{ cumulative_mean_clv_pct: 12.99 }] } as never;
    render(<RecordsClvSeries clvSeries={series} />);
    const el = screen.getByTestId("records-clv-series");
    expect(el).toHaveTextContent(CLV_UNAVAILABLE);
    expect(el).not.toHaveTextContent("12.99");
  });
});
