"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { useCapture } from "@/hooks/useCapture";
import { useSweepEvents, type Hint } from "@/hooks/useSweepEvents";
import { api } from "@/lib/api";
import { primeContext } from "@/lib/audio";
import { SHARPNESS_MIN } from "@/lib/keyframes";
import { LiveAgent, type TranscriptRole } from "@/lib/live-agent";
import type { PacketSummary } from "@/lib/types";

import { InventoryPanel, type TranscriptLine } from "./InventoryPanel";

const HINT_VISIBLE_MS = 6000;

type Phase = "idle" | "starting" | "live" | "finishing" | "done" | "error";

const errorText = (err: unknown) => (err instanceof Error ? err.message : "Something went wrong");

export function SweepConsole() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const agentRef = useRef<LiveAgent | null>(null);
  const targetRef = useRef("");
  const finishingRef = useRef(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState("");
  const [sweepId, setSweepId] = useState<string | null>(null);
  const [target, setTarget] = useState("");
  const [agentStatus, setAgentStatus] = useState("offline");
  const [transcript, setTranscript] = useState<TranscriptLine[]>([]);
  const [summary, setSummary] = useState<PacketSummary | null>(null);
  const [startedAt, setStartedAt] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const { start: startCapture, stop: stopCapture, stats } = useCapture(videoRef);

  const pushLine = useCallback((role: TranscriptRole, text: string) => {
    setTranscript((t) => [...t.slice(-80), { role, text, at: Date.now() }]);
  }, []);

  const onHint = useCallback((hint: Hint) => agentRef.current?.say(`[capture monitor] ${hint.text}`), []);
  const inventory = useSweepEvents(sweepId, onHint);

  const [hintVisible, setHintVisible] = useState(false);
  useEffect(() => {
    if (!inventory.lastHint) return;
    const show = window.setTimeout(() => setHintVisible(true), 0);
    const hide = window.setTimeout(() => setHintVisible(false), HINT_VISIBLE_MS);
    return () => {
      window.clearTimeout(show);
      window.clearTimeout(hide);
    };
  }, [inventory.lastHint]);

  useEffect(() => {
    if (phase !== "live") return;
    const id = window.setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => window.clearInterval(id);
  }, [phase, startedAt]);

  const finish = useCallback(async () => {
    if (!sweepId || finishingRef.current) return;
    finishingRef.current = true;
    setPhase("finishing");
    await stopCapture();
    try {
      const result = await api.finish(sweepId);
      setSummary(result);
      agentRef.current?.announcePacket(result);
      setPhase("done");
    } catch (err: unknown) {
      finishingRef.current = false; // allow "Retry packet" on the same sweep
      setError(errorText(err));
      setPhase("error");
    }
  }, [sweepId, stopCapture]);

  // end_sweep tool call arrives inside the agent; route it through the same finish path
  const finishRef = useRef(finish);
  useEffect(() => {
    finishRef.current = finish;
  }, [finish]);

  const start = useCallback(async () => {
    // iOS: audio contexts must be created synchronously inside the tap, before any await
    const playbackCtx = primeContext();
    const micCtx = primeContext();
    setPhase("starting");
    setError("");
    try {
      const sweep = await api.createSweep(navigator.userAgent.slice(0, 180));
      setSweepId(sweep.id);
      const agent = new LiveAgent(sweep.id, {
        onTranscript: pushLine,
        onTarget: (t) => {
          targetRef.current = t;
          setTarget(t);
        },
        onEndRequested: () => void finishRef.current(),
        onStatus: (s, detail) => setAgentStatus(detail ? `${s}: ${detail}` : s),
      }, playbackCtx);
      agentRef.current = agent;
      await agent.connect();
      await startCapture(sweep.id, {
        onAudio: (pcm) => agent.sendAudio(pcm),
        onLiveFrame: (jpeg) => agent.sendVideoFrame(jpeg),
        onLocalHint: (text) => agent.say(text),
        getTarget: () => targetRef.current,
      }, micCtx);
      setStartedAt(Date.now());
      setPhase("live");
    } catch (err: unknown) {
      setError(errorText(err));
      setPhase("error");
      await stopCapture();
      await agentRef.current?.close();
      agentRef.current = null;
      if (micCtx.state !== "closed") await micCtx.close();
      if (playbackCtx.state !== "closed") await playbackCtx.close();
    }
  }, [startCapture, stopCapture, pushLine]);

  useEffect(() => {
    return () => {
      void agentRef.current?.close();
      void stopCapture();
    };
  }, [stopCapture]);

  const sharp = stats.quality.sharpness >= SHARPNESS_MIN;
  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");

  return (
    <main className="flex h-[100dvh] flex-col overflow-hidden bg-ink lg:flex-row">
      <div className="relative min-h-0 flex-[1.2] bg-black lg:flex-[2]">
        <video ref={videoRef} className="absolute inset-0 h-full w-full object-cover" playsInline muted />

        {/* HUD */}
        <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between gap-2 bg-gradient-to-b from-black/70 to-transparent p-3">
          <Link href="/" className="pointer-events-auto flex items-center gap-2 text-sm font-semibold">
            <span className="inline-block h-4 w-1 rounded-sm bg-signal" /> SpineSight
          </Link>
          <div className="flex flex-col items-end gap-1.5">
            {phase === "live" && (
              <span className="label flex items-center gap-2 rounded-sm bg-black/60 px-2 py-1 text-signal">
                <span className="live-dot h-1.5 w-1.5 rounded-full bg-signal" /> rec {mm}:{ss}
              </span>
            )}
            <span className="label rounded-sm bg-black/60 px-2 py-1 text-paper/80">agent · {agentStatus}</span>
            {target && <span className="label rounded-sm bg-paper px-2 py-1 text-ink">capturing {target.replace(":", " ")}</span>}
          </div>
        </div>

        {phase === "live" && (
          <div className="pointer-events-none absolute inset-x-0 bottom-0 flex flex-wrap items-end justify-between gap-2 bg-gradient-to-t from-black/80 to-transparent p-3">
            <div className="flex gap-2">
              <Chip ok={sharp} label={sharp ? "sharp" : "blurry"} />
              <Chip ok={stats.quality.glare < 0.08} label={stats.quality.glare < 0.08 ? "no glare" : "glare"} />
              <Chip ok label={`${stats.uploaded} frames`} />
            </div>
            {inventory.lastHint && hintVisible && (
              <p className="max-w-xs rounded-sm bg-warn px-3 py-2 text-sm text-ink">{inventory.lastHint.text}</p>
            )}
          </div>
        )}

        {(phase === "idle" || phase === "error" || phase === "starting") && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-6 bg-ink/90 p-6 text-center">
            <h1 className="max-w-md text-4xl leading-tight tracking-tight">
              Ready when you are. <span className="italic text-brass">Put an A4 sheet on a shelf.</span>
            </h1>
            <p className="max-w-sm text-paper/70">
              Allow camera and microphone. The agent will talk you through the room. You can interrupt and correct it at any time.
            </p>
            <button
              onClick={start}
              disabled={phase === "starting"}
              className="rounded-sm bg-signal px-8 py-4 text-lg text-ink transition-all hover:shadow-[0_0_40px_-6px_rgba(255,107,44,0.7)] disabled:opacity-60"
            >
              {phase === "starting" ? "Connecting…" : "Start sweep"}
            </button>
            {error && <p role="alert" className="max-w-sm font-mono text-sm text-warn">{error}</p>}
            {phase === "error" && startedAt > 0 && sweepId && (
              <button onClick={finish} className="label rounded-sm border border-paper/40 px-6 py-3 text-paper hover:border-signal">
                Retry building the packet for sweep {sweepId}
              </button>
            )}
          </div>
        )}

        {(phase === "finishing" || phase === "done") && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-ink/92 p-6 text-center">
            {phase === "finishing" ? (
              <>
                <span className="live-dot h-3 w-3 rounded-full bg-signal" />
                <h2 className="text-3xl tracking-tight">Assembling the claim packet…</h2>
                <p className="font-mono text-sm text-muted">identification · pricing · room geometry · totals</p>
              </>
            ) : (
              summary && <PacketCard summary={summary} />
            )}
          </div>
        )}
      </div>

      <aside className="flex min-h-0 flex-1 flex-col border-t border-ink-3 lg:max-w-md lg:border-l lg:border-t-0">
        <InventoryPanel inventory={inventory} transcript={transcript} />
        {phase === "live" && (
          <button onClick={finish} className="label m-3 rounded-sm border border-paper/30 py-3 text-paper transition-colors hover:border-signal hover:text-signal">
            End sweep &amp; build packet
          </button>
        )}
      </aside>
    </main>
  );
}

