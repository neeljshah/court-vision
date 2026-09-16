import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import VerdictFlipsPage from "./page";

it("renders the published flip cases with ledger links", () => {
  render(<VerdictFlipsPage />);

  expect(screen.getByRole("heading", { name: "When we changed our mind" })).toBeInTheDocument();
  const links = screen.getAllByRole("link", { name: "View full ledger history" });
  expect(links).toHaveLength(5);
  expect(links.every(link => link.getAttribute("href")?.startsWith("/analytics/the-loop#claim-family-"))).toBe(true);
});
