"use client";

// Scroll-triggered entrances. A RevealGroup staggers its RevealItems as the group enters the
// viewport; a lone Reveal animates itself. Both render plain, fully visible markup when the
// viewer prefers reduced motion.

import { motion, useReducedMotion, type Variants } from "motion/react";
import type { ReactNode } from "react";

const EASE_OUT_EXPO = [0.16, 1, 0.3, 1] as const;
const VIEWPORT = { once: true, amount: 0.25 } as const;

const ITEM: Variants = {
  hidden: { opacity: 0, y: 36, filter: "blur(6px)" },
  shown: { opacity: 1, y: 0, filter: "blur(0px)", transition: { duration: 0.9, ease: EASE_OUT_EXPO } },
};

const GROUP_TAGS = { div: motion.div, ol: motion.ol, ul: motion.ul, tbody: motion.tbody, dl: motion.dl };
const ITEM_TAGS = { div: motion.div, li: motion.li, article: motion.article, tr: motion.tr, p: motion.p };

interface RevealProps {
  children: ReactNode;
  className?: string;
  delay?: number;
}

export function Reveal({ children, className, delay = 0 }: RevealProps) {
  const reduced = useReducedMotion();
  return (
    <motion.div
      className={className}
      variants={ITEM}
      initial={reduced ? false : "hidden"}
      whileInView="shown"
      viewport={VIEWPORT}
      transition={{ delay }}
    >
      {children}
    </motion.div>
  );
}

interface RevealGroupProps {
  children: ReactNode;
  className?: string;
  as?: keyof typeof GROUP_TAGS;
  stagger?: number;
}

export function RevealGroup({ children, className, as = "div", stagger = 0.09 }: RevealGroupProps) {
  const reduced = useReducedMotion();
  const Tag = GROUP_TAGS[as];
  return (
    <Tag
      className={className}
      initial={reduced ? false : "hidden"}
      whileInView="shown"
      viewport={VIEWPORT}
      variants={{ hidden: {}, shown: { transition: { staggerChildren: stagger } } }}
    >
      {children}
    </Tag>
  );
}

interface RevealItemProps {
  children: ReactNode;
  className?: string;
  as?: keyof typeof ITEM_TAGS;
  style?: React.CSSProperties;
}

export function RevealItem({ children, className, as = "div", style }: RevealItemProps) {
  const Tag = ITEM_TAGS[as];
  return (
    <Tag className={className} style={style} variants={ITEM}>
      {children}
    </Tag>
  );
}
