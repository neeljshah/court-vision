import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import AnalyticsError from "@/app/(analytics)/error";

it("announces a recoverable view failure without exposing raw error details", () => {
  const error = Object.assign(new Error("private diagnostic payload"), { digest: "internal-digest" });
  render(<AnalyticsError error={error} reset={vi.fn()} />);
  expect(screen.getByRole("alert")).toHaveAccessibleName("Unable to display this view.");
  expect(screen.queryByText(/private diagnostic payload|internal-digest/)).not.toBeInTheDocument();
});

it("retries only when the reader requests it", () => {
  const reset = vi.fn();
  render(<AnalyticsError error={new Error("render failed")} reset={reset} />);
  expect(reset).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(reset).toHaveBeenCalledTimes(1);
});

it("keeps an analytics escape route available if retry cannot recover", () => {
  render(<AnalyticsError error={new Error("render failed")} reset={vi.fn()} />);
  expect(screen.getByRole("link", { name: "Back to home" })).toHaveAttribute("href", "/");
});
