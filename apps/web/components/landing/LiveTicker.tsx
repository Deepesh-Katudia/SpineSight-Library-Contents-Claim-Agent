"use client";

import { useEffect, useState } from "react";

const TICK_MS = 140;
const TARGET_BOOKS = 147;

/** Decorative counters under the hero, easing up to a demo total. */
export function LiveTicker() {
  const [n, setN] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => setN((v) => (v >= TARGET_BOOKS ? 0 : v + 1)), TICK_MS);
    return () => window.clearInterval(id);
  }, []);

  const identified = Math.floor(n * 0.82);
  const unidentified = n - identified;
  const run = (n * 0.031).toFixed(2);

  return (
    <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-sm border border-ink-3 bg-ink-3 sm:grid-cols-4">
      {[
        ["spines detected", String(n).padStart(3, "0")],
        ["identified", String(identified).padStart(3, "0")],
        ["logged, not guessed", String(unidentified).padStart(3, "0")],
        ["shelf run", `${run} m`],
      ].map(([label, value]) => (
        <div key={label} className="bg-ink-2 px-4 py-3">
          <dt className="label text-muted">{label}</dt>
          <dd className="mt-1 font-mono text-2xl tabular-nums text-paper">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
