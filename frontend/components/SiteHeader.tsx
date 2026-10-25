"use client";

import { useEffect, useState } from "react";
import { get } from "@/lib/api";
import { date } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Health } from "@/lib/types";

function useNow(): Date | null {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    const tick = () => setNow(new Date());
    const first = window.setTimeout(tick, 0);
    const id = window.setInterval(tick, 1000);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(id);
    };
  }, []);
  return now;
}

/** Live clock showing the viewer's real local date and time (rendered after mount). */
export function Clock() {
  const now = useNow();
  if (!now) return <div className="h-[34px]" aria-hidden="true" />;
  const tz = new Intl.DateTimeFormat("en-GB", { timeZoneName: "short" })
    .formatToParts(now)
    .find((p) => p.type === "timeZoneName")?.value;
  return (
    <div className="text-right" data-testid="clock">
      <div className="num text-[13px] font-medium leading-tight">
        {now.toLocaleTimeString("en-GB", { hour12: false })} <span className="text-ink-60">{tz}</span>
      </div>
      <div className="kicker !tracking-[0.08em] sm:hidden">
        {now.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
      </div>
      <div className="kicker hidden !tracking-[0.08em] sm:block">
        {now.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
      </div>
    </div>
  );
}

export default function SiteHeader() {
  const health = useApi<Health>("health", (s) => get<Health>("/health", undefined, s));
  return (
    <div className="mx-auto flex min-h-[64px] max-w-[1280px] items-center gap-4 flex-wrap pl-16 pr-16 pt-3 sm:min-h-[76px] sm:flex-nowrap sm:pl-20 sm:pr-[11.5rem]">
      <div className="min-w-0">
        <span className="serif text-[22px] font-semibold leading-none tracking-[-0.01em]">VebStock</span>
        <span className="kicker ml-4 hidden lg:inline">The right stock. The right place. The right time.</span>
        {health.data?.as_of ? (
          <div className="kicker mt-1 hidden sm:block !text-ink">Simulated data snapshot: {date(health.data.as_of)}</div>
        ) : null}
      </div>
      <div className="ml-auto shrink-0">
        <Clock />
      </div>
      {health.data?.as_of ? (
        <div className="kicker basis-full !text-ink sm:hidden">Simulated data snapshot: {date(health.data.as_of)}</div>
      ) : null}
    </div>
  );
}
