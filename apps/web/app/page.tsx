import Link from "next/link";

import { Hero } from "@/components/landing/Hero";
import { Reveal, RevealGroup, RevealItem } from "@/components/landing/motion/Reveal";
import { ScaleIn } from "@/components/landing/motion/ScaleIn";
import { ScrollProgress } from "@/components/landing/motion/ScrollProgress";
import { ScrollWords } from "@/components/landing/motion/ScrollWords";
import { StepsTimeline } from "@/components/landing/motion/StepsTimeline";

const STEPS = [
  {
    n: "01",
    title: "Talk, then walk.",
    body: "The agent greets you, confirms your country and currency, and asks you to place one A4 sheet on a shelf and on a wall. That sheet is the ruler.",
  },
  {
    n: "02",
    title: "It directs the sweep.",
    body: "Shelf by shelf, then wall by wall. It hears you, sees what you see, and says so the moment spines blur, glare out or go unread: “slow down”, “step closer to the second shelf”.",
  },
  {
    n: "03",
    title: "The packet assembles itself.",
    body: "Background agents finish identification, pricing and measurement. Within five minutes it reads back the totals and hands you a claim packet an adjuster can trace line by line.",
  },
];

const RULES = [
  ["rule 01", "No title is guessed.", "An unreadable spine is logged with its dimensions and sent to review. A blank beats a confident wrong answer."],
  ["rule 02", "No price without a URL.", "Every figure carries its source, retrieval date and assumed condition. Converted prices say so. Unpriceable lines are excluded, not invented."],
  ["rule 03", "Totals are summed in code.", "The language model never writes a number into the packet. Rare, signed, antiquarian and art go to a human appraiser."],
];

const PIPELINE = [
  ["Live agent", "Gemini Live", "voice + 1 fps video, directs the capture"],
  ["Detect", "Gemini 3.8 Flash", "spines, shelves, objects, A4 sheet, walls"],
  ["Read", "Gemini 3.8 Flash", "numbered spine crops, verbatim text only"],
  ["Track", "sequence alignment", "one physical book, counted once"],
  ["Measure", "OpenCV homography", "A4 → cm; chained across frames"],
  ["Identify", "Google Books · Open Library", "fuzzy match with abstention"],
  ["Price", "eBay Browse · Google Books · ECB FX", "replacement + used, sourced"],
  ["Packet", "deterministic Python", "totals, review queue, report"],
];

const PASS_BARS = [
  ["Book count", "within 5%"],
  ["Titles", "≥70% correct, ≤3% confidently wrong"],
  ["Spine dimensions", "within 15%"],
  ["Book prices", "within 25%"],
  ["Non-book items", "≥80% found"],
  ["Floor area", "within 10%"],
  ["Wall area", "within 15%"],
  ["Time to packet", "< 5 minutes"],
];

