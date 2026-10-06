import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import type { Book, ClaimPacket, PriceQuote } from "@/lib/types";

const PUBLIC_API = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const SERVER_API = (process.env.API_BASE_URL ?? PUBLIC_API).replace(/\/$/, "");

export const metadata: Metadata = { title: "Claim packet — SpineSight" };

/** Third-party URLs from price sources: only http(s) is ever rendered as a link. */
function safeHref(url: string): string | undefined {
  try {
    const { protocol } = new URL(url);
    return protocol === "http:" || protocol === "https:" ? url : undefined;
  } catch {
    return undefined;
  }
}

async function loadPacket(id: string): Promise<ClaimPacket | null> {
  if (!/^[a-f0-9]{12}$/.test(id)) return null;
  const res = await fetch(`${SERVER_API}/sweeps/${id}/packet`, { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`API returned ${res.status}`);
  return (await res.json()) as ClaimPacket;
}

export default function ClaimPage({ params }: PageProps<"/claims/[id]">) {
  return (
    <Suspense
      fallback={
        <main className="flex flex-1 items-center justify-center bg-paper text-ink">
          <p className="label text-muted">Loading claim packet…</p>
        </main>
      }
    >
      <ClaimPacketView params={params} />
    </Suspense>
  );
}

async function ClaimPacketView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const packet = await loadPacket(id);
  if (!packet) notFound();
  const { totals: t, room: r, sweep } = packet;
  const money = (v: number | null | undefined) => (v == null ? "—" : `${t.currency} ${Math.round(v).toLocaleString()}`);
  const m = (v: number | null, unit: string) => (v == null ? "—" : `${v.toFixed(2)} ${unit}`);

  return (
    <main className="flex-1 bg-paper text-ink">
      <header className="border-b border-rule">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-4 sm:px-8">
          <Link href="/" className="flex items-center gap-2 font-semibold">
            <span className="inline-block h-4 w-1 rounded-sm bg-signal" /> SpineSight
          </Link>
          <div className="flex gap-2">
            <a href={`${PUBLIC_API}/sweeps/${id}/report`} className="label rounded-sm bg-ink px-3 py-2 text-paper hover:bg-oxblood">
              Printable report
            </a>
            <a href={`${PUBLIC_API}/sweeps/${id}/packet`} className="label rounded-sm border border-ink/30 px-3 py-2 hover:border-ink">
              claim_packet.json
            </a>
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-7xl px-4 py-12 sm:px-8">
        <p className="label text-oxblood">
          Sweep {sweep.id} · {new Date(sweep.captured_at).toLocaleString()} · {sweep.duration_s}s · {sweep.country}/{sweep.currency}
        </p>
        <h1 className="mt-3 text-5xl leading-[0.95] tracking-tight sm:text-6xl">
          {t.book_count} books, <span className="italic">{packet.items.length} other items</span>
        </h1>

        <dl className="mt-10 grid grid-cols-2 gap-px overflow-hidden rounded-sm border border-rule bg-rule md:grid-cols-4">
          {[
            ["Books replacement", money(t.books_replacement_cost)],
            ["Books used value", money(t.books_used_value)],
            ["Other contents", `${money(t.items_replacement_cost_low)} – ${Math.round(t.items_replacement_cost_high).toLocaleString()}`],
            ["Excluded from totals", `${t.excluded_from_totals} lines`],
            ["Identified / unidentified", `${t.books_identified} / ${t.books_unidentified}`],
            ["Needs appraisal", String(t.books_needs_appraisal)],
            ["Shelf run", `${t.shelf_run_m.toFixed(2)} m`],
            ["Review queue", `${packet.review_queue.length} entries`],
          ].map(([k, v]) => (
            <div key={k} className="bg-paper px-4 py-4">
              <dt className="label text-muted">{k}</dt>
              <dd className="mt-1 font-mono text-lg tabular-nums">{v}</dd>
            </div>
          ))}
        </dl>

        <h2 className="mt-16 border-b-2 border-ink pb-2 text-2xl">Room</h2>
        <div className="mt-4 grid gap-6 font-mono text-sm sm:grid-cols-3">
          <p>L × W × H: {m(r.length_m, "m")} × {m(r.width_m, "m")} × {m(r.height_m, "m")}</p>
          <p>Floor {m(r.floor_area_m2, "m²")} ({m(r.floor_area_ft2, "ft²")}) · walls {m(r.wall_area_m2, "m²")} · shelved {m(r.shelved_wall_area_m2, "m²")}</p>
          <p>{r.shape || "shape unknown"} · scale: {r.scale_method || "none"} · confidence {r.confidence.toFixed(2)}</p>
        </div>

        <h2 className="mt-16 border-b-2 border-ink pb-2 text-2xl">Books</h2>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[820px] text-sm">
            <thead>
              <tr className="label text-left text-muted">
                <th className="py-2">Shelf</th><th>Title</th><th>H × T cm</th><th>Replacement</th><th>Used</th><th>Evidence</th>
              </tr>
            </thead>
            <tbody>
              {packet.books.map((b) => (
                <BookRow key={b.id} b={b} />
              ))}
            </tbody>
          </table>
        </div>

        <h2 className="mt-16 border-b-2 border-ink pb-2 text-2xl">Review queue</h2>
        <ul className="mt-2 divide-y divide-rule text-sm">
          {packet.review_queue.map((q, i) => (
            <li key={i} className="grid grid-cols-[6rem_1fr] gap-4 py-2">
              <span className="font-mono text-oxblood">{q.ref_id}</span>
              <span>{q.reason}</span>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}

function priceCell(q: PriceQuote) {
  if (q.amount == null) return <span className="text-muted">—</span>;
  return (
    <a href={safeHref(q.url)} target="_blank" rel="noopener noreferrer" className="group block">
      <span className="font-mono tabular-nums">{q.currency} {Math.round(q.amount).toLocaleString()}</span>
      {q.converted && <span className="ml-1 text-[11px] text-warn">conv.</span>}
      <span className="block max-w-[14rem] truncate text-[11px] text-muted group-hover:text-oxblood">{q.source}</span>
    </a>
  );
}

function BookRow({ b }: { b: Book }) {
  return (
    <tr className={`border-b border-rule align-top ${b.excluded ? "opacity-50" : ""}`}>
      <td className="py-2 font-mono text-xs">{b.shelf}·{b.position}</td>
      <td className="py-2 pr-4">
        {b.title ? (
          <>
            <span className="font-medium">{b.title}</span>
            <span className="block text-xs text-muted">{b.author}{b.edition ? ` · ${b.edition}` : ""}</span>
          </>
        ) : (
          <span className="text-muted">Unidentified — “{b.spine_text_raw || "unreadable"}”</span>
        )}
        {b.status === "needs_appraisal" && <span className="label mt-1 block text-oxblood">needs appraisal · {b.appraisal_reason}</span>}
      </td>
      <td className="py-2 font-mono text-xs">{b.spine_height_cm ?? "—"} × {b.spine_thickness_cm ?? "—"}</td>
      <td className="py-2">{priceCell(b.replacement_cost)}</td>
      <td className="py-2">{priceCell(b.used_value)}</td>
      <td className="py-2">
        {b.frame_ref && (
          <a className="font-mono text-xs text-oxblood underline" href={`${PUBLIC_API}/frames/${b.frame_ref}`}>
            frame
          </a>
        )}
      </td>
    </tr>
  );
}
