import type { LucideIcon } from "lucide-react";

type PageHeaderProps = {
  eyebrow?: string;
  title: string;
  description?: string;
  icon?: LucideIcon;
  action?: React.ReactNode;
};

export function PageHeader({ eyebrow, title, description, icon: Icon, action }: PageHeaderProps) {
  return (
    <section className="border-b border-line bg-white">
      <div className="container-page py-8">
        <div className="flex min-w-0 flex-col gap-5 md:flex-row md:items-end md:justify-between">
          <div className="min-w-0 max-w-3xl">
            {eyebrow ? <p className="label mb-2">{eyebrow}</p> : null}
            <div className="flex min-w-0 items-start gap-3 sm:items-center">
              {Icon ? (
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-blue-50 text-accent">
                  <Icon aria-hidden className="h-5 w-5" />
                </span>
              ) : null}
              <h1 className="min-w-0 break-words text-2xl font-semibold leading-tight text-ink sm:text-3xl md:text-4xl">{title}</h1>
            </div>
            {description ? <p className="mt-3 break-words text-base leading-7 text-muted">{description}</p> : null}
          </div>
          {action ? <div className="flex shrink-0 items-center gap-2 self-start md:self-auto">{action}</div> : null}
        </div>
      </div>
    </section>
  );
}
