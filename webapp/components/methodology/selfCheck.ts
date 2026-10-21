// selfCheck.ts -- the ONE sentence for check_all.py's report (loaded by
// components/desk/deskExtras.server loadChecks), shared by the home page and
// /methodology/ so the two can never print different counts.
import type { Checks } from "@/components/desk/deskExtras.server";

export function selfCheckSentence(c: Checks): string {
  return `${c.pass} of ${c.total} pass, ${c.noCheck} have no self-check, ${c.other} FAIL/other`;
}
