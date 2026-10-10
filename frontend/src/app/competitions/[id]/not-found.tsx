import Link from "next/link";

export default function NotFound() {
  return <section className="container-page py-16 text-center">
    <h1 className="text-2xl font-semibold text-ink">未找到这项赛事或届次</h1>
    <p className="mt-3 text-sm text-muted">链接可能已变更，也可以提交尚未收录的信息。</p>
    <div className="mt-6 flex flex-wrap justify-center gap-3">
      <Link href="/competitions" className="button-primary">浏览竞赛</Link>
      <Link href="/contribute" className="button-secondary">补充信息</Link>
    </div>
  </section>;
}
