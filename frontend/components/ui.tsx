"use client";

import { motion } from "motion/react";
import { useId } from "react";
import { Reveal, useReduced } from "./Motion";

export function Section({
  title,
  kicker,
  aside,
  children,
}: {
  title: string;
  kicker?: string;
  aside?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Reveal className="mb-12">
      <section>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3 border-t border-ink pt-3">
        <div>
          {kicker ? <div className="kicker">{kicker}</div> : null}
          <h2 className="h2">{title}</h2>
        </div>
        {aside ? <div className="flex flex-wrap items-center gap-2">{aside}</div> : null}
      </div>
      {children}
      </section>
    </Reveal>
  );
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: { id: T; label: React.ReactNode }[];
  value: T;
  onChange: (t: T) => void;
}) {
  const group = useId();
  const reduced = useReduced();
  return (
    <div role="tablist" className="mb-4 flex flex-wrap border-b border-ink">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          type="button"
          aria-selected={value === t.id}
          onClick={() => onChange(t.id)}
          className={`relative -mb-px border border-b-0 px-3 py-2 font-mono text-[11px] uppercase tracking-[0.08em] transition-colors active:scale-[0.97] ${
            value === t.id ? "border-ink text-paper" : "border-transparent hover:bg-ink-08"
          }`}
        >
          {value === t.id ? (
            <motion.span
              layoutId={`tab-${group}`}
              className="absolute inset-0 bg-ink"
              transition={reduced ? { duration: 0 } : { type: "spring", stiffness: 500, damping: 40 }}
            />
          ) : null}
          <span className="relative">{t.label}</span>
        </button>
      ))}
    </div>
  );
}

export function Field({
  label,
  children,
  className = "",
}: {
  label: string;
  children: (id: string) => React.ReactNode;
  className?: string;
}) {
  const id = useId();
  return (
    <div className={className}>
      <label htmlFor={id} className="field-label">
        {label}
      </label>
      {children(id)}
    </div>
  );
}

export function Select({
  label,
  value,
  onChange,
  options,
  placeholder = "All",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  placeholder?: string | null;
}) {
  return (
    <Field label={label}>
      {(id) => (
        <select id={id} className="field w-full" value={value} onChange={(e) => onChange(e.target.value)}>
          {placeholder !== null ? <option value="">{placeholder}</option> : null}
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      )}
    </Field>
  );
}

export function TextInput({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  min,
  max,
  step,
  error,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  min?: number;
  max?: number;
  step?: number;
  error?: string;
}) {
  return (
    <Field label={label}>
      {(id) => (
        <>
          <input
            id={id}
            className="field w-full"
            type={type}
            value={value}
            placeholder={placeholder}
            min={min}
            max={max}
            step={step}
            onChange={(e) => onChange(e.target.value)}
            aria-invalid={!!error}
          />
          {error ? <div className="mt-1 text-[12px] font-medium">{error}</div> : null}
        </>
      )}
    </Field>
  );
}

export function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 font-mono text-[11px] uppercase tracking-[0.08em]">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 cursor-pointer appearance-none border border-ink checked:bg-ink"
      />
      {label}
    </label>
  );
}

export function KV({ rows }: { rows: [React.ReactNode, React.ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[minmax(0,1fr)_auto] border-t border-ink-15 text-[13px]">
      {rows.map(([k, v], i) => (
        <div key={i} className="contents">
          <dt className="border-b border-ink-15 py-2 pr-4 text-ink-60">{k}</dt>
          <dd className="num border-b border-ink-15 py-2 text-right">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
