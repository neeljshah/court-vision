// RTL tests for ThemeToggle -- cycles theme, exposes accessible aria-label.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, it, expect } from "vitest";
import { ThemeToggle } from "@/components/board/ThemeToggle";

afterEach(() => {
  localStorage.clear();
  document.documentElement.className = "";
});

describe("ThemeToggle", () => {
  it("renders a button with an accessible aria-label describing the next state", () => {
    render(<ThemeToggle />);
    const btn = screen.getByRole("button");
    // Must have an aria-label that is a non-empty string
    const label = btn.getAttribute("aria-label");
    expect(label).toBeTruthy();
    expect(typeof label).toBe("string");
    expect((label as string).length).toBeGreaterThan(0);
  });

  it("clicking the button cycles theme without throwing and the button stays present", async () => {
    const user = userEvent.setup();
    render(<ThemeToggle />);

    const btn = screen.getByRole("button");

    // Three clicks cover the full system->light->dark->system cycle
    await user.click(btn);
    expect(screen.getByRole("button")).toBeInTheDocument();

    await user.click(btn);
    expect(screen.getByRole("button")).toBeInTheDocument();

    await user.click(btn);
    expect(screen.getByRole("button")).toBeInTheDocument();
  });

  it("aria-label changes on each click to reflect the next state", async () => {
    const user = userEvent.setup();
    render(<ThemeToggle />);

    const btn = screen.getByRole("button");
    const labels: string[] = [];

    labels.push(btn.getAttribute("aria-label") ?? "");

    await user.click(btn);
    labels.push(btn.getAttribute("aria-label") ?? "");

    await user.click(btn);
    labels.push(btn.getAttribute("aria-label") ?? "");

    await user.click(btn);
    // After a full cycle the label returns to the original
    expect(btn.getAttribute("aria-label")).toBe(labels[0]);
    // All three intermediate labels must be non-empty and unique
    expect(new Set(labels).size).toBe(3);
  });
});
