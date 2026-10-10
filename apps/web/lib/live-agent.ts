// ElevenLabs voice agent session: the SDK owns the microphone, playback and barge-in over WebRTC.
// We hand it a short-lived token from our API, run its client tools against the SpineSight API,
// and pass it capture hints from the vision pipeline. The agent hears the user but does not see
// the camera; [capture monitor] messages are how it learns what the camera is doing.

import { Conversation, type VoiceConversation } from "@elevenlabs/client";

import { api } from "./api";
import type { PacketSummary } from "./types";

export type TranscriptRole = "agent" | "user" | "system";

export interface LiveAgentHandlers {
  onTranscript: (role: TranscriptRole, text: string) => void;
  onTarget: (target: string) => void;
  onEndRequested: () => void;
  onStatus: (status: "connecting" | "live" | "closed" | "error", detail?: string) => void;
}

type ToolArgs = Record<string, unknown>;

const str = (v: unknown): string => (typeof v === "string" ? v : "");
const errorText = (err: unknown) => (err instanceof Error ? err.message : "tool failed");

export class LiveAgent {
  private session: VoiceConversation | null = null;
  private closedByUs = false;

  constructor(private sweepId: string, private handlers: LiveAgentHandlers) {}

  async connect(country: string, currency: string): Promise<void> {
    this.handlers.onStatus("connecting");
    const { token } = await api.liveToken();
    this.session = (await Conversation.startSession({
      conversationToken: token,
      connectionType: "webrtc",
      clientTools: this.clientTools(),
      onConnect: () => this.handlers.onStatus("live"),
      onMessage: ({ message, role }) => this.transcribe(role === "agent" ? "agent" : "user", message),
      onError: (message) => this.handlers.onStatus("error", message),
      onDisconnect: (details) => {
        this.session = null;
        if (this.closedByUs) this.handlers.onStatus("closed");
        else this.handlers.onStatus("error", details.reason === "error" ? details.message : "voice connection ended");
      },
    })) as VoiceConversation;
    // Context only: the agent's own first message is already greeting the user.
    this.session.sendContextualUpdate(
      `[session start] Default country ${country}, currency ${currency}. The camera is on.`,
    );
  }

  /** Text from the system (vision pipeline, packet). The agent decides how to voice it. */
  say(text: string): void {
    this.session?.sendUserMessage(text);
    this.handlers.onTranscript("system", text);
  }

  announcePacket(summary: PacketSummary): void {
    this.say(`[packet ready] ${JSON.stringify(summary)}. Read the summary back to the policyholder now.`);
  }

  async close(): Promise<void> {
    this.closedByUs = true;
    const session = this.session;
    this.session = null;
    await session?.endSession().catch(() => undefined);
  }

  private transcribe(role: "agent" | "user", text: string): void {
    const line = text.trim();
    if (!line) return;
    this.handlers.onTranscript(role, line);
    void api.transcript(this.sweepId, role, line).catch(() => undefined);
  }

  /** Names must match CLIENT_TOOLS in services/api/app/live.py (the agent's configuration). */
  private clientTools(): Record<string, (args: ToolArgs) => Promise<string>> {
    const run = (fn: (args: ToolArgs) => Promise<Record<string, unknown>>) => async (args: ToolArgs) => {
      try {
        return JSON.stringify(await fn(args ?? {}));
      } catch (err: unknown) {
        return JSON.stringify({ ok: false, error: errorText(err) });
      }
    };
    return {
      set_capture_target: run(async (args) => {
        const res = await api.setTarget(this.sweepId, str(args.target));
        this.handlers.onTarget(res.target);
        return { ok: true, target: res.target };
      }),
      record_user_fact: run(async (args) => {
        await api.addFact(this.sweepId, str(args.kind), str(args.text), str(args.ref_hint));
        return { ok: true };
      }),
      set_locale: run(async (args) => ({
        ok: true,
        ...(await api.setLocale(this.sweepId, str(args.country), str(args.currency))),
      })),
      get_inventory_status: run(() => api.status(this.sweepId)),
      end_sweep: run(async () => {
        this.handlers.onEndRequested();
        return { ok: true, note: "Packet is being assembled; wait for the [packet ready] message." };
      }),
    };
  }
}
