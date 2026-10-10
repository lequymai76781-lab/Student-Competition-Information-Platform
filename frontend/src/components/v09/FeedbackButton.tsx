"use client";

import { MessageSquarePlus, X } from "lucide-react";
import { useState } from "react";

import { submitFeedback } from "@/lib/v09-api";
import { SessionBoundary } from "@/components/v09/SessionBoundary";

const categories = ["数据错误", "找不到比赛", "学校信息错误", "Deadline问题", "使用困难", "功能建议", "页面问题", "其他"];

export function FeedbackButton() {
  return <SessionBoundary><FeedbackButtonSession /></SessionBoundary>;
}

function FeedbackButtonSession() {
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState("功能建议");
  const [content, setContent] = useState("");
  const [sent, setSent] = useState(false);

  async function send() {
    if (!content.trim()) return;
    await submitFeedback({ category, content: content.trim(), url: window.location.href });
    setSent(true);
  }

  return (
    <>
      {open ? (
        <div className="fixed bottom-4 right-4 z-50 w-80 rounded-lg border border-line bg-white p-4 shadow-lift">
          <div className="flex items-center justify-between">
            <p className="font-semibold text-ink">反馈问题</p>
            <button type="button" aria-label="关闭" onClick={() => setOpen(false)}>
              <X aria-hidden className="h-4 w-4 text-muted" />
            </button>
          </div>
          {sent ? (
            <p className="mt-3 text-sm text-emerald-700">已收到，感谢反馈！</p>
          ) : (
            <div className="mt-3 grid gap-3">
              <select value={category} onChange={(event) => setCategory(event.target.value)} className="field">
                {categories.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
              <textarea
                value={content}
                onChange={(event) => setContent(event.target.value)}
                rows={4}
                placeholder="描述你遇到的问题或建议…"
                className="field min-h-24 py-2"
              />
              <button type="button" disabled={!content.trim()} onClick={send} className="button-primary">
                提交
              </button>
            </div>
          )}
        </div>
      ) : null}
      <button
        type="button"
        onClick={() => {
          setOpen((value) => !value);
          setSent(false);
        }}
        className="fixed bottom-4 right-4 z-40 flex h-11 items-center gap-2 rounded-md bg-ink px-3 text-sm font-medium text-white shadow-soft"
      >
        <MessageSquarePlus aria-hidden className="h-4 w-4" />
        反馈问题
      </button>
    </>
  );
}
