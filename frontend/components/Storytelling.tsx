"use client";

import { useEffect, useRef } from "react";
import type { PhotoKey } from "@/lib/photos";
import { Photo } from "./Photo";
import { Stagger, StaggerItem, useReduced } from "./Motion";

/** Overview masthead: photo with a GSAP parallax drift.. */
export function Hero({ snapshot }: { snapshot?: string }) {
  const root = useRef<HTMLElement>(null);
  const img = useRef<HTMLDivElement>(null);
  const text = useRef<HTMLDivElement>(null);
  const reduced = useReduced();

  useEffect(() => {
    if (reduced) return;
    let ctx: { revert: () => void } | undefined;
    let cancelled = false;
    (async () => {
      const [{ gsap }, { ScrollTrigger }] = await Promise.all([import("gsap"), import("gsap/ScrollTrigger")]);
      if (cancelled || !root.current) return;
      gsap.registerPlugin(ScrollTrigger);
      ctx = gsap.context(() => {
        const st = { trigger: root.current, start: "top top", end: "bottom top", scrub: true };
        gsap.to(img.current, { yPercent: 16, ease: "none", scrollTrigger: st });
        gsap.to(text.current, { yPercent: -14, opacity: 0.15, ease: "none", scrollTrigger: st });
      }, root);
    })();
    return () => {
      cancelled = true;
      ctx?.revert();
    };
  }, [reduced]);

  return (
    <header ref={root} className="relative mb-10 h-[min(72vh,600px)] min-h-[380px] overflow-hidden bg-sage text-paper">
      <div ref={img} className="absolute -top-[10%] bottom-0 left-0 right-0 will-change-transform">
        <Photo k="warehouse" w={1800} fill eager />
        <div aria-hidden className="absolute inset-0 bg-ink opacity-30" />
      </div>
      <div ref={text} className="relative flex h-full flex-col justify-end p-6 sm:p-10">
        <div className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-paper-60">
          Distribution intelligence and inventory optimization
        </div>
        <h1 className="serif mt-3 text-[64px] font-medium leading-[0.92] tracking-[-0.03em] sm:text-[116px]">VebStock</h1>
        <p className="serif mt-3 text-[22px] italic leading-snug sm:text-[32px]">The right stock. The right place. The right time.</p>
        {snapshot ? (
          <div className="mt-5 inline-block self-start border border-paper px-2 py-1 font-mono text-[10.5px] uppercase tracking-[0.12em]">
            Simulated data snapshot: {snapshot}
          </div>
        ) : null}
      </div>
    </header>
  );
}

const STEPS = [
  {
    n: "01",
    title: "Forecast",
    body: "For every store and product the system predicts demand as a range: a Low, an Expected and a High value for the next 7, 14 and 30 days. The range tells planners how sure the forecast is.",
  },
  {
    n: "02",
    title: "Allocate, oldest stock first",
    body: "An optimizer decides which warehouse batch ships to which store. It ships the oldest stock first, respects lane and store capacity and shelf life, and balances the cost of running out against the cost of expiry.",
  },
  {
    n: "03",
    title: "Explain",
    body: "Every shipment line carries a plain-language reason: what the store needs, why this batch, why this lane. Planners can override a line, with a recorded reason, and every override is checked against the plan rules.",
  },
  {
    n: "04",
    title: "Prove by replay",
    body: "Both the optimized policy and a simple reorder-point baseline are replayed day by day on the same held-out simulated demand. Results are reported as measured, including targets that are not met.",
  },
];

