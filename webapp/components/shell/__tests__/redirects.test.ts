import { existsSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { PREFIX_REDIRECTS, REDIRECTS, resolveRedirect } from "@/lib/redirects";

const APP = join(process.cwd(), "app");

describe("redirects", () => {
  it("every REDIRECTS key has a stub page", () => {
    for (const key of Object.keys(REDIRECTS)) {
      const rel = key.replace(/^\/|\/$/g, "");
      const found = ["(terminal)", "(analytics)", ""].some((g) => existsSync(join(APP, g, rel, "page.tsx")));
      expect(found, key).toBe(true);
    }
  });

  it("every target is a same-site absolute path", () => {
    const targets = [...Object.values(REDIRECTS).map((r) => r.to), ...PREFIX_REDIRECTS.map((r) => r.to)];
    for (const to of targets) {
      expect(to.startsWith("/") && !to.startsWith("//") && !/^\/?http/i.test(to), to).toBe(true);
    }
  });

  it("resolveRedirect covers each prefix family", () => {
    for (const { from, to } of PREFIX_REDIRECTS) {
      expect(resolveRedirect(`${from}sample-slug/deep`), from).toBe(to);
    }
    expect(resolveRedirect("/desk/")).toBeNull();
  });

  it("NotFoundBody inlines the same maps as lib/redirects", async () => {
    const { renderToStaticMarkup } = await import("react-dom/server");
    const { NotFoundBody } = await import("../NotFoundBody");
    const html = renderToStaticMarkup(NotFoundBody()).replace(/&quot;/g, '"').replace(/\u003c/g, "<");
    const exact = Object.fromEntries(Object.entries(REDIRECTS).map(([k, v]) => [k, v.to]));
    expect(html).toContain(JSON.stringify(exact));
    expect(html).toContain(JSON.stringify(PREFIX_REDIRECTS));
  });
});
