"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { setToken } from "@/lib/v09-api";

export function SessionButton() {
  const [token, setTokenState] = useState<string | null>(null);
  useEffect(() => {
    setTokenState(window.localStorage.getItem("v09_token"));
  }, []);
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
        className="hidden text-sm text-muted transition hover:text-ink sm:inline-flex"
        onClick={() => {
          setToken(null);
          setTokenState(null);
        }}
      >
        退出
      </button>
    </span>
  );
}
