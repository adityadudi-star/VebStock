"use client";

import { configError } from "@/lib/api";
import type { ApiState } from "@/lib/hooks";

export function Banner({ children, strong }: { children: React.ReactNode; strong?: boolean }) {
  return (
    <div
      className={`border px-4 py-3 text-[13px] leading-relaxed ${strong ? "border-ink bg-ink text-paper" : "border-ink-40"}`}
    >
      {children}
    </div>
  );
}

export function ConfigBanner() {
  if (!configError) return null;
  return (
    <div className="mx-auto max-w-[1280px] px-4 pt-4 sm:px-8">
      <Banner strong>
        <b className="font-mono text-[11px] uppercase tracking-[0.1em]">Configuration error.</b> {configError}
      </Banner>
    </div>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div
      role="status"
      className="border border-dashed border-ink-40 px-4 py-10 text-center font-mono text-[11px] uppercase tracking-[0.14em] text-ink-60"
    >
      {label}…
    </div>
  );
}

export function ErrorBox({
  error,
  onRetry,
}: {
  error: { message: string; unreachable?: boolean };
  onRetry?: () => void;
}) {
  return (
    <div role="alert" className="border border-ink px-4 py-5">
      <div className="kicker !text-ink">
        {error.unreachable ? "Backend unreachable or waking up" : "Request failed"}
      </div>
      <p className="mt-2 max-w-[80ch] text-[13.5px] leading-relaxed">{error.message}</p>
      {onRetry ? (
        <button type="button" className="btn mt-3" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="border border-dashed border-ink-40 px-4 py-8 text-center">
      <div className="serif text-[18px]">{title}</div>
      {children ? <div className="mx-auto mt-1 max-w-[70ch] text-[13px] text-ink-60">{children}</div> : null}
    </div>
  );
}

/** Renders loading / error (with retry) / empty / data. Keeps stale data visible while refetching. */
export default function Stateful<T>({
  state,
  children,
  isEmpty,
  empty,
  label,
}: {
  state: ApiState<T>;
  children: (data: T) => React.ReactNode;
  isEmpty?: (data: T) => boolean;
  empty?: React.ReactNode;
  label?: string;
}) {
  if (state.error) return <ErrorBox error={state.error} onRetry={state.refetch} />;
  if (!state.data) return <Loading label={label} />;
  if (isEmpty?.(state.data)) return <>{empty ?? <Empty title="Nothing to show" />}</>;
  return (
    <div className={state.loading ? "opacity-50 transition-opacity" : ""} aria-busy={state.loading}>
      {children(state.data)}
    </div>
  );
}
