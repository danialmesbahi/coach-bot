import type { ReactNode } from "react";

/** Re-mounted on every page change: a short fade gives in-app transitions instead of a hard swap. */
export default function Template({ children }: { children: ReactNode }) {
  return <div className="page-enter">{children}</div>;
}
