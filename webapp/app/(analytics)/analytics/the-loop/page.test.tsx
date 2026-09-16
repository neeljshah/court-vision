import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import TheLoopPage from "./page";

describe("TheLoopPage", () => {
  it("renders the rerun ledger and all published flip links", () => {
    render(<TheLoopPage />);
    expect(screen.getByRole("heading", { name: "Claim family ledger" })).toBeInTheDocument();
    const links = screen.getAllByRole("link", { name: "View full history" });
    expect(links).toHaveLength(5);
    expect(links.every(link => link.getAttribute("href")?.startsWith("#claim-family-"))).toBe(true);
  });
});
