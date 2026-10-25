"use client";

import { AnimatePresence, motion } from "motion/react";
import { useId, useState } from "react";
import { GLOSSARY } from "@/lib/glossary";
import { useReduced } from "./Motion";

/** Animated accordion. Used for every page's "Technical details". */
export default function Disclosure({
  title = "Technical details",
  children,
  defaultOpen = false,
}: {
  title?: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  const reduced = useReduced();
  return (
    <div className="mt-10 border-t border-ink-15">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-3 py-3 text-left font-mono text-[11px] uppercase tracking-[0.12em] active:scale-[0.995]"
      >
        <span>{title}</span>
        <motion.span aria-hidden animate={{ rotate: open ? 45 : 0 }} transition={{ duration: reduced ? 0 : 0.2 }} className="text-[16px] leading-none">
          +
        </motion.span>
      </button>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            id={id}
            key="c"
            initial={reduced ? false : { height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={reduced ? { opacity: 0 } : { height: 0, opacity: 0 }}
            transition={{ duration: reduced ? 0 : 0.28, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <div className="pb-6 pt-2">{children}</div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

/** Inline term with a plain-language tooltip from the glossary. */
export function Term({ k, children }: { k: keyof typeof GLOSSARY; children?: React.ReactNode }) {
  const g = GLOSSARY[k];
  return (
    <abbr title={g.plain} className="cursor-help underline decoration-ink-40 decoration-dotted underline-offset-2">
      {children ?? g.term}
    </abbr>
  );
}

export function Glossary() {
  return (
    <dl className="grid gap-x-8 sm:grid-cols-2">
      {Object.values(GLOSSARY).map((g) => (
        <div key={g.term} className="border-b border-ink-15 py-2">
          <dt className="font-mono text-[11px] uppercase tracking-[0.1em]">{g.term}</dt>
          <dd className="text-[13px] text-ink-60">{g.plain}</dd>
        </div>
      ))}
    </dl>
  );
}
