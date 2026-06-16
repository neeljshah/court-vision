/** RTL tests for SortSelect -- label, options, value reflection, onChange. */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { SortSelect } from "@/components/board/SortSelect";
import type { SortMode } from "@/lib/sort";

describe("SortSelect", () => {
  it("renders a labeled select accessible by /sort/i", () => {
    render(<SortSelect value="default" onChange={vi.fn()} />);
    expect(screen.getByLabelText(/sort/i)).toBeInTheDocument();
  });

  it("renders the three option labels", () => {
    render(<SortSelect value="default" onChange={vi.fn()} />);
    expect(screen.getByRole("option", { name: /default/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /biggest favorite/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /starting soonest/i })).toBeInTheDocument();
  });

  it("reflects the value prop as the selected option", () => {
    const { rerender } = render(<SortSelect value="default" onChange={vi.fn()} />);
    const select = screen.getByLabelText(/sort/i) as HTMLSelectElement;
    expect(select.value).toBe("default");

    rerender(<SortSelect value="favorite" onChange={vi.fn()} />);
    expect(select.value).toBe("favorite");

    rerender(<SortSelect value="soonest" onChange={vi.fn()} />);
    expect(select.value).toBe("soonest");
  });

  it("calls onChange with 'favorite' when the user selects Biggest favorite", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<SortSelect value="default" onChange={onChange} />);

    await user.selectOptions(screen.getByLabelText(/sort/i), "favorite");

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith("favorite" satisfies SortMode);
  });

  it("calls onChange with 'soonest' when the user selects Starting soonest", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<SortSelect value="default" onChange={onChange} />);

    await user.selectOptions(screen.getByLabelText(/sort/i), "soonest");

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith("soonest" satisfies SortMode);
  });
});
