// LeagueSelect -- labeled native select for filtering by soccer league.

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";

import { LeagueSelect } from "@/components/board/LeagueSelect";
import { SOCCER_LEAGUES } from "@/types/board";

describe("LeagueSelect", () => {
  it("renders a labeled select associated with the League label", () => {
    render(<LeagueSelect league="eng.1" onChange={vi.fn()} />);
    expect(screen.getByLabelText(/league/i)).toBeInTheDocument();
  });

  it("renders options for every entry in SOCCER_LEAGUES", () => {
    render(<LeagueSelect league="" onChange={vi.fn()} />);
    const select = screen.getByLabelText(/league/i);
    for (const { label } of SOCCER_LEAGUES) {
      expect(
        Array.from((select as HTMLSelectElement).options).some(
          (o) => o.text === label
        )
      ).toBe(true);
    }
  });

  it("includes a World Cup option", () => {
    render(<LeagueSelect league="" onChange={vi.fn()} />);
    const select = screen.getByLabelText(/league/i) as HTMLSelectElement;
    expect(
      Array.from(select.options).some((o) => o.text === "World Cup")
    ).toBe(true);
  });

  it("includes a Premier League option", () => {
    render(<LeagueSelect league="" onChange={vi.fn()} />);
    const select = screen.getByLabelText(/league/i) as HTMLSelectElement;
    expect(
      Array.from(select.options).some((o) => o.text === "Premier League")
    ).toBe(true);
  });

  it("reflects the current league value in the select element", () => {
    render(<LeagueSelect league="eng.1" onChange={vi.fn()} />);
    const select = screen.getByLabelText(/league/i) as HTMLSelectElement;
    expect(select.value).toBe("eng.1");
  });

  it("calls onChange with the selected league value when user picks a different option", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<LeagueSelect league="eng.1" onChange={onChange} />);

    await user.selectOptions(
      screen.getByLabelText(/league/i),
      "fifa.world"
    );

    expect(onChange).toHaveBeenCalledOnce();
    expect(onChange).toHaveBeenCalledWith("fifa.world");
  });

  it("calls onChange with an empty string when All Leagues is selected", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<LeagueSelect league="eng.1" onChange={onChange} />);

    await user.selectOptions(screen.getByLabelText(/league/i), "");

    expect(onChange).toHaveBeenCalledWith("");
  });
});
