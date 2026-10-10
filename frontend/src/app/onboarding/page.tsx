"use client";

import { SessionBoundary } from "@/components/v09/SessionBoundary";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { PageHeader } from "@/components/PageHeader";
import { ProfileForm } from "@/components/v09/ProfileForm";
import { Radar } from "lucide-react";
import { me, type V09Profile } from "@/lib/v09-api";

export default function OnboardingPage() {
  return <SessionBoundary><OnboardingPageSession /></SessionBoundary>;
}

function OnboardingPageSession() {
  const router = useRouter();
  const [initial, setInitial] = useState<V09Profile | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const token = window.localStorage.getItem("v09_token");
    if (!token) {
      router.replace("/login");
      return;
    }
    let active = true;
    me()
      .then((session) => {
        if (!active) return;
        if (session.onboarding_complete) {
          router.replace("/my-competitions");
          return;
        }
        setInitial(session.user);
      })
      .catch(() => { if (active) router.replace("/login"); })
      .finally(() => { if (active) setReady(true); });
    return () => { active = false; };
  }, [router]);

  return (
    <>
      <PageHeader
        eyebrow="Onboarding"
        title="设置你的竞赛画像"
        description="5步完成：学校 → 学院 → 专业 → 年级 → 感兴趣方向。技能等偏好可稍后补充。"
        icon={Radar}
      />
      <section className="container-page py-8">
        {ready ? <ProfileForm initial={initial} /> : <p className="text-center text-sm text-muted">加载中…</p>}
      </section>
    </>
  );
}
