// Gemini Live session: streams mic audio + 1 fps video, plays the agent's voice, executes its
// tool calls against the SpineSight API, and injects capture hints from the vision pipeline.
// Sweeps outlast a single Live connection, so the session uses context-window compression and
// session resumption, and transparently reconnects on goAway / unexpected close.

import { GoogleGenAI, Modality, type LiveServerMessage, type Session, type Tool } from "@google/genai";

import { api } from "./api";
import { PcmPlayer } from "./audio";
import type { LiveTokenResponse, PacketSummary } from "./types";

export type TranscriptRole = "agent" | "user" | "system";

export interface LiveAgentHandlers {
  onTranscript: (role: TranscriptRole, text: string) => void;
  onTarget: (target: string) => void;
  onEndRequested: () => void;
  onStatus: (status: "connecting" | "live" | "reconnecting" | "closed" | "error", detail?: string) => void;
}

type ToolArgs = Record<string, unknown>;

const MAX_RECONNECTS = 5;
const str = (v: unknown): string => (typeof v === "string" ? v : "");

export class LiveAgent {
  private session: Session | null = null;
  private player: PcmPlayer;
  private agentLine = "";
  private userLine = "";
  private resumeHandle: string | undefined;
  private closedByUs = false;
  private reconnecting = false;
  private reconnects = 0;

  constructor(private sweepId: string, private handlers: LiveAgentHandlers, playbackCtx: AudioContext) {
    this.player = new PcmPlayer(playbackCtx);
  }

  async connect(): Promise<void> {
    this.handlers.onStatus("connecting");
    await this.player.init();
    await this.open();
    this.say("[session start] The policyholder has opened the app with the camera on. Greet them now.");
  }

  private async open(): Promise<void> {
    const cfg: LiveTokenResponse = await api.liveToken();
    const ai = new GoogleGenAI({ apiKey: cfg.token, httpOptions: { apiVersion: "v1alpha" } });
    this.session = await ai.live.connect({
      model: cfg.model,
      config: {
        responseModalities: [Modality.AUDIO],
        systemInstruction: cfg.instructions,
        tools: cfg.tools as Tool[],
        inputAudioTranscription: {},
        outputAudioTranscription: {},
        contextWindowCompression: { slidingWindow: {} },
        sessionResumption: { handle: this.resumeHandle },
      },
      callbacks: {
        onopen: () => this.handlers.onStatus("live"),
        onmessage: (m) => void this.onMessage(m),
        onerror: (e) => this.handlers.onStatus("error", e.message),
        onclose: () => {
          this.session = null;
          if (!this.closedByUs) void this.reconnect();
          else this.handlers.onStatus("closed");
        },
      },
    });
  }

  private async reconnect(): Promise<void> {
    if (this.reconnecting || this.closedByUs) return;
    if (this.reconnects >= MAX_RECONNECTS) {
      this.handlers.onStatus("error", "voice connection lost");
      return;
    }
    this.reconnecting = true;
    this.reconnects++;
    this.handlers.onStatus("reconnecting");
    const old = this.session;
    this.session = null;
    try {
      old?.close();
    } catch {
      /* already closed */
    }
    try {
      await this.open();
    } catch (err: unknown) {
      this.handlers.onStatus("error", err instanceof Error ? err.message : "reconnect failed");
    } finally {
      this.reconnecting = false;
    }
  }

  private send(fn: (s: Session) => void): void {
    if (!this.session) return;
    try {
      fn(this.session);
    } catch {
      void this.reconnect();
    }
  }

  sendAudio(pcm16Base64: string): void {
    this.send((s) => s.sendRealtimeInput({ audio: { data: pcm16Base64, mimeType: "audio/pcm;rate=16000" } }));
  }

  sendVideoFrame(jpegBase64: string): void {
    this.send((s) => s.sendRealtimeInput({ video: { data: jpegBase64, mimeType: "image/jpeg" } }));
  }

  /** Text from the system (vision pipeline, packet). The agent decides how to voice it. */
  say(text: string): void {
    this.send((s) => s.sendClientContent({ turns: [{ role: "user", parts: [{ text }] }], turnComplete: true }));
    this.handlers.onTranscript("system", text);
  }

  announcePacket(summary: PacketSummary): void {
    this.say(`[packet ready] ${JSON.stringify(summary)}. Read the summary back to the policyholder now.`);
  }

  async close(): Promise<void> {
    this.closedByUs = true;
    try {
      this.session?.close();
    } catch {
      /* already closed */
    }
    this.session = null;
    await this.player.close();
  }

  private flushLine(role: "agent" | "user"): void {
    const line = role === "agent" ? this.agentLine : this.userLine;
    if (!line.trim()) return;
    this.handlers.onTranscript(role, line.trim());
    void api.transcript(this.sweepId, role, line.trim()).catch(() => undefined);
    if (role === "agent") this.agentLine = "";
    else this.userLine = "";
  }

  private async onMessage(msg: LiveServerMessage): Promise<void> {
    if (msg.sessionResumptionUpdate?.resumable && msg.sessionResumptionUpdate.newHandle) {
      this.resumeHandle = msg.sessionResumptionUpdate.newHandle;
    }
    if (msg.goAway) {
      void this.reconnect();
      return;
    }
    const content = msg.serverContent;
    if (content?.interrupted) this.player.interrupt();
    for (const part of content?.modelTurn?.parts ?? []) {
      if (part.inlineData?.data) this.player.play(part.inlineData.data);
    }
    if (content?.inputTranscription?.text) this.userLine += content.inputTranscription.text;
    if (content?.outputTranscription?.text) {
      this.flushLine("user");
      this.agentLine += content.outputTranscription.text;
    }
    if (content?.turnComplete) {
      this.flushLine("user");
      this.flushLine("agent");
    }
    if (msg.toolCall?.functionCalls?.length) {
      const responses = await Promise.all(
        msg.toolCall.functionCalls.map(async (fc) => ({
          id: fc.id,
          name: fc.name,
          response: await this.runTool(fc.name ?? "", (fc.args ?? {}) as ToolArgs),
        })),
      );
      this.send((s) => s.sendToolResponse({ functionResponses: responses }));
    }
  }

  private async runTool(name: string, args: ToolArgs): Promise<Record<string, unknown>> {
    try {
      switch (name) {
        case "set_capture_target": {
          const res = await api.setTarget(this.sweepId, str(args.target));
          this.handlers.onTarget(res.target);
          return { ok: true, target: res.target };
        }
        case "record_user_fact":
          await api.addFact(this.sweepId, str(args.kind), str(args.text), str(args.ref_hint));
          return { ok: true };
        case "set_locale":
          return { ok: true, ...(await api.setLocale(this.sweepId, str(args.country), str(args.currency))) };
        case "get_inventory_status":
          return await api.status(this.sweepId);
        case "end_sweep":
          this.handlers.onEndRequested();
          return { ok: true, note: "Packet is being assembled; wait for the [packet ready] message." };
        default:
          return { ok: false, error: `unknown tool ${name}` };
      }
    } catch (err: unknown) {
      return { ok: false, error: err instanceof Error ? err.message : "tool failed" };
    }
  }
}
