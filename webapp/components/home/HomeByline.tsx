// HomeByline -- author line with contact, one click from the first screen (P2.1 / brief 4).
import { CONTACT_EMAIL, GITHUB, PORTFOLIO } from "@/components/shell/nav";

export function HomeByline() {
  return (
    <p className="m-0 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground" data-testid="byline">
      <span>Built by Neel Shah</span>
      <a href={`mailto:${CONTACT_EMAIL}`} className="hover:text-foreground">{CONTACT_EMAIL}</a>
      <a href={GITHUB} className="hover:text-foreground">GitHub</a>
      <a href={PORTFOLIO} className="hover:text-foreground">Portfolio</a>
      <span className="basis-full">
        Education: three years of data-science coursework at the University of Iowa. Built by one person
        directing Claude and Codex agents; every number links to its receipt.
      </span>
    </p>
  );
}
