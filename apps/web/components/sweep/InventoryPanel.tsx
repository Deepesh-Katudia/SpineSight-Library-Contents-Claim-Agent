"use client";

import { useState } from "react";

import { identifiedFor, type InventoryState } from "@/hooks/useSweepEvents";
import type { TranscriptRole } from "@/lib/live-agent";

export interface TranscriptLine {
  role: TranscriptRole;
  text: string;
  at: number;
}

interface Props {
  inventory: InventoryState;
  transcript: TranscriptLine[];
}

type Tab = "books" | "items" | "room" | "talk";

export function InventoryPanel({ inventory, transcript }: Props) {
  const [tab, setTab] = useState<Tab>("books");
  const books = Object.values(inventory.books).sort((a, b) => a.shelf.localeCompare(b.shelf) || a.id.localeCompare(b.id));
  const items = Object.values(inventory.items);
  const walls = Object.values(inventory.walls).sort((a, b) => a.label.localeCompare(b.label));
  const tabs: [Tab, string][] = [
    ["books", `Books ${books.length}`],
    ["items", `Items ${items.length}`],
    ["room", `Walls ${walls.length}`],
    ["talk", "Transcript"],
  ];

  return (
    <section aria-label="Live inventory" className="flex min-h-0 flex-1 flex-col bg-ink-2">
      <div role="tablist" className="flex border-b border-ink-3">
        {tabs.map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={`label flex-1 px-2 py-3 transition-colors ${tab === key ? "border-b-2 border-signal text-paper" : "text-muted hover:text-paper"}`}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {tab === "books" && (
          <ul className="divide-y divide-ink-3">
            {books.length === 0 && <Empty text="Point the camera at a shelf. Spines appear here as they are detected." />}
            {books.map((b) => {
              const ident = identifiedFor(inventory, b);
              const legible = b.legibility >= 0.6 && b.title;
              return (
                <li key={b.id} className="grid grid-cols-[1fr_auto] gap-2 px-4 py-2.5">
                  <div className="min-w-0">
                    <p className="truncate text-[15px]">
                      {ident?.status === "identified" ? ident.title : legible ? b.title : <span className="text-warn">unreadable spine</span>}
                    </p>
                    <p className="truncate font-mono text-[11px] text-muted">
                      {b.shelf} · {ident?.status === "identified" ? `✓ ${ident.author}` : ident ? "no confident match" : legible ? "matching…" : "logged, not guessed"}
                    </p>
                  </div>
                  <span className="self-center font-mono text-[11px] tabular-nums text-paper/70">
                    {b.height_cm ? `${b.height_cm}×${b.thickness_cm ?? "?"} cm` : "no scale"}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
        {tab === "items" && (
          <ul className="divide-y divide-ink-3">
            {items.length === 0 && <Empty text="Furniture, lamps, art and electronics appear here." />}
            {items.map((i) => (
              <li key={i.id} className="px-4 py-2.5">
                <p className="text-[15px]">{i.description || i.category}</p>
                <p className="font-mono text-[11px] text-muted">
                  {i.category}
                  {i.brand_model ? ` · ${i.brand_model}` : ""}
                  {i.category === "portrait" || i.category === "framed_art" ? " · needs appraisal unless a print" : ""}
                </p>
              </li>
            ))}
          </ul>
        )}
        {tab === "room" && (
          <ul className="divide-y divide-ink-3">
            {walls.length === 0 && <Empty text="After the shelves the agent walks you around each wall." />}
            {walls.map((w) => (
              <li key={w.label} className="flex justify-between px-4 py-2.5 font-mono text-sm">
                <span>wall {w.label}</span>
                <span>
                  {w.width_m.toFixed(2)} × {w.height_m.toFixed(2)} m <span className="text-muted">· {w.method}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
        {tab === "talk" && (
          <ul className="space-y-2 px-4 py-3">
            {transcript.map((t, i) => (
              <li key={i} className={`text-sm leading-snug ${t.role === "agent" ? "text-paper" : t.role === "user" ? "text-brass" : "font-mono text-[11px] text-muted"}`}>
                <span className="label mr-2 text-muted">{t.role}</span>
                {t.text}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function Empty({ text }: { text: string }) {
  return <li className="px-4 py-8 text-center text-sm text-muted">{text}</li>;
}
