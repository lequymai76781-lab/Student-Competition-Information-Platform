import { Search } from "lucide-react";

export function HomeSearch() {
  return (
    <form action="/competitions" className="mt-8 max-w-3xl">
      <label className="sr-only" htmlFor="home-search">
        搜索竞赛、专业、学校或主办方
      </label>
      <div className="group flex min-h-14 items-center gap-3 rounded-xl border border-line bg-white px-3 shadow-soft transition duration-200 focus-within:border-accent focus-within:ring-4 focus-within:ring-blue-50">
        <Search aria-hidden className="h-5 w-5 shrink-0 text-quiet transition group-focus-within:text-accent" />
        <input
          id="home-search"
          name="keyword"
          className="h-12 min-w-0 flex-1 bg-transparent text-base text-ink outline-none placeholder:text-quiet"
          placeholder="搜索蓝桥杯、数学建模、计算机设计大赛……"
        />
        <button className="button-primary hidden sm:inline-flex" type="submit">
          搜索
        </button>
      </div>
    </form>
  );
}

