"use client";

// A headline whose words light up one by one as it scrolls through the viewport.

import { motion, useReducedMotion, useScroll, useTransform, type MotionValue } from "motion/react";
import { useRef } from "react";

const DIM_OPACITY = 0.14;

interface ScrollWordsProps {
  text: string;
  id?: string;
  className?: string;
}

export function ScrollWords({ text, id, className }: ScrollWordsProps) {
  const ref = useRef<HTMLHeadingElement>(null);
  const reduced = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 0.9", "start 0.3"] });
  const words = text.split(" ");

  return (
    <h2 ref={ref} id={id} className={className} aria-label={text}>
      {words.map((word, i) => (
        <Word key={i} progress={scrollYProgress} range={[i / words.length, (i + 1) / words.length]} still={!!reduced}>
          {word}
        </Word>
      ))}
    </h2>
  );
}

interface WordProps {
  children: string;
  progress: MotionValue<number>;
  range: [number, number];
  still: boolean;
}

function Word({ children, progress, range, still }: WordProps) {
  const opacity = useTransform(progress, range, [DIM_OPACITY, 1]);
  return (
    <motion.span aria-hidden className="inline-block pr-[0.25em]" style={still ? undefined : { opacity }}>
      {children}
    </motion.span>
  );
}
