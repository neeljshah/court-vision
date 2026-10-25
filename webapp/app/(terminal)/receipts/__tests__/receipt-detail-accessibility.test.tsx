import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import ReceiptDrillPage from "../[row]/page";

afterEach(cleanup);

function renderReceipt(row: string) {
  return render(<main id="main-content"><ReceiptDrillPage params={{ row }} /></main>);
}

describe("receipt detail accessibility", () => {
  it.each(["8", "11", "15", "17", "missing"])("keeps the shell's sole main landmark for row %s", (row) => {
    renderReceipt(row);
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
    expect(screen.getByRole("link", { name: /receipts/ })).toBeVisible();
  });

  it.each(["8", "15"])("makes the model confidence-interval table keyboard reachable for row %s", (row) => {
    renderReceipt(row);
    const region = screen.getByRole("region", { name: "Model calibration confidence intervals" });
    expect(region).toHaveAttribute("tabindex", "0");
    expect(within(region).getByRole("table")).toBeVisible();
    region.focus();
    expect(region).toHaveFocus();
  });
});
