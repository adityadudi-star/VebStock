"use client";

import { Bot } from "lucide-react";
import { motion, useMotionValue, useSpring } from "motion/react";
import dynamic from "next/dynamic";
import { createContext, useContext, useEffect, useRef, useState } from "react";
import { useReduced } from "./Motion";
import { Loading } from "./Stateful";

// The chat widget (react-chatbotify) is a separate chunk, fetched the first time the panel opens.
const AssistantWidget = dynamic(() => import("./AssistantWidget"), {
  ssr: false,
  loading: () => <Loading label="Loading assistant" />,
});

const DEFAULT_LABEL =
  "Intent-matching assistant (open-source RapidFuzz, no LLM): it understands questions about stock, forecasts, risks, plans, comparison results and how VebStock works, and answers only from stored data.";

interface Ctx {
  open: boolean;
  setOpen: (v: boolean) => void;
  everOpened: boolean;
  label: string;
  setLabel: (l: string) => void;
  buttonRef: React.RefObject<HTMLButtonElement | null>;
}

const AssistantContext = createContext<Ctx | null>(null);

function useAssistant(): Ctx {
  const c = useContext(AssistantContext);
  if (!c) throw new Error("AssistantProvider missing");
  return c;
}

/** Layout-level state: the widget stays mounted after first open, so the conversation survives navigation and close/reopen. */
export function AssistantProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpenState] = useState(false);
  const [everOpened, setEverOpened] = useState(false);
  const [label, setLabel] = useState(DEFAULT_LABEL);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const setOpen = (v: boolean) => {
    setOpenState(v);
    if (v) setEverOpened(true);
  };
  return (
    <AssistantContext.Provider value={{ open, setOpen, everOpened, label, setLabel, buttonRef }}>
      {children}
      <AssistantButton />
      <AssistantPanel />
    </AssistantContext.Provider>
  );
}

/** Top-right assistant button with a flat magnetic hover. Mouse only; reduced motion gets a plain colour change. */
function AssistantButton() {
  const { open, setOpen, buttonRef } = useAssistant();
  const reduced = useReduced();
  const wrap = useRef<HTMLDivElement>(null);
  const x = useSpring(useMotionValue(0), { stiffness: 260, damping: 18, mass: 0.4 });
  const y = useSpring(useMotionValue(0), { stiffness: 260, damping: 18, mass: 0.4 });
  const scale = useSpring(useMotionValue(1), { stiffness: 300, damping: 20 });
  const rotate = useSpring(useMotionValue(0), { stiffness: 260, damping: 18 });
  const [near, setNear] = useState(false);

  useEffect(() => {
    if (reduced) return;
    const NEAR = 60;
    const onMove = (e: PointerEvent) => {
      if (e.pointerType !== "mouse" || !wrap.current) return;
      const r = wrap.current.getBoundingClientRect();
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const dx = e.clientX - cx;
      const dy = e.clientY - cy;
      const dist = Math.hypot(dx, dy);
      if (dist <= r.width / 2 + NEAR) {
        const clamp = (v: number, m: number) => Math.max(-m, Math.min(m, v));
        x.set(clamp(dx * 0.3, 6));
        y.set(clamp(dy * 0.3, 6));
        rotate.set(clamp(dx * 0.25, 10));
        scale.set(1.1);
        setNear(true);
      } else {
        x.set(0);
        y.set(0);
        rotate.set(0);
        scale.set(1);
        setNear(false);
      }
    };
    const onLeave = () => {
      x.set(0);
      y.set(0);
      rotate.set(0);
      scale.set(1);
      setNear(false);
    };
    window.addEventListener("pointermove", onMove);
    document.documentElement.addEventListener("pointerleave", onLeave);
    return () => {
      window.removeEventListener("pointermove", onMove);
      document.documentElement.removeEventListener("pointerleave", onLeave);
    };
  }, [reduced, x, y, scale, rotate]);

  return (
    <div ref={wrap} className="fixed right-3 top-3 z-30 sm:right-5 sm:top-5">
      {!reduced ? (
        <>
          <motion.span
            aria-hidden
            className="pointer-events-none absolute inset-0 border border-sage"
            initial={false}
            animate={{ scale: near ? 1.9 : 1, opacity: near ? 1 : 0 }}
            transition={{ duration: 0.35, ease: "easeOut" }}
          />
          <motion.span
            aria-hidden
            className="pointer-events-none absolute right-full top-1/2 mr-3 -translate-y-1/2 whitespace-nowrap border border-ink bg-paper px-2 py-1 font-mono text-[10.5px] uppercase tracking-[0.12em]"
            initial={false}
            animate={{ x: near ? 0 : 12, opacity: near ? 1 : 0 }}
            transition={{ duration: 0.25, ease: "easeOut" }}
          >
            Ask VebStock
          </motion.span>
        </>
      ) : null}
      <motion.button
        ref={buttonRef}
        type="button"
        aria-label="Ask the VebStock assistant"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls="assistant-panel"
        onClick={() => setOpen(true)}
        data-testid="assistant-button"
        style={reduced ? undefined : { x, y, scale, rotate }}
        whileTap={reduced ? undefined : { scale: 0.92 }}
        className="relative flex h-10 w-10 items-center justify-center border border-ink bg-paper text-ink transition-colors hover:bg-ink hover:text-paper"
      >
        <Bot size={20} strokeWidth={1.5} aria-hidden />
      </motion.button>
    </div>
  );
}