export default function Home() {
  return (
    <main className="flex-1">
      <ScrollProgress />
      <header className="sticky top-0 z-30 border-b border-ink-3/80 bg-ink/80 backdrop-blur">
        <nav aria-label="Main navigation" className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-8">
          <Link href="/" className="flex items-center gap-2 text-lg font-semibold tracking-tight">
            <span className="inline-block h-5 w-1.5 rounded-sm bg-signal" />
            SpineSight
          </Link>
          <Link
            href="/sweep"
            className="label rounded-sm bg-paper px-4 py-2 text-ink transition-transform duration-200 hover:-translate-y-0.5 hover:bg-signal active:translate-y-0"
          >
            Start a sweep
          </Link>
        </nav>
      </header>

      {/* HERO */}
      <Hero />

      {/* STEPS */}
      <section aria-labelledby="steps-heading" className="bg-paper text-ink" style={{ paddingBlock: "var(--space-section)" }}>
        <div className="mx-auto grid max-w-7xl gap-12 px-4 sm:px-8 lg:grid-cols-[0.8fr_2fr]">
          <Reveal className="lg:sticky lg:top-28 lg:self-start">
            <p className="label text-oxblood">The sweep</p>
            <h2 id="steps-heading" className="mt-3 text-5xl leading-[0.95] tracking-tight sm:text-7xl">
              One walk.
              <br />
              <span className="italic">Under three minutes.</span>
            </h2>
          </Reveal>
          <StepsTimeline steps={STEPS} />
        </div>
      </section>

      {/* RULES */}
      <section id="rules" aria-labelledby="rules-heading" className="grain relative bg-oxblood" style={{ paddingBlock: "var(--space-section)" }}>
        <div className="mx-auto max-w-7xl px-4 sm:px-8">
          <Reveal>
            <p className="label text-paper/60">Money is attached</p>
          </Reveal>
          <ScrollWords
            id="rules-heading"
            text="No number without evidence."
            className="mt-3 max-w-5xl text-6xl leading-[0.92] tracking-tight sm:text-8xl"
          />
          <RevealGroup className="mt-20 grid gap-10 md:grid-cols-3" stagger={0.14}>
            {RULES.map(([tag, title, body]) => (
              <RevealItem key={tag} as="article" className="group border-t-2 border-paper/80 pt-5">
                <p className="label text-brass">{tag}</p>
                <h3 className="mt-3 text-3xl italic leading-tight transition-transform duration-500 group-hover:translate-x-1">
                  {title}
                </h3>
                <p className="mt-4 leading-relaxed text-paper/75">{body}</p>
              </RevealItem>
            ))}
          </RevealGroup>
        </div>
      </section>

      {/* PIPELINE */}
      <section aria-labelledby="pipeline-heading" style={{ paddingBlock: "var(--space-section)" }}>
        <div className="mx-auto max-w-7xl px-4 sm:px-8">
          <Reveal className="flex flex-wrap items-end justify-between gap-6">
            <h2 id="pipeline-heading" className="max-w-2xl text-5xl leading-[0.95] tracking-tight sm:text-6xl">
              Eight stages. <span className="italic text-brass">Each one testable.</span>
            </h2>
            <p className="max-w-sm text-paper/60">
              Identification, pricing and measurement are separate steps with their own outputs, so every line traces
              back to a frame and a price source.
            </p>
          </Reveal>
          <RevealGroup
            as="ol"
            className="mt-14 grid gap-px overflow-hidden rounded-sm border border-ink-3 bg-ink-3 sm:grid-cols-2 lg:grid-cols-4"
            stagger={0.07}
          >
            {PIPELINE.map(([stage, tech, what], i) => (
              <RevealItem
                as="li"
                key={stage}
                className="group relative bg-ink-2 p-6 transition-colors duration-300 hover:bg-ink-3"
              >
                <span
                  aria-hidden
                  className="absolute inset-x-0 top-0 h-[2px] origin-left scale-x-0 bg-signal transition-transform duration-500 group-hover:scale-x-100"
                />
                <span className="font-mono text-xs text-muted">{String(i + 1).padStart(2, "0")}</span>
                <h3 className="mt-6 text-2xl tracking-tight transition-colors group-hover:text-signal">{stage}</h3>
                <p className="label mt-2 text-brass">{tech}</p>
                <p className="mt-3 text-sm leading-relaxed text-paper/60">{what}</p>
              </RevealItem>
            ))}
          </RevealGroup>
        </div>
      </section>

      {/* PASS BARS */}
      <section aria-labelledby="bars-heading" className="bg-paper-2 text-ink" style={{ paddingBlock: "var(--space-section)" }}>
        <div className="mx-auto grid max-w-7xl gap-12 px-4 sm:px-8 lg:grid-cols-[1fr_1.4fr]">
          <Reveal className="lg:sticky lg:top-28 lg:self-start">
            <p className="label text-oxblood">Measured against tape and receipts</p>
            <h2 id="bars-heading" className="mt-3 text-5xl leading-[0.95] tracking-tight">
              The bars it is held to.
            </h2>
            <p className="mt-6 max-w-md text-lg text-ink/70">
              Scored on hand-built ground truth: a true count, hand-read titles, tape-measured spines and room, and
              hand-checked prices. Misses are reported, not hidden.
            </p>
          </Reveal>
          <table className="w-full border-collapse text-left">
            <RevealGroup as="tbody" stagger={0.06}>
              {PASS_BARS.map(([m, bar]) => (
                <RevealItem as="tr" key={m} className="border-b border-rule">
                  <th scope="row" className="py-4 pr-4 text-xl font-normal">{m}</th>
                  <td className="py-4 text-right font-mono text-sm text-oxblood">{bar}</td>
                </RevealItem>
              ))}
            </RevealGroup>
          </table>
        </div>
      </section>

      {/* CTA */}
      <section className="grain relative overflow-hidden" style={{ paddingBlock: "var(--space-section)" }}>
        <div
          aria-hidden
          className="pointer-events-none absolute left-1/2 top-1/2 h-[520px] w-[820px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-signal/10 blur-[140px]"
        />
        <ScaleIn className="relative mx-auto max-w-7xl px-4 text-center sm:px-8">
          <h2 className="text-6xl leading-[0.92] tracking-tight sm:text-8xl">
            Open it on your phone.
            <br />
            <span className="italic text-signal">Start talking.</span>
          </h2>
          <Link
            href="/sweep"
            className="mt-10 inline-flex items-center gap-3 rounded-sm bg-paper px-8 py-4 text-lg text-ink transition-all hover:gap-5 hover:bg-signal"
          >
            Begin the sweep <span aria-hidden>→</span>
          </Link>
        </ScaleIn>
      </section>

      <footer className="border-t border-ink-3 px-4 py-8 sm:px-8">
        <div className="mx-auto flex max-w-7xl flex-wrap justify-between gap-4 text-sm text-muted">
          <span>SpineSight · contents claim agent</span>
          <span className="font-mono">Prices: eBay Browse · Google Books · ECB via Frankfurter</span>
        </div>
      </footer>
    </main>
  );
}
