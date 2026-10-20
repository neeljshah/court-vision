import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { GLOSSARY, GLOSSARY_IDS } from "./glossary";
import { Term } from "./Term";

describe("Term", () => {
  it.each(GLOSSARY_IDS)("describes %s with its verbatim glossary text", (id) => {
    render(<Term id={id} />);
    const trigger = screen.getByRole("button", { name: GLOSSARY[id].term });
    const tip = screen.getByRole("tooltip");
    expect(trigger).toHaveAttribute("aria-describedby", tip.id);
    expect(tip).toHaveTextContent(`${GLOSSARY[id].term} ${GLOSSARY[id].text}`);
    expect(trigger.getAttribute("title")).toBe(`${GLOSSARY[id].term}: ${GLOSSARY[id].text}`);
    trigger.focus();
    expect(trigger).toHaveFocus();
  });

  it("keeps the author's wording as the visible trigger", () => {
    render(<p>scored by <Term id="brier">Brier</Term> against the <Term id="devigged-close">devigged close</Term></p>);
    expect(screen.getByRole("button", { name: "Brier" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "devigged close" })).toBeInTheDocument();
    expect(screen.getAllByRole("tooltip")).toHaveLength(2);
  });
});
