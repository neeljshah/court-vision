import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

const DESTINATIONS = [
  ["Home", "/"],
  ["Games", "/games"],
  ["Risk", "/risk"],
  ["Progress", "/progress"],
  ["System", "/system"],
  ["How it works", "/how-it-works"],
] as const;

beforeEach(() => {
  localStorage.clear();
  vi.unstubAllEnvs();
  vi.resetModules();
  // Next's CommonJS link helper caches the build-time basePath at load time.
  for (const id of ["next/link", "next/dist/client/link", "next/dist/client/add-base-path"]) {
    delete require.cache[require.resolve(id)];
  }
});

async function renderGuide(basePath: string) {
  vi.stubEnv("__NEXT_ROUTER_BASEPATH", basePath);
  // Reload the actual Next Link implementation after selecting this build mode.
  vi.doMock("next/link", () => ({
    default: require("next/dist/client/link").default,
  }));
  const { OnboardingOverlay } = await import("./OnboardingOverlay");
  render(<OnboardingOverlay />);
  const dialog = await screen.findByRole("dialog");
  return within(dialog).getAllByRole("link");
}

describe("OnboardingOverlay page guide", () => {
  it.each([
    ["snapshot", "/court-vision"],
    ["root", ""],
  ])("uses the six correct %s deployment links", async (_mode, basePath) => {
    const links = await renderGuide(basePath);
    expect(links).toHaveLength(DESTINATIONS.length);
    DESTINATIONS.forEach(([label, destination], index) => {
      expect(links[index].textContent).toContain(label);
      expect(links[index]).toHaveAttribute(
        "href",
        `${basePath}${destination}`.replace(/\/$/, "") || "/",
      );
    });
  });

  it("closes on a guide link and remembers that the guide was seen", async () => {
    const links = await renderGuide("/court-vision");
    links[1].addEventListener("click", (event) => event.preventDefault(), { capture: true });
    fireEvent.click(links[1]);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(localStorage.getItem("cv-onboarded")).toBe("1");
    fireEvent.click(screen.getByRole("button", { name: /open the how-to-read-this guide/i }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });
});
