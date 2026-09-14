// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AnalyticsNavigation } from "./AnalyticsNavigation";
let path = "/court-vision/analytics/lab/";
vi.mock("next/navigation", () => ({ usePathname: () => path }));
afterEach(cleanup);
const links = [{ href: "/analytics", label: "Overview" }, { href: "/analytics/lab", label: "Lab" }, { href: "/analytics/browse", label: "Library" }];
it("updates active navigation when the client route changes", () => {
  const view = render(<AnalyticsNavigation links={links} />);
  expect(screen.getByRole("link", { name: "Lab" }).getAttribute("aria-current")).toBe("page");
  path = "/analytics/m/statcast_showcase/";
  view.rerender(<AnalyticsNavigation links={links} />);
  expect(screen.getByRole("link", { name: "Lab" }).getAttribute("aria-current")).toBeNull();
  expect(screen.getByRole("link", { name: "Library" }).getAttribute("aria-current")).toBe("page");
  path = "/court-vision/analytics/research/mlb-velocity-shape/";
  view.rerender(<AnalyticsNavigation links={links} />);
  expect(screen.getByRole("link", { name: "Library" }).getAttribute("aria-current")).toBe("page");
});
