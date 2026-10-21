import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import AboutPage from "./page";
import { COMMIT_COUNTS, COMMIT_COUNT_COMMANDS, COMMIT_COUNT_RECEIPT, COMMIT_HISTORY_URL, agentShare } from "./commitCounts";

describe("About page", () => {
  it("has contact, methods and the what-this-is-not block", () => {
    render(<AboutPage />);
    expect(screen.getByRole("link", { name: "neeljshah22@gmail.com" })).toHaveAttribute("href", "mailto:neeljshah22@gmail.com");
    expect(screen.getByRole("heading", { name: "What this is not" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "How it works" })).toHaveAttribute("href", expect.stringMatching(/^\/how-it-works\/?$/));
    expect(screen.getByRole("link", { name: "Glossary" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "retraction record" })).toHaveAttribute("href", expect.stringMatching(/^\/evidence\/retractions\/?$/));
  });

  it("leads with the headline finding, with the reference and scoring rule as glossary terms", () => {
    const { container } = render(<AboutPage />);
    const lede = container.querySelector("header p")!;
    expect(lede.textContent).toMatch(/does not\s+price games better than the market/);
    expect(lede.textContent).toMatch(/on MLB moneyline and soccer\s+over\/under 2\.5; on NBA moneyline the interval includes zero, so we cannot tell/);
    expect(screen.getByRole("button", { name: "devigged closing price" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Brier score" })).toBeTruthy();
    expect(container.textContent).not.toMatch(/within noise/i);
  });

  it("uses no banned or degree wording", () => {
    const { container } = render(<AboutPage />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\b(edge|roi|profit|beats?|money)\b/i);
    expect(text).not.toMatch(/degree|ph\.?d|graduat|bachelor|master'?s/i);
  });

  it("counts the agent co-author share from git, with its method and date, and never the quoted figures", () => {
    const { container } = render(<AboutPage />);
    // The counts are integers, the share is computed from them, and the date is an ISO day.
    expect(COMMIT_COUNTS.asOf).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(Number.isInteger(COMMIT_COUNTS.total) && COMMIT_COUNTS.total > 0).toBe(true);
    expect(Number.isInteger(COMMIT_COUNTS.agentCoAuthored) && COMMIT_COUNTS.agentCoAuthored <= COMMIT_COUNTS.total).toBe(true);
    expect(agentShare({ total: 6556, agentCoAuthored: 1620 })).toBe("24.7%");
    const how = container.querySelector("#how")!.closest("section")!;
    const text = how.textContent ?? "";
    const total = COMMIT_COUNTS.total.toLocaleString("en-US");
    const agent = COMMIT_COUNTS.agentCoAuthored.toLocaleString("en-US");
    expect(text).toMatch(new RegExp(`Counted from git log at commit ${COMMIT_COUNTS.sha} on ${COMMIT_COUNTS.asOf},\\s+${agent} of the ${total} commits\\s+on the public master branch \\(${agentShare().replace(".", "\\.")}\\) carry a Co-Authored-By trailer\\s+naming Claude or Codex`));
    expect(text).toMatch(/true agent share is higher/);
    expect(text).not.toMatch(/24\.8%|6,515|As measured on/);
    // The receipt: the chip names the commands and links the counted history; the command is printed.
    const chip = screen.getByRole("link", { name: `Receipt: git log (public master), as of ${COMMIT_COUNTS.asOf}, descriptive_only` });
    expect(chip).toHaveAttribute("href", COMMIT_HISTORY_URL);
    expect(COMMIT_HISTORY_URL).toBe("https://github.com/neeljshah/court-vision/commits/4f033b5a5");
    expect(chip.getAttribute("title")).toContain(COMMIT_COUNT_COMMANDS.total);
    expect(chip.getAttribute("title")).toContain(COMMIT_COUNT_COMMANDS.agentCoAuthored);
    expect(screen.getByTestId("commit-count-command").textContent).toBe(COMMIT_COUNT_RECEIPT);
    expect(COMMIT_COUNT_COMMANDS.total).toBe("git rev-list --count 4f033b5a5");
    expect(COMMIT_COUNT_COMMANDS.agentCoAuthored).toBe("git log 4f033b5a5 -i --grep='^Co-Authored-By:.*\\(Claude\\|Codex\\)' --format=%H | wc -l");
  });
  it("adds the owner-decision example, what is next, the why line and the roles line", () => {
    const { container } = render(<AboutPage />);
    const text = (container.textContent ?? "").replace(/\s+/g, " ");
    expect(text).toContain("the former headline return figure was withdrawn once its grader was found never to read the model.");
    expect(screen.getByRole("heading", { name: "What is next" })).toBeTruthy();
    expect(text).toContain("The forward paper series keeps running until each cell reaches its 30-game floor; the NBA fitted arms need a new dated seal. Computer-vision tracking stays paused.");
    expect(screen.getByTestId("about-why").textContent).toBe("The aim is a forecaster whose every number someone else can check against the market.");
    const open = screen.getByTestId("open-to");
    expect(open.textContent!.trim()).toBe("Open to data-science / forecasting, quant-research, ML-engineering and analytics-engineering roles.");
    expect(open.nextElementSibling!.textContent).toMatch(/^\s*Built by Neel Shah, who has three years of data-science coursework/);
  });
});
