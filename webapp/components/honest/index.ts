// components/honest -- public barrel export.
//
// Import from here so consumers don't need to know internal file names:
//   import { PanelErrorBoundary } from "@/components/honest";
//   import { Unavailable, HonestState } from "@/components/honest";

export { PanelErrorBoundary, withPanelErrorBoundary } from "./PanelErrorBoundary";
export type { PanelErrorBoundaryProps } from "./PanelErrorBoundary";

export {
  Unavailable,
  Empty,
  Stale,
  Degraded,
  HonestState,
} from "./HonestState";

export { DataSurface } from "./DataSurface";
export type { DataSurfaceProps } from "./DataSurface";

export { RouteError } from "./RouteError";
export { RouteLoading } from "./RouteLoading";
