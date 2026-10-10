"use client";

import { GraduationCap, Menu, Search, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { SessionButton } from "@/components/v09/SessionButton";
import { NotificationBell } from "@/components/v09/NotificationBell";
import { FeedbackButton } from "@/components/v09/FeedbackButton";

const navItems = [
  { href: "/", label: "首页" },
  { href: "/competitions", label: "发现竞赛" },
  { href: "/calendar", label: "竞赛日历" },
  { href: "/universities", label: "高校政策库" },
  { href: "/data", label: "数据工程" },
  { href: "/my-competitions", label: "我的竞赛" },
  { href: "/contribute", label: "补充信息" }
];

export function AppShell({ children }: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="min-h-screen bg-white">
      <header className="sticky top-0 z-40 border-b border-line bg-white">
        <div className="container-page flex h-16 items-center justify-between gap-4">
          <Link href="/" className="flex min-w-0 items-center gap-2 font-semibold text-ink transition duration-200 hover:text-accent">
            <span className="flex h-9 w-9 items-center justify-center rounded-md bg-ink text-white shadow-sm">
              <GraduationCap aria-hidden className="h-5 w-5" />
            </span>
            <span className="hidden truncate sm:block">竞赛决策与情报平台</span>
          </Link>
          <nav className="hidden items-center gap-1 lg:flex" aria-label="主导航">
            {navItems.map((item) => (
              <Link key={item.href} href={item.href} className={navLinkClass(pathname, item.href)}>
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <NotificationBell />
            <Link href="/competitions" className="hidden h-10 w-10 items-center justify-center rounded-md border border-line bg-white text-muted transition duration-200 hover:border-accent hover:text-accent focus-ring md:inline-flex" aria-label="搜索竞赛">
              <Search aria-hidden className="h-4 w-4" />
            </Link>
            <SessionButton />
            <button
              type="button"
              className="flex h-11 w-11 items-center justify-center rounded-md border border-line bg-white text-ink transition duration-200 hover:border-accent hover:text-accent focus-ring lg:hidden"
              aria-expanded={mobileOpen}
              aria-label={mobileOpen ? "关闭导航" : "打开导航"}
              onClick={() => setMobileOpen((open) => !open)}
            >
              {mobileOpen ? <X aria-hidden className="h-5 w-5" /> : <Menu aria-hidden className="h-5 w-5" />}
            </button>
          </div>
        </div>
        {mobileOpen ? (
          <nav className="container-page grid gap-1 border-t border-line py-3 lg:hidden" aria-label="移动端导航">
            {navItems.map((item) => (
              <Link key={item.href} href={item.href} className={mobileNavLinkClass(pathname, item.href)} onClick={() => setMobileOpen(false)}>
                {item.label}
              </Link>
            ))}
            <div className="mt-2">
              <SessionButton />
            </div>
          </nav>
        ) : null}
      </header>
      <main>{children}</main>
      <footer className="border-t border-line bg-paper">
        <div className="container-page flex flex-wrap items-center justify-between gap-3 py-6 text-sm text-muted">
          <p>学校、专业或赛事尚未收录？发现通知或信息有误？</p>
          <Link href="/contribute" className="font-semibold text-accent hover:underline">提交补充与查看进度 →</Link>
        </div>
      </footer>
      <FeedbackButton />
    </div>
  );
}

function isActive(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

function navLinkClass(pathname: string, href: string): string {
  const active = isActive(pathname, href);
  return [
    "relative rounded-md px-3 py-2 text-sm font-medium transition duration-200",
    active ? "bg-paper text-ink after:absolute after:inset-x-3 after:-bottom-[13px] after:h-0.5 after:rounded-full after:bg-accent" : "text-muted hover:bg-paper hover:text-ink"
  ].join(" ");
}

function mobileNavLinkClass(pathname: string, href: string): string {
  const active = isActive(pathname, href);
  return [
    "min-h-11 rounded-md px-3 py-2.5 text-sm font-medium transition duration-200",
    active ? "bg-blue-50 text-accent" : "text-muted hover:bg-paper hover:text-ink"
  ].join(" ");
}
