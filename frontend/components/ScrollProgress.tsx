"use client";

import { motion, useScroll } from "motion/react";
import { useReduced } from "./Motion";

/** Thin flat scroll-progress line at the very top: charcoal fill on a sage track. */
export default function ScrollProgress() {
  const { scrollYProgress } = useScroll();
  const reduced = useReduced();
  return (
    <div aria-hidden="true" className="fixed inset-x-0 top-0 z-[60] h-[3px] bg-sage-30">
      <motion.div
        className="h-full origin-left bg-ink"
        style={reduced ? { transform: "scaleX(0)" } : { scaleX: scrollYProgress }}
      />
    </div>
  );
}
