import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Figure } from "./Figure";

describe("Figure", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("links a published source through the deployment base path", () => {
    vi.stubEnv("NEXT_PUBLIC_BASE_PATH", "/court-vision");
    render(<Figure source="data/showcase/blowout_dynamics.json" asOf="2026-07-25"><div>Chart</div></Figure>);
    expect(screen.getByRole("link", { name: "data/showcase/blowout_dynamics.json" })).toHaveAttribute(
      "href",
      "/court-vision/data/showcase/blowout_dynamics.json"
    );
  });

  it("prints a not-published fallback rather than a dead link", () => {
    render(<Figure source="private_measurement.json" asOf="2026-07-25"><div>Chart</div></Figure>);
    expect(screen.getByText("private_measurement.json (not published)")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "private_measurement.json" })).not.toBeInTheDocument();
  });

  it("treats a placeholder snapshot date as absent", () => {
    render(<Figure source="data/showcase/blowout_dynamics.json" asOf="Published snapshot"><div>Chart</div></Figure>);
    expect(screen.getByText("Date not published.")).toBeInTheDocument();
  });

  it("prints published row and game denominators", () => {
    render(<Figure source="data/showcase/blowout_dynamics.json" asOf="2026-07-25" nRows={78986} nGames={1234}><div>Chart</div></Figure>);
    expect(screen.getByText("n rows=78,986; n games=1,234")).toBeInTheDocument();
  });

  it("marks an absent denominator explicitly", () => {
    render(<Figure source="data/showcase/blowout_dynamics.json" asOf="2026-07-25"><div>Chart</div></Figure>);
    expect(screen.getByText("n not published")).toBeInTheDocument();
  });
});
