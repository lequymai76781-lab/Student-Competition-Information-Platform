"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { BellRing } from "lucide-react";
import { formatDate } from "@/lib/format";
import { markNotificationRead, notifications, type V09Notification } from "@/lib/v09-api";

const filters = [
  { key: "", label: "全部" },
  { key: "deadline", label: "截止提醒" },
  { key: "updates", label: "赛事更新" },
  { key: "school", label: "学校通知" },
];

export default function NotificationsPage() {
  const router = useRouter();
  const [filter, setFilter] = useState("");
  const [items, setItems] = useState<V09Notification[]>([]);
  const [unread, setUnread] = useState(0);
  const [loaded, setLoaded] = useState(false);

  function load() {
    notifications(filter || undefined)
      .then((data) => {
        setItems(data.items);
        setUnread(data.unread);
      })
      .catch(() => setItems([]))
      .finally(() => setLoaded(true));
  }

  useEffect(() => {
    const token = window.localStorage.getItem("v09_token");
    if (!token) {
      router.replace("/login");
      return;
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  async function open(item: V09Notification) {
    if (!item.is_read) {
      await markNotificationRead(item.id);
    }
    if (item.competition_id) {
      router.push(`/competitions/${item.competition_id}`);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Notifications"
        title="通知中心"
        description={unread > 0 ? `你有 ${unread} 条未读通知` : "暂无未读通知"}
        icon={BellRing}
      />
      <section className="container-page py-8">
        <div className="mb-5 flex flex-wrap gap-2">
          {filters.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setFilter(item.key)}
              className={
                filter === item.key
                  ? "button-primary min-h-9 px-3 text-sm"
                  : "button-secondary min-h-9 px-3 text-sm"
              }
            >
              {item.label}
            </button>
          ))}
        </div>
        {loaded && items.length === 0 ? (
          <div className="panel-soft p-6 text-sm text-muted">暂无通知。收藏或标记“准备参加”赛事后，我们会在这里提醒你。</div>
        ) : null}
        <div className="grid gap-3">
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => open(item)}
              className={`panel w-full p-4 text-left transition hover:border-accent ${item.is_read ? "" : "border-blue-200 bg-blue-50/40"}`}
            >
              <div className="flex items-center justify-between gap-3">
                <p className="font-semibold text-ink">{item.title}</p>
                <span className="shrink-0 text-xs text-muted">{item.created_at ? formatDate(item.created_at) : ""}</span>
              </div>
              {item.content ? <p className="mt-1 text-sm leading-6 text-muted">{item.content}</p> : null}
              {!item.is_read ? <span className="mt-2 inline-block h-2 w-2 rounded-full bg-accent" /> : null}
            </button>
          ))}
        </div>
        <p className="mt-6 text-center text-xs text-muted">
          去 <Link href="/my-competitions" className="text-accent hover:underline">我的竞赛</Link> 管理关注与状态
        </p>
      </section>
    </>
  );
}
