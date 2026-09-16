import { snapshot } from "./labHelpers";
import { buildCountContext, type CountContextData } from "./countContext";

/** Reads the committed count-leverage JSON at build time; the browser never fetches it. */
export function loadCountContext(): CountContextData {
  return buildCountContext(snapshot<unknown>("mlb_count_leverage"));
}
