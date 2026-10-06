import type { ClaimPacket, LiveTokenResponse, PacketSummary } from "./types";

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: unknown };
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  liveToken: () => request<LiveTokenResponse>("/live/token", { method: "POST" }),
  createSweep: (device: string) =>
    request<{ id: string; country: string; currency: string }>("/sweeps", json({ device })),
  setTarget: (id: string, target: string) => request<{ target: string }>(`/sweeps/${id}/target`, json({ target })),
  addFact: (id: string, kind: string, text: string, refHint = "") =>
    request<{ recorded: boolean }>(`/sweeps/${id}/facts`, json({ kind, text, ref_hint: refHint })),
  setLocale: (id: string, country: string, currency: string) =>
    request<{ country: string; currency: string }>(`/sweeps/${id}/locale`, json({ country, currency })),
  status: (id: string) => request<Record<string, unknown>>(`/sweeps/${id}/status`),
  transcript: (id: string, role: string, text: string) =>
    request<{ ok: boolean }>(`/sweeps/${id}/transcript`, json({ role, text })),
  finish: (id: string) => request<PacketSummary>(`/sweeps/${id}/finish`, { method: "POST" }),
  packet: (id: string) => request<ClaimPacket>(`/sweeps/${id}/packet`, { cache: "no-store" }),
  uploadFrame: (id: string, blob: Blob, tMs: number, width: number, height: number, target: string) => {
    const form = new FormData();
    form.append("file", blob, `${tMs}.jpg`);
    form.append("t_ms", String(Math.round(tMs)));
    form.append("width", String(width));
    form.append("height", String(height));
    form.append("target", target);
    return request<{ frame_ref: string | null; queued: boolean }>(`/sweeps/${id}/frames`, { method: "POST", body: form });
  },
  eventsUrl: (id: string) => `${API_BASE}/sweeps/${id}/events`,
  reportUrl: (id: string) => `${API_BASE}/sweeps/${id}/report`,
  packetUrl: (id: string) => `${API_BASE}/sweeps/${id}/packet`,
  frameUrl: (ref: string) => `${API_BASE}/frames/${ref}`,
};
