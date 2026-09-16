import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
// @ts-expect-error -- the executable scanner is deliberately dependency-free ESM.
import { scanRenderedText } from "../../../../../scripts/check-analytics-copy.mjs";
import RetractionPage from "./page";

it("renders retraction headings whose text clears the public-copy token check", () => {
  const { container } = render(<RetractionPage />);
  const headings = screen.getAllByRole("heading", { level: 2 });

  expect(headings).toHaveLength(6);
  expect(headings[0]).toHaveTextContent("+18.38%");
  expect(headings[5]).toHaveTextContent("2026-07-21");
  expect(scanRenderedText(container.textContent || "")).toEqual([]);
});
