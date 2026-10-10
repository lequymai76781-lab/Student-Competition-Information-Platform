"use client";

import Link from "next/link";

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <section className="container-page flex flex-col items-center py-20 text-center">
      <p className="label">Something went wrong</p>
      <h1 className="mt-2 text-2xl font-semibold text-ink">页面暂时无法加载</h1>
      <p className="mt-3 max-w-md text-sm leading-6 text-muted">
        服务暂时不可用或网络异常。你可以重试，或返回赛事列表继续浏览。
      </p>
      <div className="mt-6 flex flex-wrap justify-center gap-3">
        <button type="button" className="button-primary" onClick={() => reset()}>
          重试
        </button>
        <Link href="/competitions" className="button-secondary">
          返回赛事列表
        </Link>
        <Link href="/" className="button-secondary">
          返回首页
        </Link>
      </div>
    </section>
  );
}
