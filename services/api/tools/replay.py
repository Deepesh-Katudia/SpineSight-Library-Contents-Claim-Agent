"""Replay a recorded sweep video through the running API (for tuning and regression, not the demo).

    python tools/replay.py sweep.mp4 --targets "0:shelf:A,45:shelf:B,95:wall:1,110:wall:2,125:wall:3,140:wall:4"

Samples sharp frames at --fps, tags each with the capture target active at that time, uploads them,
then calls /finish and prints the packet summary. The live voice agent is not involved.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import cv2
import httpx

SHARPNESS_MIN = 60.0


def parse_targets(spec: str) -> list[tuple[float, str]]:
    out = []
    for part in filter(None, spec.split(",")):
        t, _, target = part.partition(":")
        out.append((float(t), target))
    return sorted(out)


def target_at(schedule: list[tuple[float, str]], t: float) -> str:
    current = ""
    for start, target in schedule:
        if t >= start:
            current = target
    return current


def sharpness(frame) -> float:
    small = cv2.resize(frame, (240, int(240 * frame.shape[0] / frame.shape[1])))
    return float(cv2.Laplacian(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--fps", type=float, default=1.5)
    ap.add_argument("--targets", default="")
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"cannot open {args.video}", file=sys.stderr)
        return 1
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, int(round(src_fps / args.fps)))
    schedule = parse_targets(args.targets)

    with httpx.Client(base_url=args.api, timeout=600) as api:
        sweep = api.post("/sweeps", json={"device": f"replay:{args.video}"}).json()
        sid, idx, sent, last_target = sweep["id"], 0, 0, None
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % step == 0 and sharpness(frame) >= SHARPNESS_MIN:
                t_ms = int(idx / src_fps * 1000)
                target = target_at(schedule, t_ms / 1000)
                if target != last_target and target:
                    api.post(f"/sweeps/{sid}/target", json={"target": target})
                    last_target = target
                ok_enc, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if ok_enc:
                    api.post(f"/sweeps/{sid}/frames",
                             files={"file": (f"{t_ms}.jpg", buf.tobytes(), "image/jpeg")},
                             data={"t_ms": t_ms, "width": frame.shape[1], "height": frame.shape[0], "target": target})
                    sent += 1
                    time.sleep(0.2)  # keep the queue from overflowing
            idx += 1
        print(f"uploaded {sent} frames to sweep {sid}; finishing...", file=sys.stderr)
        print(json.dumps(api.post(f"/sweeps/{sid}/finish").json(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
