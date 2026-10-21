import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RedirectStub, stubMetadata } from "@/components/shell/RedirectStub";
import { REDIRECTS } from "@/lib/redirects";

describe("redirect stub metadata", () => {
  it("every retired route is noindex, canonical on its destination, with its own description", () => {
    const seen = new Set<string>();
    for (const [from, r] of Object.entries(REDIRECTS)) {
      const m = stubMetadata(from);
      expect(m.robots, from).toEqual({ index: false, follow: true });
      expect(String(m.alternates?.canonical), from).toMatch(new RegExp(`${r.to.replace(/\//g, "\\/")}$`));
      expect(m.description, from).toContain(from);
      expect(seen.has(String(m.description)), `duplicate description for ${from}`).toBe(false);
      seen.add(String(m.description));
    }
  });
  it("keeps the meta refresh to the destination", () => {
    const { container } = render(<RedirectStub from="/today/" />);
    const refresh = container.querySelector('meta[http-equiv="refresh"]');
    expect(refresh?.getAttribute("content")).toMatch(/^0; url=.*\/desk\/$/);
  });
  it("refuses a route that is not in the redirect map", () => {
    expect(() => stubMetadata("/not-retired/")).toThrow(/lib\/redirects\.ts/);
  });
});
