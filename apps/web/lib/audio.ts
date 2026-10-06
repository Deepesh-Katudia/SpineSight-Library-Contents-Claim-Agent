// Microphone -> 16 kHz PCM16 chunks (Gemini Live input), and 24 kHz PCM16 playback with barge-in.
// iOS Safari runs AudioContext at 44.1/48 kHz, so the worklet resamples.

const CAPTURE_WORKLET = `
class Pcm16Capture extends AudioWorkletProcessor {
  constructor() { super(); this.ratio = sampleRate / 16000; this.acc = []; this.pos = 0; }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    for (let i = 0; i < ch.length; i++) this.acc.push(ch[i]);
    const out = [];
    // box-filter each decimation window (cheap anti-alias low-pass), then take one sample
    while (this.pos + this.ratio <= this.acc.length) {
      const a = Math.floor(this.pos), b = Math.max(a + 1, Math.floor(this.pos + this.ratio));
      let sum = 0;
      for (let k = a; k < b; k++) sum += this.acc[k];
      const s = Math.max(-1, Math.min(1, sum / (b - a)));
      out.push(s < 0 ? s * 0x8000 : s * 0x7fff);
      this.pos += this.ratio;
    }
    const used = Math.floor(this.pos);
    this.acc = this.acc.slice(used); this.pos -= used;
    if (out.length) this.port.postMessage(Int16Array.from(out).buffer, []);
    return true;
  }
}
registerProcessor("pcm16-capture", Pcm16Capture);
`;

export function bytesToBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

export function base64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

const RESUME_TIMEOUT_MS = 3000;

/** iOS Safari: an AudioContext must be created and resumed inside the user's tap, before any await. */
export function primeContext(): AudioContext {
  const ctx = new AudioContext();
  void ctx.resume().catch(() => undefined);
  return ctx;
}

async function ensureRunning(ctx: AudioContext): Promise<void> {
  if (ctx.state === "running") return;
  await Promise.race([
    ctx.resume(),
    new Promise((_, reject) => setTimeout(() => reject(new Error("audio blocked: tap Start again")), RESUME_TIMEOUT_MS)),
  ]);
}

export class MicCapture {
  private node: AudioWorkletNode | null = null;
  private sink: GainNode | null = null;

  constructor(private ctx: AudioContext) {}

  async start(stream: MediaStream, onChunk: (pcm16Base64: string) => void): Promise<void> {
    await ensureRunning(this.ctx);
    const url = URL.createObjectURL(new Blob([CAPTURE_WORKLET], { type: "application/javascript" }));
    try {
      await this.ctx.audioWorklet.addModule(url);
    } finally {
      URL.revokeObjectURL(url);
    }
    const source = this.ctx.createMediaStreamSource(stream);
    this.node = new AudioWorkletNode(this.ctx, "pcm16-capture");
    this.node.port.onmessage = (e: MessageEvent<ArrayBuffer>) => onChunk(bytesToBase64(e.data));
    // Safari only pulls process() on nodes connected to the destination: route through a muted gain.
    this.sink = this.ctx.createGain();
    this.sink.gain.value = 0;
    source.connect(this.node);
    this.node.connect(this.sink);
    this.sink.connect(this.ctx.destination);
  }

  async stop(): Promise<void> {
    this.node?.disconnect();
    this.sink?.disconnect();
    this.node = null;
    this.sink = null;
    if (this.ctx.state !== "closed") await this.ctx.close();
  }
}

export class PcmPlayer {
  private nextAt = 0;
  private sources = new Set<AudioBufferSourceNode>();

  constructor(private ctx: AudioContext | null) {}

  async init(): Promise<void> {
    if (this.ctx) await ensureRunning(this.ctx);
  }

  get speaking(): boolean {
    return this.sources.size > 0;
  }

  play(pcm16Base64: string, sampleRate = 24000): void {
    if (!this.ctx) return;
    const bytes = base64ToBytes(pcm16Base64);
    const samples = new Int16Array(bytes.buffer, bytes.byteOffset, Math.floor(bytes.byteLength / 2));
    const buffer = this.ctx.createBuffer(1, samples.length, sampleRate);
    const ch = buffer.getChannelData(0);
    for (let i = 0; i < samples.length; i++) ch[i] = samples[i] / 0x8000;
    const src = this.ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(this.ctx.destination);
    const startAt = Math.max(this.ctx.currentTime + 0.02, this.nextAt);
    src.start(startAt);
    this.nextAt = startAt + buffer.duration;
    this.sources.add(src);
    src.onended = () => this.sources.delete(src);
  }

  /** User barged in: drop everything queued. */
  interrupt(): void {
    for (const s of this.sources) {
      try {
        s.stop();
      } catch {
        /* already stopped */
      }
    }
    this.sources.clear();
    this.nextAt = 0;
  }

  async close(): Promise<void> {
    this.interrupt();
    if (this.ctx && this.ctx.state !== "closed") await this.ctx.close();
    this.ctx = null;
  }
}
