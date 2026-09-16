// @vitest-environment jsdom
import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { ComparisonEntity } from "@/lib/analytics/comparisonData";
import { ProfileHeading } from "./CompareResultParts";

vi.mock("next/link", () => ({ default: ({ children, ...props }: React.ComponentProps<"a">) => <a {...props}>{children}</a> }));

const alpha: ComparisonEntity = { slug: "alpha", name: "Alpha", values: {}, percentiles: {} };

it("keeps a closest-comparable pair together in its compare URL", () => {
  render(<ProfileHeading entity={alpha} pack="nba_players" label="Profile A" hasPackComparables comparables={[{ slug: "beta", name: "Beta", score: 0.983 }]} />);
  const list = screen.getByRole("list");
  expect(within(list).getByRole("link", { name: "Compare with Alpha" })).toHaveAttribute("href", "/analytics/compare?pack=nba_players&a=alpha&b=beta");
});

it("keeps the antipode pair together in its compare URL", () => {
  render(<ProfileHeading entity={alpha} pack="nba_players" label="Profile A" hasPackComparables antipode={{ slug: "gamma", name: "Gamma", score: -0.983 }} />);
  const antipode = screen.getByText("Most distant profile").parentElement;
  expect(antipode).not.toBeNull();
  expect(within(antipode as HTMLElement).getByRole("link", { name: "Compare with Alpha" })).toHaveAttribute("href", "/analytics/compare?pack=nba_players&a=alpha&b=gamma");
});
