// RTL tests for ErrorState -- alert role, message text, heading, retry callback.
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"
import { ErrorState } from "@/components/board/ErrorState"

describe("ErrorState", () => {
  it("wraps content in an alert region", () => {
    render(<ErrorState message="Network failure" onRetry={vi.fn()} />)
    expect(screen.getByRole("alert")).toBeInTheDocument()
  })

  it("renders a heading matching /could not load/i", () => {
    render(<ErrorState message="Network failure" onRetry={vi.fn()} />)
    expect(
      screen.getByRole("heading", { name: /could not load/i })
    ).toBeInTheDocument()
  })

  it("displays the message text", () => {
    render(<ErrorState message="Network failure" onRetry={vi.fn()} />)
    expect(screen.getByText("Network failure")).toBeInTheDocument()
  })

  it("renders a Retry button", () => {
    render(<ErrorState message="Network failure" onRetry={vi.fn()} />)
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument()
  })

  it("calls onRetry when Retry is clicked", async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    render(<ErrorState message="Request timed out" onRetry={onRetry} />)
    await user.click(screen.getByRole("button", { name: /retry/i }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it("onRetry is not called before any interaction", () => {
    const onRetry = vi.fn()
    render(<ErrorState message="Request timed out" onRetry={onRetry} />)
    expect(onRetry).not.toHaveBeenCalled()
  })
})
