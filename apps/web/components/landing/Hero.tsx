"use client";

// Full-height opening scene. On load the headline rises line by line out of a mask; on scroll the
// layers separate (headline drifts up and fades, glow swells, the tilted shelf swings flat to face
// the viewer) so the page opens like a stage rather than a slide.

import Link from "next/link";
import { motion, useReducedMotion, useScroll, useSpring, useTransform } from "motion/react";
import { useRef } from "react";

import { HeroShelf } from "./HeroShelf";
import { LiveTicker } from "./LiveTicker";

const EASE_OUT_EXPO = [0.16, 1, 0.3, 1] as const;
const LINE_STAGGER_S = 0.14;
const HEADLINE_LINES = [
  <>Every spine.</>,
  <>
    <span className="italic text-brass">Measured,</span> priced,
  </>,
  <>proven.</>,
];

function MaskedLine({ children, index, still }: { children: React.ReactNode; index: number; still: boolean }) {
  return (
    <span className="block overflow-hidden pb-[0.08em]">
      <motion.span
        className="block"
        initial={still ? false : { y: "110%", rotate: 2 }}
        animate={{ y: "0%", rotate: 0 }}
        transition={{ duration: 1.2, ease: EASE_OUT_EXPO, delay: 0.15 + index * LINE_STAGGER_S }}
      >
        {children}
      </motion.span>
    </span>
  );
}

export function Hero() {
  const ref = useRef<HTMLElement>(null);
  const reduced = !!useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const smooth = useSpring(scrollYProgress, { stiffness: 140, damping: 30, mass: 0.3 });

  const headlineY = useTransform(smooth, [0, 1], [0, -180]);
  const headlineOpacity = useTransform(smooth, [0, 0.55], [1, 0]);
  const glowScale = useTransform(smooth, [0, 1], [1, 1.7]);
  const glowY = useTransform(smooth, [0, 1], [0, 160]);
  const wordmarkX = useTransform(smooth, [0, 1], ["0%", "-18%"]);
  const shelfTilt = useTransform(smooth, [0, 0.45], [24, 0]);
  const shelfScale = useTransform(smooth, [0, 0.45], [0.92, 1.04]);
  const cueOpacity = useTransform(smooth, [0, 0.08], [1, 0]);

  const layer = <T,>(value: T) => (reduced ? undefined : value);

  return (
    <section ref={ref} aria-labelledby="hero-heading" className="grain relative overflow-hidden">
      <motion.div
        aria-hidden
        className="pointer-events-none absolute -right-40 -top-40 h-[620px] w-[620px] rounded-full bg-oxblood/35 blur-[130px]"
        style={layer({ scale: glowScale, y: glowY })}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -bottom-48 -left-32 h-[480px] w-[480px] rounded-full bg-brass/10 blur-[120px]"
      />
      <motion.p
        aria-hidden
        className="pointer-events-none absolute left-0 top-[46%] whitespace-nowrap font-display text-[22vw] font-semibold leading-none tracking-[-0.06em] text-paper/[0.03]"
        style={layer({ x: wordmarkX })}
      >
        SPINESIGHT · SPINESIGHT
      </motion.p>

      <div className="relative mx-auto flex min-h-[100svh] max-w-7xl flex-col px-4 pb-10 pt-14 sm:px-8 sm:pt-20">
        <motion.div style={layer({ y: headlineY, opacity: headlineOpacity })}>
          <motion.p
            className="label flex items-center gap-2 text-signal"
            initial={reduced ? false : { opacity: 0, x: -16 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, ease: EASE_OUT_EXPO }}
          >
            <span className="live-dot inline-block h-2 w-2 rounded-full bg-signal" />
            Contents claim agent · voice + vision · one sweep
          </motion.p>
          <h1
            id="hero-heading"
            className="mt-6 font-display leading-[0.86] tracking-[-0.035em] drop-shadow-[0_12px_40px_rgba(0,0,0,0.55)]"
            style={{ fontSize: "var(--text-hero)", fontVariationSettings: '"SOFT" 30, "WONK" 1' }}
          >
            {HEADLINE_LINES.map((line, i) => (
              <MaskedLine key={i} index={i} still={reduced}>
                {line}
              </MaskedLine>
            ))}
          </h1>
          <motion.div
            className="mt-10 grid gap-8 lg:grid-cols-[1.1fr_1fr] lg:items-end"
            initial={reduced ? false : { opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 1, ease: EASE_OUT_EXPO, delay: 0.75 }}
          >
            <p className="max-w-xl text-lg leading-relaxed text-paper/75 sm:text-xl">
              Walk your home library once with your phone. SpineSight talks you through it, reads and measures every
              book from its spine, prices it at local market value with a source you can click, and measures the room
              from the same pass.
            </p>
            <div className="flex flex-wrap gap-3 lg:justify-end">
              <Link
                href="/sweep"
                className="group inline-flex items-center gap-3 rounded-sm bg-signal px-6 py-4 text-lg font-medium text-ink transition-all duration-300 hover:gap-5 hover:shadow-[0_0_48px_-4px_rgba(255,107,44,0.75)] active:scale-[0.98]"
              >
                Start a live sweep <span aria-hidden>→</span>
              </Link>
              <a
                href="#rules"
                className="inline-flex items-center rounded-sm border border-paper/25 px-6 py-4 text-lg text-paper/85 transition-colors hover:border-paper hover:text-paper"
              >
                How it stays honest
              </a>
            </div>
          </motion.div>
        </motion.div>

        <div className="mt-auto pt-16 [perspective:1400px]">
          <motion.div
            className="origin-bottom"
            initial={reduced ? false : { opacity: 0, y: 60 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 1.3, ease: EASE_OUT_EXPO, delay: 0.5 }}
            style={layer({ rotateX: shelfTilt, scale: shelfScale })}
          >
            <HeroShelf />
          </motion.div>
          <motion.div
            className="mt-6"
            initial={reduced ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 1, delay: 1.1 }}
          >
            <LiveTicker />
          </motion.div>
          <motion.div
            aria-hidden
            className="label mt-8 flex items-center justify-center gap-3 text-muted"
            style={layer({ opacity: cueOpacity })}
          >
            <span className="scroll-cue relative block h-8 w-px overflow-hidden bg-paper/15" />
            Scroll
          </motion.div>
        </div>
      </div>
    </section>
  );
}
