// RTL unit tests for EmptyState component.
import { render, screen } from "@testing-library/react";
import { EmptyState } from "@/components/board/EmptyState";

describe("EmptyState", () => {
  it("renders a default 'No games' heading and default message when no props supplied", () => {
    render(<EmptyState />);
    expect(
      screen.getByRole("heading", { name: /no games right now/i })
    ).toBeInTheDocument();
    expect(
      screen.getByText(/nothing scheduled for this selection/i)
    ).toBeInTheDocument();
  });

  it("renders custom message and does not show the default message text", () => {
    const custom = "No games match your filter.";
    render(<EmptyState message={custom} />);
    expect(screen.queryByText(custom)).toBeInTheDocument();
    expect(
      screen.queryByText(/nothing scheduled for this selection/i)
    ).not.toBeInTheDocument();
  });
});