function AssistantPanel() {
  const { open, setOpen, everOpened, label, setLabel, buttonRef } = useAssistant();
  const reduced = useReduced();
  const panelRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    const btn = buttonRef.current;
    const focusables = () =>
      Array.from(panel?.querySelectorAll<HTMLElement>("a[href], button:not(:disabled), input, textarea, summary") ?? []);
    const t = window.setTimeout(() => {
      const target = panel?.querySelector<HTMLElement>("textarea, input");
      (target ?? panel?.querySelector<HTMLElement>("button"))?.focus();
    }, 80);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        return;
      }
      if (e.key !== "Tab") return;
      const f = focusables();
      if (!f.length) return;
      const first = f[0];
      const last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(t);
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
      btn?.focus({ preventScroll: true });
    };
  }, [open, setOpen, buttonRef]);

  return (
    <>
      <motion.div
        aria-hidden="true"
        onClick={() => setOpen(false)}
        initial={false}
        animate={{ opacity: open ? 1 : 0 }}
        transition={{ duration: reduced ? 0 : 0.2 }}
        className={`fixed inset-0 z-[70] bg-ink-40 ${open ? "" : "pointer-events-none"}`}
      />
      <motion.aside
        id="assistant-panel"
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="VebStock assistant"
        inert={!open}
        data-lenis-prevent
        initial={false}
        animate={{ x: open ? "0%" : "100%" }}
        transition={reduced ? { duration: 0 } : { type: "spring", stiffness: 380, damping: 38, mass: 0.9 }}
        className="fixed inset-y-0 right-0 z-[80] flex w-full flex-col border-l border-ink bg-paper sm:max-w-[420px]"
      >
        <div className="flex items-start justify-between gap-4 border-b border-ink px-5 pb-3 pt-5">
          <div>
            <div className="kicker">Ask a question</div>
            <h2 className="serif text-[26px] font-medium leading-tight">Assistant</h2>
            <p className="mt-1 text-[12px] leading-relaxed text-ink-60" data-testid="assistant-label">
              {label}
            </p>
          </div>
          <button
            type="button"
            aria-label="Close assistant"
            onClick={() => setOpen(false)}
            className="relative h-10 w-10 shrink-0 border border-ink active:scale-95"
          >
            <span className="absolute left-1/2 top-1/2 block h-px w-5 -translate-x-1/2 -translate-y-1/2 rotate-45 bg-ink" />
            <span className="absolute left-1/2 top-1/2 block h-px w-5 -translate-x-1/2 -translate-y-1/2 -rotate-45 bg-ink" />
          </button>
        </div>
        <div className="min-h-0 flex-1" data-lenis-prevent>
          {everOpened ? <AssistantWidget onLabel={setLabel} active={open} /> : null}
        </div>
      </motion.aside>
    </>
  );
}
