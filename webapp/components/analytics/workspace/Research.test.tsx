import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Mechanism } from "@/lib/analytics/dashboardTypes";
import { Research } from "./Research";

const row: Mechanism = {
  sport: "tennis",
  mechanism: "break_point_conversion_by_set_number",
  verdict: "NOT_TESTABLE",
  bucket: "not_testable",
  effect: null,
  p: null,
  evidence: "No qualifying corpus",
  corpus: "tennis",
  as_of: null,
};

describe("research ledger search", () => {
  it.each([
    "break point conversion by set number",
    "break_point_conversion_by_set_number",
  ])("matches human-readable and identifier queries: %s", query => {
    render(<Research rows={[row]} sport="tennis" />);
    fireEvent.change(screen.getByLabelText("Research verdict"), {
      target: { value: "not_testable" },
    });
    fireEvent.change(screen.getByLabelText("Search research"), {
      target: { value: query },
    });

    expect(screen.getByRole("status")).toHaveTextContent("1 matching records");
    expect(screen.getByText("Break Point Conversion By Set Number")).toBeInTheDocument();
  });
});
