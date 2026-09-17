import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import EffectiveSampleSizePage from "./page";

it("labels the ledger as the joined-corpus revision 1 measurement and carries the under-review notice", () => {
  render(<EffectiveSampleSizePage />);
  const notice = screen.getByRole("complementary", { name: "Data integrity" });
  expect(notice).toHaveAttribute("data-status", "under-review");
  expect(within(notice).getByText("ess_ledger")).toBeInTheDocument();
  expect(within(notice).getByText(/residual_autocorrelation/)).toBeInTheDocument();
  expect(screen.getByText(/this ledger is the joined-corpus measurement, revision 1/i)).toBeInTheDocument();
  expect(screen.getByText(/recomposition on the segment-clean corpus is\s+pending/i)).toBeInTheDocument();
});

it("stops instructing readers to widen every interval", () => {
  render(<EffectiveSampleSizePage />);
  expect(screen.getByRole("columnheader", { name: "Implied interval-width factor" })).toBeInTheDocument();
  expect(screen.queryByRole("columnheader", { name: "CI must widen by" })).not.toBeInTheDocument();
  expect(screen.getByText(/not an instruction to scale a published interval/i)).toBeInTheDocument();
  expect(screen.getByText(/re-estimated by cluster bootstrap/i)).toBeInTheDocument();
  expect(screen.queryByText(/must therefore be widened/i)).not.toBeInTheDocument();
});
