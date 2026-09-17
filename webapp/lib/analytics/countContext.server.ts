import { snapshot } from "./labHelpers";
import { buildCountContext, type CountContextData } from "./countContext";
import { buildExactCountContext, type ExactCountData } from "./exactCountContext";

/** Reads the committed count-leverage JSON at build time; the browser never fetches it. */
export function loadCountContext(): CountContextData {
  return buildCountContext(snapshot<unknown>("mlb_count_leverage"));
}

/** Reads exact-count rows without substituting the broader class denominators. */
export function loadExactCountContext(): ExactCountData {
  return buildExactCountContext(snapshot<unknown>("mlb_count_leverage"));
}
