"use client";

import { useId } from "react";

export default function Slider({
  label,
  value,
  onChange,
  min = 0,
  max = 1,
  step = 0.05,
  hint,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  hint?: string;
}) {
  const id = useId();
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <label htmlFor={id} className="text-[13px]">
          {label}
        </label>
        <output htmlFor={id} className="num text-[13px] font-medium">
          {value.toFixed(2)}
        </output>
      </div>
      <input
        id={id}
        type="range"
        className="slider"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      {hint ? <div className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink-60">{hint}</div> : null}
    </div>
  );
}
