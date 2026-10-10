"use client";

import { useSyncExternalStore } from "react";

function subscribe(listener: () => void) {
  window.addEventListener("storage", listener);
  window.addEventListener("v09-session-change", listener);
  window.addEventListener("popstate", listener);
  return () => {
    window.removeEventListener("storage", listener);
    window.removeEventListener("v09-session-change", listener);
    window.removeEventListener("popstate", listener);
  };
}

export function useSessionToken() {
  return useSyncExternalStore(subscribe, () => window.localStorage.getItem("v09_token"), () => null);
}

export function useReturnPath() {
  return useSyncExternalStore(subscribe, () => window.location.pathname + window.location.search, () => "/contribute");
}
