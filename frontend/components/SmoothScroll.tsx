"use client";

import { useEffect } from "react";

/**
 * Lenis smooth scrolling wired to GSAP ScrollTrigger. Client-only, code-split, disabled for
 * reduced motion, destroyed on unmount. Inner scroll areas opt out with data-lenis-prevent.
 */
export default function SmoothScroll() {
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let cancelled = false;
    let cleanup: (() => void) | undefined;
    (async () => {
      const [{ default: Lenis }, { gsap }, { ScrollTrigger }] = await Promise.all([
        import("lenis"),
        import("gsap"),
        import("gsap/ScrollTrigger"),
      ]);
      if (cancelled) return;
      gsap.registerPlugin(ScrollTrigger);
      const lenis = new Lenis({ lerp: 0.12, wheelMultiplier: 0.95, anchors: true });
      const onScroll = () => ScrollTrigger.update();
      lenis.on("scroll", onScroll);
      const tick = (t: number) => lenis.raf(t * 1000);
      gsap.ticker.add(tick);
      gsap.ticker.lagSmoothing(0);
      cleanup = () => {
        gsap.ticker.remove(tick);
        lenis.off("scroll", onScroll);
        lenis.destroy();
      };
    })();
    return () => {
      cancelled = true;
      cleanup?.();
    };
  }, []);
  return null;
}
