"use client";

// The three sweep steps with a rail that fills as you scroll past them.

import { motion, useReducedMotion, useScroll, useSpring } from "motion/react";
import { useRef } from "react";

import { RevealGroup, RevealItem } from "./Reveal";

export interface Step {
  n: string;
  title: string;
  body: string;
}

export function StepsTimeline({ steps }: { steps: readonly Step[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 0.75", "end 0.55"] });
  const fill = useSpring(scrollYProgress, { stiffness: 120, damping: 30, mass: 0.4 });

  return (
    <div ref={ref} className="relative">
      <div className="absolute inset-y-0 left-0 w-[2px] bg-rule" aria-hidden />
      <motion.div
        aria-hidden
        className="absolute inset-y-0 left-0 w-[2px] origin-top bg-oxblood"
        style={{ scaleY: reduced ? 1 : fill }}
      />
      <RevealGroup as="ol" className="divide-y divide-rule" stagger={0.15}>
        {steps.map((s, i) => (
          <RevealItem
            key={s.n}
            as="li"
            className="grid gap-4 py-10 pl-8 sm:grid-cols-[5rem_1fr]"
            style={{ marginLeft: `${i * 1.5}rem` }}
          >
            <span className="font-mono text-sm text-oxblood">{s.n}</span>
            <div>
              <h3 className="text-3xl tracking-tight sm:text-4xl">{s.title}</h3>
              <p className="mt-3 max-w-2xl text-lg leading-relaxed text-ink/70">{s.body}</p>
            </div>
          </RevealItem>
        ))}
      </RevealGroup>
    </div>
  );
}
