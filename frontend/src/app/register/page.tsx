"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { UserPlus } from "lucide-react";
import { register } from "@/lib/v09-api";

export default function RegisterPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError("");
    try {
      await register({ username, email, password, invite_code: inviteCode.trim() || undefined });
      router.push("/onboarding");
    } catch (exc) {
      setError(exc instanceof Error ? "注册失败，可能邮箱已存在" : "注册失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader eyebrow="V0.9" title="注册" description="创建账号并完成约1分钟的竞赛画像设置。" icon={UserPlus} />
      <section className="container-page flex justify-center py-8">
        <div className="w-full max-w-md panel p-6">
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-ink">昵称</span>
            <input className="field" value={username} onChange={(event) => setUsername(event.target.value)} />
          </label>
          <label className="mt-4 block">
            <span className="mb-1.5 block text-sm font-medium text-ink">邮箱</span>
            <input className="field" value={email} onChange={(event) => setEmail(event.target.value)} />
          </label>
          <label className="mt-4 block">
            <span className="mb-1.5 block text-sm font-medium text-ink">密码</span>
            <input className="field" type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
          </label>
          <label className="mt-4 block">
            <span className="mb-1.5 block text-sm font-medium text-ink">邀请码（Beta阶段填写）</span>
            <input className="field" value={inviteCode} onChange={(event) => setInviteCode(event.target.value)} placeholder="如有邀请码请填写" />
          </label>
          {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
          <button type="button" disabled={busy || !email || !password || !username} onClick={submit} className="button-primary mt-6 w-full">
            {busy ? "注册中…" : "注册并设置画像"}
          </button>
          <p className="mt-4 text-center text-sm text-muted">
            已有账号？<Link href="/login" className="font-medium text-accent hover:underline">登录</Link>
          </p>
          <div className="mt-5 rounded-md border border-line bg-paper p-3 text-xs leading-5 text-muted">
            平台赛事与校内信息来自公开来源整理，报名与截止时间请以赛事官方及所在学校最新通知为准；
            你提交的学校/专业信息仅用于个性化赛事筛选。
          </div>
        </div>
      </section>
    </>
  );
}
