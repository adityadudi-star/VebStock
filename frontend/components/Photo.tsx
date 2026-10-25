"use client";

import { motion } from "motion/react";
import { useState } from "react";
import { PHOTOS, photoUrl, type PhotoKey, VIEW_PHOTO } from "@/lib/photos";
import { useReduced } from "./Motion";

/**
 * Photo with a flat tone treatment (greyscale, sage tint and a flat charcoal wash).
 * Fixed aspect box so nothing shifts; falls back to a flat sage block if the image cannot load.
 */
export function Photo({
  k,
  w = 1200,
  ratio = 1.6,
  eager = false,
  className = "",
  tint = true,
  scale = 1,
  fill = false,
}: {
  k: PhotoKey;
  w?: number;
  ratio?: number;
  eager?: boolean;
  className?: string;
  tint?: boolean;
  scale?: number;
  fill?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  const p = PHOTOS[k];
  return (
    <div className={`${fill ? "absolute inset-0" : "relative"} overflow-hidden bg-sage ${className}`} style={fill ? undefined : { aspectRatio: String(ratio) }}>
      {!failed ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          ref={(el) => {
            if (el && el.complete && el.naturalWidth === 0) setFailed(true);
          }}
          src={photoUrl(k, w)}
          alt={p.alt}
          width={w}
          height={Math.round(w / ratio)}
          loading={eager ? "eager" : "lazy"}
          decoding="async"
          referrerPolicy="no-referrer"
          onError={() => setFailed(true)}
          className="absolute inset-0 h-full w-full object-cover"
          style={{ filter: tint ? "grayscale(1) contrast(1.05)" : undefined, transform: scale !== 1 ? `scale(${scale})` : undefined }}
        />
      ) : (
        <span className="sr-only">{p.alt}</span>
      )}
      {tint && !failed ? (
        <>
          <div aria-hidden className="absolute inset-0 bg-sage opacity-75 mix-blend-multiply" />
          <div aria-hidden className="absolute inset-0 bg-ink opacity-20" />
        </>
      ) : null}
    </div>
  );
}

/** Wide banner revealed on scroll with a clip-path wipe and a slow settle. */
export function PhotoBanner({ href, caption }: { href: string; caption?: string }) {
  const k = VIEW_PHOTO[href] ?? "warehouse";
  const reduced = useReduced();
  const inner = <Photo k={k} w={1600} ratio={3.4} className="!aspect-[16/7] sm:!aspect-[3.4/1]" eager />;
  return (
    <figure className="mb-8">
      {reduced ? (
        inner
      ) : (
        <motion.div
          initial={{ clipPath: "inset(0 0 100% 0)" }}
          animate={{ clipPath: "inset(0 0 0% 0)" }}
          transition={{ duration: 0.9, ease: [0.22, 0.61, 0.36, 1] }}
        >
          <motion.div initial={{ scale: 1.1 }} animate={{ scale: 1 }} transition={{ duration: 1.4, ease: "easeOut" }}>
            {inner}
          </motion.div>
        </motion.div>
      )}
      {caption ? <figcaption className="kicker mt-1">{caption}</figcaption> : null}
    </figure>
  );
}
