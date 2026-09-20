import { SearchX } from "lucide-react";

export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="panel flex flex-col items-center justify-center p-10 text-center">
      <SearchX aria-hidden className="h-10 w-10 text-muted" />
      <h2 className="mt-4 text-lg font-semibold text-ink">{title}</h2>
      <p className="mt-2 max-w-xl text-sm leading-6 text-muted">{description}</p>
    </div>
  );
}
