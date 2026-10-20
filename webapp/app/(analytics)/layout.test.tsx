// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("next/navigation", () => ({ usePathname: () => "/analytics/calibration/" }));
import AnalyticsGroupLayout from "./layout";

describe("analytics group layout", () => {
  it("wears the shared shell: one main nav, main landmark, footer", () => {
    render(<AnalyticsGroupLayout><p>Test</p></AnalyticsGroupLayout>);
    expect(screen.getAllByRole("navigation", { name: "Main" })).toHaveLength(1);
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
    expect(screen.getByRole("contentinfo")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Calibration" })).toHaveAttribute("aria-current", "page");
  });
});
