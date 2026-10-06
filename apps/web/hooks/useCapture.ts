"use client";

import { useCallback, useRef, useState } from "react";

import { api } from "@/lib/api";
import { bytesToBase64, MicCapture } from "@/lib/audio";
import { GLARE_MAX, grabJpeg, measureQuality, SHARPNESS_MIN, type FrameQuality } from "@/lib/keyframes";

const PROBE_MS = 250;
const KEYFRAME_MS = 700;
const LIVE_VIDEO_MS = 1000;
const MAX_INFLIGHT = 2;
const KEYFRAME_WIDTH = 1920;
const LIVE_WIDTH = 768;
const BAD_STREAK_FOR_HINT = 8; // ~2 s of consecutive blurry / glary probes
// Plain walls have little texture: only reject truly smeared frames there.
const WALL_SHARPNESS_MIN = SHARPNESS_MIN / 4;

function acceptable(q: FrameQuality, target: string): boolean {
  if (target.startsWith("wall:")) return q.sharpness >= WALL_SHARPNESS_MIN;
  return q.sharpness >= SHARPNESS_MIN && q.glare <= GLARE_MAX;
}

export interface CaptureCallbacks {
  onAudio: (pcm16Base64: string) => void;
  onLiveFrame: (jpegBase64: string) => void;
  onLocalHint: (text: string) => void;
  getTarget: () => string;
}

export interface CaptureStats {
  quality: FrameQuality;
  uploaded: number;
  skipped: number;
}

/** Owns camera + mic and the three loops: quality probe, keyframe upload, live video. */
export function useCapture(videoRef: React.RefObject<HTMLVideoElement | null>) {
  const [stats, setStats] = useState<CaptureStats>({ quality: { sharpness: 0, glare: 0 }, uploaded: 0, skipped: 0 });
  const streamRef = useRef<MediaStream | null>(null);
  const micRef = useRef<MicCapture | null>(null);
  const timers = useRef<number[]>([]);
  const pending = useRef<Set<Promise<unknown>>>(new Set());

  const start = useCallback(
    async (sweepId: string, cb: CaptureCallbacks, micCtx: AudioContext) => {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      streamRef.current = stream;
      const video = videoRef.current;
      if (!video) throw new Error("video element missing");
      video.srcObject = stream;
      video.muted = true;
      video.playsInline = true;
      await video.play();

      const mic = new MicCapture(micCtx);
      micRef.current = mic;
      await mic.start(new MediaStream(stream.getAudioTracks()), cb.onAudio);

      const probe = document.createElement("canvas");
      const grab = document.createElement("canvas");
      const live = document.createElement("canvas");
      const t0 = performance.now();
      let latest: FrameQuality = { sharpness: 0, glare: 0 };
      let badStreak = 0;
      let inflight = 0;

      const probeLoop = window.setInterval(() => {
        if (!video.videoWidth) return;
        latest = measureQuality(video, probe);
        const bad = !acceptable(latest, cb.getTarget());
        badStreak = bad ? badStreak + 1 : 0;
        if (badStreak === BAD_STREAK_FOR_HINT) {
          cb.onLocalHint(
            latest.glare > GLARE_MAX
              ? "[capture monitor] Strong glare in the camera image. Ask the user to tilt the phone or step out of the light."
              : "[capture monitor] The camera image is blurry. Ask the user to slow down and hold steady.",
          );
        }
        setStats((s) => ({ ...s, quality: latest }));
      }, PROBE_MS);

      const keyframeLoop = window.setInterval(async () => {
        if (!video.videoWidth || inflight >= MAX_INFLIGHT) return;
        const target = cb.getTarget();
        if (!acceptable(latest, target)) {
          setStats((s) => ({ ...s, skipped: s.skipped + 1 }));
          return;
        }
        inflight++;
        const job = (async () => {
          const tMs = performance.now() - t0;
          const blob = await grabJpeg(video, grab, KEYFRAME_WIDTH, 0.85);
          if (!blob) return;
          await api.uploadFrame(sweepId, blob, tMs, grab.width, grab.height, target);
          setStats((s) => ({ ...s, uploaded: s.uploaded + 1 }));
        })()
          .catch(() => setStats((s) => ({ ...s, skipped: s.skipped + 1 })))
          .finally(() => {
            inflight--;
            pending.current.delete(job);
          });
        pending.current.add(job);
      }, KEYFRAME_MS);

      const liveLoop = window.setInterval(async () => {
        if (!video.videoWidth) return;
        const blob = await grabJpeg(video, live, LIVE_WIDTH, 0.6);
        if (blob) cb.onLiveFrame(bytesToBase64(await blob.arrayBuffer()));
      }, LIVE_VIDEO_MS);

      timers.current = [probeLoop, keyframeLoop, liveLoop];
    },
    [videoRef],
  );

  const stop = useCallback(async () => {
    timers.current.forEach((t) => window.clearInterval(t));
    timers.current = [];
    // let in-flight keyframes land before the sweep is finalized
    await Promise.allSettled([...pending.current]);
    await micRef.current?.stop();
    micRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  return { start, stop, stats };
}
