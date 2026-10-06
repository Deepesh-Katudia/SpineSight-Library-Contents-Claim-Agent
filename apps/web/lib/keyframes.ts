// Client-side capture quality: sharpness (variance of Laplacian) and glare (blown-out pixels),
// computed on a small grayscale copy so it runs every frame on a phone.

export interface FrameQuality {
  sharpness: number;
  glare: number;
}

export const SHARPNESS_MIN = 60;
export const GLARE_MAX = 0.08;
const PROBE_WIDTH = 240;

export function measureQuality(video: HTMLVideoElement, probe: HTMLCanvasElement): FrameQuality {
  const scale = PROBE_WIDTH / video.videoWidth;
  const w = PROBE_WIDTH;
  const h = Math.max(1, Math.round(video.videoHeight * scale));
  probe.width = w;
  probe.height = h;
  const ctx = probe.getContext("2d", { willReadFrequently: true });
  if (!ctx) return { sharpness: 0, glare: 0 };
  ctx.drawImage(video, 0, 0, w, h);
  const { data } = ctx.getImageData(0, 0, w, h);
  const gray = new Float32Array(w * h);
  let blown = 0;
  for (let i = 0, p = 0; i < data.length; i += 4, p++) {
    const g = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
    gray[p] = g;
    if (g > 250) blown++;
  }
  let sum = 0;
  let sumSq = 0;
  let n = 0;
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const i = y * w + x;
      const lap = 4 * gray[i] - gray[i - 1] - gray[i + 1] - gray[i - w] - gray[i + w];
      sum += lap;
      sumSq += lap * lap;
      n++;
    }
  }
  const mean = sum / n;
  return { sharpness: sumSq / n - mean * mean, glare: blown / (w * h) };
}

export function grabJpeg(video: HTMLVideoElement, canvas: HTMLCanvasElement, maxWidth: number, quality: number): Promise<Blob | null> {
  const scale = Math.min(1, maxWidth / video.videoWidth);
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext("2d")?.drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
}
