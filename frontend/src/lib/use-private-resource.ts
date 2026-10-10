"use client";

import { useCallback, useEffect, useState } from "react";
import { useSessionToken } from "@/lib/use-session";

export function usePrivateResource<T>(key: string, load: () => Promise<T>) {
  const token = useSessionToken();
  const [revision, setRevision] = useState(0);
  const owner = JSON.stringify([token, key, revision]);
  const [snapshot, setSnapshot] = useState<{ owner: string; data: T | null; error: string } | null>(null);
  useEffect(() => {
    if (!token) return;
    let active = true;
    load().then((data) => {
      if (active) setSnapshot({ owner, data, error: "" });
    }).catch((error: unknown) => {
      if (active) setSnapshot({ owner, data: null, error: error instanceof Error ? error.message : "加载失败，请重试。" });
    });
    return () => { active = false; };
  }, [token, owner, load]);
  const reload = useCallback(() => setRevision((value) => value + 1), []);
  const current = snapshot?.owner === owner ? snapshot : null;
  return { data: current?.data ?? null, error: current?.error ?? "", ready: Boolean(current), reload };
}
