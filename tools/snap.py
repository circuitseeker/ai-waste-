#!/usr/bin/env python3
"""
Capture photo(s) from the ESP32-CAM, save to disk, and open in your viewer.

Run from the project root (so `backend` is importable):

    python tools/snap.py                 # one photo -> captures/, opens it
    python tools/snap.py -n 5            # five photos
    python tools/snap.py -o ~/Downloads # save somewhere else
    python tools/snap.py --no-open      # just save, don't open a viewer
    python tools/snap.py --scale 3      # upscale small frames before saving

Uses whatever camera the backend is configured for (CAMERA_MODE in
backend/config.py) — serial USB by default. Close the web server / Serial
Monitor first so the USB port is free.
"""
import argparse
import datetime as dt
import os
import subprocess
import sys

import cv2

# Allow running as `python tools/snap.py` from the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.hardware import make_hardware  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Capture photos from the ESP32-CAM.")
    ap.add_argument("-n", "--count", type=int, default=1, help="how many photos")
    ap.add_argument("-o", "--outdir", default="captures", help="output folder")
    ap.add_argument("--scale", type=int, default=2, help="upscale factor for saved image")
    ap.add_argument("--no-open", action="store_true", help="don't open the viewer")
    args = ap.parse_args()

    outdir = os.path.expanduser(args.outdir)
    os.makedirs(outdir, exist_ok=True)

    hw = make_hardware()
    try:
        for i in range(args.count):
            frame = hw.capture()
            if args.scale > 1:
                frame = cv2.resize(frame, None, fx=args.scale, fy=args.scale,
                                   interpolation=cv2.INTER_NEAREST)
            ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.abspath(os.path.join(outdir, f"waste_{ts}_{i:02d}.jpg"))
            cv2.imwrite(path, frame)
            print("saved:", path)
            if not args.no_open:
                _open(path)
    finally:
        hw.close()


def _open(path: str) -> None:
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        elif sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606
        else:
            subprocess.run(["xdg-open", path], check=False)
    except Exception as exc:  # noqa: BLE001
        print(f"(couldn't auto-open: {exc})")


if __name__ == "__main__":
    main()
