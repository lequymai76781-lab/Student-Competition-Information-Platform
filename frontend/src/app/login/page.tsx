"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { LogIn } from "lucide-react";
import { login } from "@/lib/v09-api";
import { safeReturnPath } from "@/lib/safe-return-path";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError("");
    try {
      const session = await login(email, password);
      const next = new URLSearchParams(window.location.search).get("next");
      router.push(safeReturnPath(next, window.location.origin)
        ?? (session.onboarding_complete ? "/my-competitions" : "/onboarding"));
    } catch (exc) {
      setError(exc instanceof Error ? "邮箱或密码错误" : "登录失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader eyebrow="V0.9" title="登录" description="登录后启用我的学校、我的截止时间、收藏与我的竞赛。" icon={LogIn} />
      <section className="container-page flex justify-center py-8">
        <div className="w-full max-w-md panel p-6">
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-ink">邮箱</span>
            <input className="field" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" />
          </label>
          <label className="mt-4 block">
            <span className="mb-1.5 block text-sm font-medium text-ink">密码</span>
            <input className="field" type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="至少6位" />
          </label>
          {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
          <button type="button" disabled={busy || !email || !password} onClick={submit} className="button-primary mt-6 w-full">
            {busy ? "登录中…" : "登录"}
          </button>
          <p className="mt-4 text-center text-sm text-muted">
            还没有账号？<Link href="/register" className="font-medium text-accent hover:underline">注册</Link>
          </p>
        </div>
      </section>
    </>
  );
}
