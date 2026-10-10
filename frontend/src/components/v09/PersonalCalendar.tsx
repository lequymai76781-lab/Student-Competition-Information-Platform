"use client";

import { SessionBoundary } from "@/components/v09/SessionBoundary";

import Link from "next/link";
import { useEffect, useState } from "react";

import { myCalendarEvents } from "@/lib/v09-api";
import { formatDate } from "@/lib/format";

export function PersonalCalendar() {
  return <SessionBoundary><PersonalCalendarSession /></SessionBoundary>;
}

function PersonalCalendarSession() {
  const [events, setEvents] = useState<{ competition_id: number; name: string; deadline: string; deadline_label: string }[] | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const token = window.localStorage.getItem("v09_token");
    if (!token) return;
    myCalendarEvents()
      .then(setEvents)
      .catch(() => setEvents([]));
  }, []);

  if (events === null) return null;
  return (
    <div className="panel-soft p-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-ink">我的赛事截止（个性化有效截止）</p>
        <button type="button" className="button-secondary min-h-8 px-3 text-xs" onClick={() => setOpen((value) => !value)}>
          {open ? "收起" : `查看 ${events.length} 个`}
        </button>
      </div>
      {open ? (
        <div className="mt-3 divide-y divide-line">
          {events.slice(0, 30).map((event) => (
            <Link key={event.competition_id} href={`/competitions/${event.competition_id}`} className="flex items-center justify-between gap-3 py-2 text-sm hover:text-accent">
              <span className="font-medium text-ink">{event.name}</span>
              <span className="shrink-0 text-muted">
                {formatDate(event.deadline)} · {event.deadline_label}
              </span>
            </Link>
          ))}
        </div>
      ) : null}
    </div>
  );
}
