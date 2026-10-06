import { fireEvent, render, screen, within } from "@testing-library/react";
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

it("keeps historical counts labeled as proxies and links their ledger receipt", () => {
  render(<EffectiveSampleSizePage />);
  const table = screen.getByRole("table");
  expect(within(table).getByRole("columnheader", { name: "Stored series" })).toBeInTheDocument();
  expect(within(table).getByRole("columnheader", { name: "Published anchor (proxy)" })).toBeInTheDocument();
  expect(within(table).queryByRole("columnheader", { name: "Distinct games" })).not.toBeInTheDocument();
  expect(within(table).getByRole("cell", { name: "78,986" })).toBeInTheDocument();
  expect(within(table).getAllByRole("cell", { name: "227" })).toHaveLength(2);
  expect(within(table).getByRole("cell", { name: "9,003" })).toBeInTheDocument();
  expect(within(table).getAllByRole("cell", { name: "51" })).toHaveLength(2);
  expect(screen.getByText(/this count cannot establish how many distinct games/i)).toBeInTheDocument();
  expect(screen.queryByText(/independent information of at most/i)).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /Receipt: descriptive_only/ }));
  expect(screen.getByRole("link", { name: "webapp/public/data/showcase/ess_ledger.json" }))
    .toHaveAttribute("href", expect.stringMatching(/\/data\/showcase\/ess_ledger\.json$/));
});