/** Pinned, scrubbed storytelling band. Falls back to a plain staggered grid for reduced motion or narrow screens. */
export function HowItWorks() {
  const root = useRef<HTMLElement>(null);
  const reduced = useReduced();

  useEffect(() => {
    if (reduced) return;
    let ctx: { revert: () => void } | undefined;
    let cancelled = false;
    (async () => {
      const [{ gsap }, { ScrollTrigger }] = await Promise.all([import("gsap"), import("gsap/ScrollTrigger")]);
      if (cancelled || !root.current) return;
      gsap.registerPlugin(ScrollTrigger);
      const mm = gsap.matchMedia();
      mm.add("(min-width: 900px)", () => {
        const panels = gsap.utils.toArray<HTMLElement>(".hiw-panel", root.current!);
        const rows = gsap.utils.toArray<HTMLElement>(".hiw-row", root.current!);
        gsap.set(panels, { autoAlpha: 0, y: 24 });
        gsap.set(panels[0], { autoAlpha: 1, y: 0 });
        gsap.set(rows, { opacity: 0.3 });
        gsap.set(rows[0], { opacity: 1 });
        const tl = gsap.timeline({
          defaults: { ease: "none" },
          scrollTrigger: { trigger: root.current, start: "top 12%", end: "+=" + STEPS.length * 55 + "%", scrub: 0.6, pin: true, anticipatePin: 1 },
        });
        tl.fromTo(".hiw-bar", { scaleY: 0 }, { scaleY: 1, duration: STEPS.length - 1 }, 0);
        for (let i = 1; i < STEPS.length; i++) {
          tl.to(panels[i - 1], { autoAlpha: 0, y: -24, duration: 0.35 }, i - 0.5);
          tl.to(panels[i], { autoAlpha: 1, y: 0, duration: 0.35 }, i - 0.35);
          tl.to(rows[i], { opacity: 1, duration: 0.3 }, i - 0.35);
          tl.to(rows[i - 1], { opacity: 0.3, duration: 0.3 }, i - 0.35);
        }
        tl.to({}, { duration: 0.4 });
      });
      ctx = mm;
    })();
    return () => {
      cancelled = true;
      ctx?.revert();
    };
  }, [reduced]);

  return (
    <section ref={root} aria-label="How VebStock works" className="mb-14 border-t border-ink pt-3">
      <div className="kicker">How it works</div>
      <h2 className="h2 mb-6">Four steps from forecast to proof</h2>

      {/* Wide screens, motion allowed: pinned stage. Everything else: the plain grid below. */}
      <div className={reduced ? "hidden" : "hidden min-[900px]:block"}>
        <div className="grid min-h-[320px] grid-cols-[1.4fr_1fr] gap-12">
          <div className="relative">
            {STEPS.map((s) => (
              <div key={s.n} className="hiw-panel absolute inset-0">
                <div className="serif text-[120px] font-medium leading-none tracking-[-0.04em] text-ink-15">{s.n}</div>
                <h3 className="serif -mt-4 text-[44px] font-medium leading-none tracking-[-0.02em]">{s.title}</h3>
                <p className="mt-4 max-w-[52ch] text-[16px] leading-relaxed">{s.body}</p>
              </div>
            ))}
          </div>
          <div className="relative pl-6">
            <div className="absolute bottom-0 left-0 top-0 w-px bg-ink-15" />
            <div className="hiw-bar absolute left-0 top-0 h-full w-[3px] origin-top bg-ink" />
            {STEPS.map((s) => (
              <div key={s.n} className="hiw-row border-b border-ink-15 py-4">
                <span className="num mr-3 text-[11px] text-ink-60">{s.n}</span>
                <span className="serif text-[22px]">{s.title}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className={reduced ? "" : "min-[900px]:hidden"}>
        <Stagger className="grid gap-px border border-ink-15 bg-ink-15 sm:grid-cols-2 [&>*]:bg-paper">
          {STEPS.map((s) => (
            <StaggerItem key={s.n}>
              <div className="h-full p-5">
                <div className="num text-[11px] text-ink-60">{s.n}</div>
                <h3 className="serif text-[24px] font-medium">{s.title}</h3>
                <p className="mt-2 text-[14px] leading-relaxed text-ink-60">{s.body}</p>
              </div>
            </StaggerItem>
          ))}
        </Stagger>
      </div>
    </section>
  );
}

const STRIP: { k: PhotoKey; cap: string }[] = [
  { k: "aisleWorkers", cap: "Receiving" },
  { k: "racks", cap: "Storage" },
  { k: "dusk", cap: "Dispatch" },
  { k: "dairy", cap: "Cold chain" },
  { k: "cereal", cap: "On the shelf" },
];

/** Photo strip, five frames, staggered reveal. */
export function PhotoStrip() {
  return (
    <section aria-label="Photo strip" className="mb-14">
      <Stagger className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5" gap={0.09}>
        {STRIP.map((s) => (
          <StaggerItem key={s.k}>
            <figure>
              <Photo k={s.k} w={500} ratio={0.8} className="group" />
              <figcaption className="kicker mt-1">{s.cap}</figcaption>
            </figure>
          </StaggerItem>
        ))}
      </Stagger>
    </section>
  );
}
