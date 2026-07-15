/**
 * live/ -- shared LiveBadge + UpdatedAge primitives.
 *
 * Public API surface:
 *   LiveBadge    -- full badge rendering the useLiveData contract
 *   UpdatedAge   -- stand-alone "updated Xs ago" span
 *   humanizeAge  -- pure utility: seconds -> "Xs ago" / "Xm ago" / "Xh ago"
 *   SideProb     -- winner-clarity primitive (leading side green, trailing red)
 *   LiveBadgeProps, UpdatedAgeProps -- TypeScript prop interfaces
 */

export { LiveBadge } from "./LiveBadge";
export type { LiveBadgeProps } from "./LiveBadge";

export { UpdatedAge, humanizeAge } from "./UpdatedAge";
export type { UpdatedAgeProps } from "./UpdatedAge";

export { SideProb } from "./SideProb";
export type { SideProbSide } from "./SideProb";
