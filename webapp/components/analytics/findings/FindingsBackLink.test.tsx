import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { FindingsBackLink } from "./FindingsBackLink";

it("links directly to the findings index", () => {
  render(<FindingsBackLink />);
  expect(screen.getByRole("link", { name: "Findings" })).toHaveAttribute("href", "/analytics/findings");
});
