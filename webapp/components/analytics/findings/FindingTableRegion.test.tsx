import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { FindingTableRegion } from "./FindingTableRegion";

it("provides a keyboard-focusable, named horizontal-scroll region", () => {
  render(<FindingTableRegion label="Published measurements"><table><tbody><tr><td>1</td></tr></tbody></table></FindingTableRegion>);
  const region = screen.getByRole("region", { name: "Published measurements scroll horizontally" });
  expect(region).toHaveAttribute("tabindex", "0");
  expect(region).toHaveAttribute("data-scroll-region");
  expect(screen.getByText("Scroll horizontally for all columns.")).toBeInTheDocument();
});
