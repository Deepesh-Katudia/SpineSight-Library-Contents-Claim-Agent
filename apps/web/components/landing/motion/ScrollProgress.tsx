"use client";

// A hairline across the top of the page that fills with reading progress.

import { motion, useReducedMotion, useScroll, useSpring } from "motion/react";

export function ScrollProgress() {
  const reduced = useReducedMotion();
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, { stiffness: 160, damping: 32, mass: 0.3 });
  if (reduced) return null;
  return (
    <motion.div
      aria-hidden
      className="fixed inset-x-0 top-0 z-40 h-[2px] origin-left bg-signal shadow-[0_0_12px_rgba(255,107,44,0.8)]"
      style={{ scaleX }}
    />
  );
}
