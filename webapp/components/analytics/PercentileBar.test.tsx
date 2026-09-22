// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { PercentileBar } from "./PercentileBar";

it("uses the field-specific ranked cohort in its caption", () => {
  render(<PercentileBar pct={31} nRanked={184} />);
  const caption = "Percentile rank 31 among 184 measured profiles";

  expect(screen.getByText(caption)).toBeInTheDocument();
  expect(screen.getByRole("img", { name: caption })).toBeInTheDocument();
  expect(screen.queryByRole("img", { name: /31th/ })).not.toBeInTheDocument();
});

it("reports a published tied percentile without a higher-than claim", () => {
  render(<PercentileBar pct={50} nRanked={44} />);
  expect(screen.getByText("Percentile rank 50 among 44 measured profiles")).toBeInTheDocument();
  expect(screen.queryByText(/Higher than/)).not.toBeInTheDocument();
});

it("omits the cohort when ranked support is unknown", () => {
  render(<PercentileBar pct={82} />);
  expect(screen.getByText("Percentile rank 82")).toBeInTheDocument();
  expect(screen.getByRole("img", { name: "Percentile rank 82" })).toBeInTheDocument();
  expect(screen.queryByText(/measured profiles/)).not.toBeInTheDocument();
});
