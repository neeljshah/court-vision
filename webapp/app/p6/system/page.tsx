import { redirect } from "next/navigation";

// Legacy route. The canonical, richer System view (health + self-improve +
// gate ledger + backlog + parity + CLV-over-time) now lives at /system.
// Redirect so there is exactly ONE System surface (no duplicate page).
export default function LegacyP6SystemRedirect() {
  redirect("/system");
}
