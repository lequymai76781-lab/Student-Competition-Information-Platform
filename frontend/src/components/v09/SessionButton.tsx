"use client";

import Link from "next/link";
import { useSessionToken } from "@/lib/use-session";

import { setToken } from "@/lib/v09-api";

export function SessionButton() {
  const token = useSessionToken();
  if (!token) {
    return (
      <Link href="/login" className="button-secondary hidden sm:inline-flex">
        登录 / 注册
      </Link>
    );
  }
  return (
    <span className="flex items-center gap-2">
      <Link href="/my-competitions" className="button-primary hidden sm:inline-flex">
        我的竞赛
      </Link>
      <button
        type="button"
        className="inline-flex text-sm text-muted transition hover:text-ink"
        onClick={() => {
          setToken(null);
        }}
      >
        退出
      </button>
    </span>
  );
}
