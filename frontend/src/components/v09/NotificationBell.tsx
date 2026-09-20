"use client";

import Link from "next/link";
import { Bell } from "lucide-react";
import { useEffect, useState } from "react";

import { unreadNotifications } from "@/lib/v09-api";

export function NotificationBell() {
  const [count, setCount] = useState(0);
  const [token, setTokenState] = useState(false);

  useEffect(() => {
    if (!window.localStorage.getItem("v09_token")) return;
    setTokenState(true);
    const refresh = () =>
      unreadNotifications()
        .then((data) => setCount(data.unread))
        .catch(() => undefined);
    refresh();
    const timer = window.setInterval(refresh, 60_000);
    return () => window.clearInterval(timer);
  }, []);

  if (!token) return null;
  return (
    <Link
      href="/notifications"
      aria-label="通知"
      className="relative flex h-10 w-10 items-center justify-center rounded-md border border-line bg-white text-muted transition duration-200 hover:border-accent hover:text-accent"
    >
      <Bell aria-hidden className="h-4 w-4" />
      {count > 0 ? (
        <span className="absolute right-0.5 top-0.5 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-red-500 px-0.5 text-[10px] font-semibold leading-none text-white">
          {count > 99 ? "99+" : count}
        </span>
      ) : null}
    </Link>
  );
}