function Chip({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={`label rounded-sm px-2 py-1 ${ok ? "bg-black/60 text-paper/80" : "bg-warn text-ink"}`}>{label}</span>
  );
}

function PacketCard({ summary: s }: { summary: PacketSummary }) {
  const money = (v: number) => `${s.currency} ${Math.round(v).toLocaleString()}`;
  return (
    <div className="w-full max-w-md text-left">
      <p className="label text-signal">Packet ready · {s.time_to_packet_s ?? "?"} s after sweep</p>
      <h2 className="mt-2 text-4xl tracking-tight">{s.book_count} books logged</h2>
      <dl className="mt-6 grid grid-cols-2 gap-px overflow-hidden rounded-sm bg-ink-3">
        {[
          ["identified", String(s.books_identified)],
          ["unidentified", String(s.books_unidentified)],
          ["appraisal", String(s.books_needs_appraisal)],
          ["review queue", String(s.review_queue)],
          ["books replacement", money(s.books_replacement_cost)],
          ["books used", money(s.books_used_value)],
          ["other contents", `${money(s.items_low)}–${Math.round(s.items_high).toLocaleString()}`],
          ["floor area", s.floor_area_m2 ? `${s.floor_area_m2} m²` : "not measured"],
        ].map(([k, v]) => (
          <div key={k} className="bg-ink-2 px-3 py-2.5">
            <dt className="label text-muted">{k}</dt>
            <dd className="mt-0.5 font-mono text-base">{v}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-6 flex gap-3">
        <Link href={`/claims/${s.sweep_id}`} className="flex-1 rounded-sm bg-paper py-3 text-center text-ink hover:bg-signal">
          Open claim packet
        </Link>
        <a href={api.packetUrl(s.sweep_id)} className="label flex items-center rounded-sm border border-paper/30 px-4">
          JSON
        </a>
      </div>
    </div>
  );
}
