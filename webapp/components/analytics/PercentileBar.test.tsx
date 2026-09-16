// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { PercentileBar } from "./PercentileBar";

it("uses the field-specific ranked cohort in its caption", () => {
  render(<PercentileBar pct={82} nRanked={69} />);
  expect(screen.getByText("Percentile rank 82 among 69 measured profiles")).toBeInTheDocument();
});

it("reports a published tied percentile without a higher-than claim", () => {
  render(<PercentileBar pct={50} nRanked={44} />);
  expect(screen.getByText("Percentile rank 50 among 44 measured profiles")).toBeInTheDocument();
  expect(screen.queryByText(/Higher than/)).not.toBeInTheDocument();
});

it("omits the cohort when ranked support is unknown", () => {
  render(<PercentileBar pct={82} />);
  expect(screen.getByText("Percentile rank 82")).toBeInTheDocument();
  expect(screen.queryByText(/measured profiles/)).not.toBeInTheDocument();
});
