"use client";

import { animate, useInView } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { useReduced } from "./Motion";

/** Counts up to `value` when scrolled into view. Reduced motion shows the final value at once. */
export default function CountUp({
  value,
  format,
  duration = 1.2,
}: {
  value: number;
  format: (n: number) => string;
  duration?: number;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "0px 0px -5% 0px" });
  const reduced = useReduced();
  const [v, setV] = useState(0);
  useEffect(() => {
    if (reduced || !inView) return;
    const c = animate(0, value, { duration, ease: "easeOut", onUpdate: setV });
    return () => c.stop();
  }, [inView, value, reduced, duration]);
  return (
    <span ref={ref} className="num-display">
      {format(reduced ? value : v)}
    </span>
  );
}
