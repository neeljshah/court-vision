// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AnalyticsNavigation } from "./AnalyticsNavigation";
let path = "/court-vision/analytics/lab/";
vi.mock("next/navigation", () => ({ usePathname: () => path }));
afterEach(cleanup);
const links = [
  { href: "/analytics", label: "Overview" },
  { href: "/analytics/papers", label: "Papers" },
  { href: "/analytics/calibration", label: "Calibration" },
  { href: "/analytics/state-reliability", label: "State reliability" },
  { href: "/analytics/forecaster", label: "Forecaster" },
  { href: "/analytics/novel", label: "Experimental metrics" },
  { href: "/analytics/lab", label: "Measurement lab" },
  { href: "/analytics/compare", label: "Compare" },
  { href: "/analytics/browse", label: "Library" },
  { href: "/analytics/ask", label: "Ask Scout" },
];
it("updates active navigation when the client route changes", () => {
  const view = render(<AnalyticsNavigation links={links} />);
  expect(screen.getByRole("link", { name: "Measurement lab" }).getAttribute("aria-current")).toBe("page");
  path = "/analytics/m/statcast_showcase/";
  view.rerender(<AnalyticsNavigation links={links} />);
  expect(screen.getByRole("link", { name: "Measurement lab" }).getAttribute("aria-current")).toBeNull();
  expect(screen.getByRole("link", { name: "Library" }).getAttribute("aria-current")).toBe("page");
  path = "/court-vision/analytics/research/mlb-velocity-shape/";
  view.rerender(<AnalyticsNavigation links={links} />);
  expect(screen.getByRole("link", { name: "Library" }).getAttribute("aria-current")).toBe("page");
});

it("renders the ten header pillars in order and activates research descendants", () => {
  const view = render(<AnalyticsNavigation links={links} />);
  expect(screen.getAllByRole("link").map(link => link.textContent)).toEqual(links.map(link => link.label));
  expect(screen.queryByRole("link", { name: "Evidence" })).not.toBeInTheDocument();

  path = "/analytics/papers/age-and-production-lightly/";
  view.rerender(<AnalyticsNavigation links={links} />);
  expect(screen.getByRole("link", { name: "Papers" })).toHaveAttribute("aria-current", "page");

  path = "/analytics/novel/";
  view.rerender(<AnalyticsNavigation links={links} />);
  expect(screen.getByRole("link", { name: "Experimental metrics" })).toHaveAttribute("aria-current", "page");
});

it.each([
  ["/analytics/papers/example/", "Papers"],
  ["/analytics/calibration/example/", "Calibration"],
  ["/analytics/state-reliability/example/", "State reliability"],
  ["/analytics/forecaster/example/", "Forecaster"],
  ["/analytics/novel/example/", "Experimental metrics"],
  ["/analytics/lab/", "Measurement lab"],
  ["/analytics/compare/", "Compare"],
  ["/analytics/players/nba_players/example/", "Compare"],
  ["/analytics/ask/", "Ask Scout"],
  ["/analytics/about/", "Overview"],
  ["/analytics/explainers/example/", "Overview"],
  ["/analytics/evidence/", "Overview"],
  ["/analytics/findings/example/", "Library"],
  ["/analytics/research/example/", "Library"],
  ["/analytics/m/example/", "Library"],
  ["/analytics/browse/", "Library"],
  ["/analytics/score-decomposition/", "Library"],
  ["/analytics/residual-anatomy/", "Library"],
  ["/analytics/observation-dependence/", "Library"],
  ["/analytics/blowout-timing/", "Library"],
  ["/analytics/state-contrasts/", "Library"],
  ["/analytics/cross-sport-comparability/", "Library"],
  ["/analytics/pitch-sequencing/", "Library"],
  ["/analytics/count-context/", "Library"],
])("maps %s to exactly one active pillar", (route, label) => {
  path = route;
  render(<AnalyticsNavigation links={links} />);
  const active = screen.getAllByRole("link").filter(link => link.getAttribute("aria-current") === "page");
  expect(active).toHaveLength(1);
  expect(active[0]).toHaveTextContent(label);
});
