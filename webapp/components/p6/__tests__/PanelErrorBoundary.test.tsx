// PanelErrorBoundary.test.tsx -- WS7: isolation tests for the PanelErrorBoundary
// class component.
//
// Acceptance criteria (WS7):
//   (a) Happy path: renders children unchanged.
//   (b) Error path: catches a render error -> shows panel-error-fallback, not white.
//   (c) Fallback contains no dollar-amount (honesty rail).
//   (d) Fallback has role="status" and aria-label derived from label prop.
//   (e) Fallback does not use red/danger classes (neutral amber only).

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { PanelErrorBoundary } from "../PanelErrorBoundary";

// A child that always throws.
function AlwaysThrows(): never {
  throw new Error("intentional test throw");
}

// A well-behaved child.
function GoodChild({ testId }: { testId: string }) {
  return <div data-testid={testId}>content ok</div>;
}

// Suppress React's console.error output for the expected error boundary log.
function suppressConsoleError() {
  return vi.spyOn(console, "error").mockImplementation(() => {});
}

describe("PanelErrorBoundary (WS7) -- happy path", () => {
  it("(a) renders children when no error is thrown", () => {
    render(
      <PanelErrorBoundary label="test panel">
        <GoodChild testId="good-child" />
      </PanelErrorBoundary>,
    );
    expect(screen.getByTestId("good-child")).toBeInTheDocument();
    expect(screen.queryByTestId("panel-error-fallback")).toBeNull();
  });

  it("(a) label prop does not appear in DOM on the happy path", () => {
    const { container } = render(
      <PanelErrorBoundary label="my-panel-label">
        <GoodChild testId="c2" />
      </PanelErrorBoundary>,
    );
    // Children present, fallback absent
    expect(container.textContent).toContain("content ok");
    expect(container.textContent).not.toContain("could not be displayed");
  });
});

describe("PanelErrorBoundary (WS7) -- error path", () => {
  it("(b) renders panel-error-fallback when child throws", () => {
    const spy = suppressConsoleError();
    render(
      <PanelErrorBoundary label="best bets board">
        <AlwaysThrows />
      </PanelErrorBoundary>,
    );
    const fallback = screen.getByTestId("panel-error-fallback");
    expect(fallback).toBeInTheDocument();
    spy.mockRestore();
  });

  it("(b) fallback body mentions the label prop", () => {
    const spy = suppressConsoleError();
    render(
      <PanelErrorBoundary label="venue summary">
        <AlwaysThrows />
      </PanelErrorBoundary>,
    );
    expect(screen.getByTestId("panel-error-fallback").textContent).toContain("venue summary");
    spy.mockRestore();
  });

  it("(b) fallback body contains 'unavailable' text", () => {
    const spy = suppressConsoleError();
    render(
      <PanelErrorBoundary label="pm trail table">
        <AlwaysThrows />
      </PanelErrorBoundary>,
    );
    const text = screen.getByTestId("panel-error-fallback").textContent ?? "";
    expect(text.toLowerCase()).toContain("unavailable");
    spy.mockRestore();
  });

  it("(d) fallback has role=status and correct aria-label", () => {
    const spy = suppressConsoleError();
    render(
      <PanelErrorBoundary label="my panel">
        <AlwaysThrows />
      </PanelErrorBoundary>,
    );
    const el = screen.getByRole("status", { name: /my panel unavailable/i });
    expect(el).toBeInTheDocument();
    spy.mockRestore();
  });

  it("(c) fallback contains no dollar-amount (honesty rail)", () => {
    const spy = suppressConsoleError();
    const { container } = render(
      <PanelErrorBoundary label="some board">
        <AlwaysThrows />
      </PanelErrorBoundary>,
    );
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
    spy.mockRestore();
  });

  it("(e) fallback uses amber tone, not red/danger classes", () => {
    const spy = suppressConsoleError();
    const { container } = render(
      <PanelErrorBoundary label="some board">
        <AlwaysThrows />
      </PanelErrorBoundary>,
    );
    const allClasses = Array.from(container.querySelectorAll("*"))
      .map((el) => el.className)
      .join(" ");
    expect(allClasses).toMatch(/amber/);
    expect(allClasses).not.toMatch(/text-red|bg-red|text-danger|text-destructive/);
    spy.mockRestore();
  });
});
