export default function Loading() {
  return <section className="container-page py-12" role="status" aria-live="polite" aria-busy="true">
    <p className="text-sm text-muted">正在加载赛事与来源信息…</p>
    <div className="mt-6 grid gap-4 md:grid-cols-3" aria-hidden="true">
      {[0, 1, 2].map((item) => <div key={item} className="h-48 animate-pulse rounded-lg bg-slate-100 motion-reduce:animate-none" />)}
    </div>
  </section>;
}
