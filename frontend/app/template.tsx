"use client";

import { motion } from "motion/react";
import { useReduced } from "@/components/Motion";

/** Re-mounted on every route change: a short flat fade and rise between views. */
export default function Template({ children }: { children: React.ReactNode }) {
  const reduced = useReduced();
  if (reduced) return <>{children}</>;
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, ease: "easeOut" }}>
      {children}
    </motion.div>
  );
}
