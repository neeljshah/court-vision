// @vitest-environment jsdom
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/analytics/fonts", () => ({ analyticsFontVars: "analytics-fonts" }));
vi.mock("next/navigation", () => ({ usePathname: () => "/analytics", useSearchParams: () => new URLSearchParams(), useRouter: () => ({ push: () => undefined, replace: () => undefined }) }));
import AnalyticsRootLayout from "./layout";

afterEach(() => {
  document.body.innerHTML = "";
  document.documentElement.setAttribute("data-theme", "light");
  localStorage.clear();
});

describe("analytics theme control", () => {
  it("publishes and updates its pressed state and next-action label", () => {
    const markup = renderToStaticMarkup(<AnalyticsRootLayout><p>Test</p></AnalyticsRootLayout>);
    const scripts = [...markup.matchAll(/<script>([\s\S]*?)<\/script>/g)];
    const chrome = scripts.at(-1)?.[1];
    expect(markup).toContain('aria-pressed="false"');
    expect(markup).toContain('aria-label="Switch to dark theme"');
    expect(chrome).toBeTruthy();

    document.body.innerHTML = '<button id="a-theme-toggle" type="button"></button>';
    window.eval(chrome || "");
    const toggle = document.getElementById("a-theme-toggle")!;
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
    expect(toggle.getAttribute("aria-label")).toBe("Switch to dark theme");
    toggle.click();
    expect(toggle.getAttribute("aria-pressed")).toBe("true");
    expect(toggle.getAttribute("aria-label")).toBe("Switch to light theme");
  });
});
