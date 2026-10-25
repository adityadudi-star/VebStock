"use client";

import { motion } from "motion/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { VIEWS } from "@/lib/nav";
import { canAccess } from "@/lib/roles";
import { useAuth } from "./AuthProvider";
import { useReduced } from "./Motion";

export default function Drawer() {
  const pathname = usePathname();
  // The drawer is open only while the pathname it was opened on is still current,
  // so any route change closes it without an effect.
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn === pathname;
  const btnRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const reduced = useReduced();
  const { status, user, role, roleDef, logout } = useAuth();
  // Open mode keeps the full menu; a role (signed in, or chosen as a demo view) narrows it to that role's pages.
  const signedOut = status === "secure" && !user;
  const items = signedOut ? [] : [
    ...(roleDef ? [{ n: "00", href: roleDef.home, title: `${roleDef.label} dashboard`, blurb: "Your role's home page" }] : []),
    ...VIEWS.filter((v) => !role || canAccess(role, v.href)),
  ];

  useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    const btn = btnRef.current;
    const focusables = () => Array.from(panel?.querySelectorAll<HTMLElement>("a[href], button") ?? []);
    focusables()[0]?.focus();
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpenOn(null);
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
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
      btn?.focus({ preventScroll: true });
    };
  }, [open]);

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        aria-label="Open menu"
        aria-expanded={open}
        aria-controls="view-drawer"
        onClick={() => setOpenOn(pathname)}
        className="fixed left-3 top-3 z-30 flex h-10 w-10 flex-col items-center justify-center gap-[5px] border border-ink bg-paper sm:left-5 sm:top-5"
      >
        <span className="block h-px w-5 bg-ink" />
        <span className="block h-px w-5 bg-ink" />
        <span className="block h-px w-5 bg-ink" />
      </button>

      <motion.div
        aria-hidden="true"
        onClick={() => setOpenOn(null)}
        initial={false}
        animate={{ opacity: open ? 1 : 0 }}
        transition={{ duration: reduced ? 0 : 0.2 }}
        className={`fixed inset-0 z-[70] bg-ink-40 ${open ? "" : "pointer-events-none"}`}
      />

      <motion.aside
        id="view-drawer"
        data-lenis-prevent
        initial={false}
        animate={{ x: open ? "0%" : "-100%" }}
        transition={reduced ? { duration: 0 } : { type: "spring", stiffness: 380, damping: 38, mass: 0.9 }}
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Views"
        inert={!open}
        className="fixed inset-y-0 left-0 z-[80] flex w-full max-w-[420px] flex-col overflow-y-auto bg-ink text-paper"
      >
        <div className="flex items-start justify-between px-6 pb-4 pt-5 sm:px-8">
          <div>
            <div className="serif text-[26px] leading-none">VebStock</div>
            <div className="mt-2 font-mono text-[10px] uppercase tracking-[0.14em] text-paper-60">
              The right stock. The right place. The right time.
            </div>
          </div>
          <button
            type="button"
            onClick={() => setOpenOn(null)}
            aria-label="Close menu"
            className="relative h-10 w-10 shrink-0 border border-paper-60"
          >
            <span className="absolute left-1/2 top-1/2 block h-px w-5 -translate-x-1/2 -translate-y-1/2 rotate-45 bg-paper" />
            <span className="absolute left-1/2 top-1/2 block h-px w-5 -translate-x-1/2 -translate-y-1/2 -rotate-45 bg-paper" />
          </button>
        </div>
        <nav aria-label="Views" className="flex-1 px-6 pb-8 sm:px-8">
          <motion.ol
            className="border-t border-paper-60"
            initial={false}
            animate={open ? "open" : "closed"}
            variants={{ open: { transition: { staggerChildren: reduced ? 0 : 0.035, delayChildren: reduced ? 0 : 0.08 } }, closed: {} }}
          >
            {items.map((v) => {
              const current = pathname === v.href || pathname.startsWith(`${v.href}/`);
              return (
                <motion.li
                  key={v.href}
                  className="border-b border-paper-15"
                  variants={{ open: { opacity: 1, x: 0 }, closed: { opacity: reduced ? 1 : 0, x: reduced ? 0 : -18 } }}
                >
                  <Link
                    href={v.href}
                    aria-current={current ? "page" : undefined}
                    className={`flex items-baseline gap-4 px-2 py-3 transition-transform active:scale-[0.99] ${current ? "bg-paper text-ink" : "hover:bg-paper-15"}`}
                  >
                    <span className="num w-6 text-[11px] opacity-60">{v.n}</span>
                    <span className="min-w-0">
                      <span className="serif block text-[21px] leading-tight">{v.title}</span>
                      <span className="block font-mono text-[10px] uppercase tracking-[0.1em] opacity-60">
                        {v.blurb}
                      </span>
                    </span>
                  </Link>
                </motion.li>
              );
            })}
          </motion.ol>
          <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-paper-60 pt-4">
            {user || (status === "open" && roleDef) ? (
              <Link
                href="/"
                onClick={logout}
                className="inline-flex items-center gap-2 border border-paper-60 px-3 py-2 font-mono text-[11px] uppercase tracking-[0.08em] hover:bg-paper-15"
              >
                {user ? "Sign out" : "Switch role"}
              </Link>
            ) : (
              <Link href="/" className="inline-flex items-center gap-2 border border-paper-60 px-3 py-2 font-mono text-[11px] uppercase tracking-[0.08em] hover:bg-paper-15">
                Choose a role
              </Link>
            )}
            {user ? <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-paper-60">{user.username}</span> : null}
          </div>
          <p className="mt-6 font-mono text-[10px] uppercase leading-relaxed tracking-[0.1em] text-paper-60">
            All figures come from simulated data. Targets are shown separately and never assumed met.
          </p>
        </nav>
      </motion.aside>
    </>
  );
}
