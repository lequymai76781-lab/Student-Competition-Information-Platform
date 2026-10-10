"use client";

import { SessionBoundary } from "@/components/v09/SessionBoundary";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { PageHeader } from "@/components/PageHeader";
import { ProfileForm } from "@/components/v09/ProfileForm";
import { Settings } from "lucide-react";
import { me, type V09Profile } from "@/lib/v09-api";

export default function ProfileSettingsPage() {
  return <SessionBoundary><ProfileSettingsPageSession /></SessionBoundary>;
}

function ProfileSettingsPageSession() {
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
      .then((session) => { if (active) setInitial(session.user); })
      .catch(() => { if (active) router.replace("/login"); })
      .finally(() => { if (active) setReady(true); });
    return () => { active = false; };
  }, [router]);

  return (
    <>
      <PageHeader eyebrow="Settings" title="个人资料" description="修改学校、学院、专业、年级与兴趣方向后，个性化结果会实时重新计算。" icon={Settings} />
      <section className="container-page py-8">
        {ready ? (
          <ProfileForm initial={initial} title="编辑资料" submitLabel="保存修改" redirectTo="/my-competitions" />
        ) : (
          <p className="text-center text-sm text-muted">加载中…</p>
        )}
      </section>
    </>
  );
}
