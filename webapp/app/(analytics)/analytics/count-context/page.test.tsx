import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CountContextPage from "./page";

describe("CountContextPage", () => {
  it("renders the published count-context analysis", () => {
    render(<CountContextPage />);
    expect(screen.getByRole("heading", { name: "Pitch profiles for every count." })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Exact MLB count explorer" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /^Use count / })).toHaveLength(12);
    expect(screen.getByRole("region", { name: "behind pitch mix table" })).toBeInTheDocument();
  });
});
