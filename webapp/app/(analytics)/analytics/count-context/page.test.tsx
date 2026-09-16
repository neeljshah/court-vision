import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CountContextPage from "./page";

describe("CountContextPage", () => {
  it("renders the published count-context analysis", () => {
    render(<CountContextPage />);
    expect(screen.getByRole("heading", { name: /Pitch mix by count class/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "behind pitch mix table" })).toBeInTheDocument();
  });
});
