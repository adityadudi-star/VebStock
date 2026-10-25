"use client";

import { VIEWS } from "@/lib/nav";
import { PhotoBanner } from "./Photo";

export default function PageHeader({
  href,
  title,
  lede,
  kicker,
  children,
}: {
  href: string;
  title?: string;
  kicker?: string;
  lede?: string;
  children?: React.ReactNode;
}) {
  const v = VIEWS.find((x) => x.href === href);
  return (
    <>
      <header className="mb-6 border-b border-ink pb-5">
        <div className="kicker">{kicker ?? `View ${v?.n} of ${VIEWS.length}`}</div>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-4">
          <h1 className="serif text-[38px] font-medium leading-[1.05] tracking-[-0.02em] sm:text-[48px]">{title ?? v?.title}</h1>
          {children ? <div className="flex flex-wrap items-center gap-2">{children}</div> : null}
        </div>
        {lede ? <p className="mt-3 max-w-[70ch] text-[15px] leading-relaxed">{lede}</p> : null}
      </header>
      <PhotoBanner href={href} />
    </>
  );
}
