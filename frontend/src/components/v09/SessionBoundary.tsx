"use client";

import { Fragment, type ReactNode } from "react";
import { useSessionToken } from "@/lib/use-session";

// A different identity gets a new component tree, including drafts, rows and
// in-flight state. Late completions can only update the discarded tree.
export function SessionBoundary({ children }: { children: ReactNode }) {
  const token = useSessionToken();
  return <Fragment key={token ?? "guest"}>{children}</Fragment>;
}
