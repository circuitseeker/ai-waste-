#!/usr/bin/env python3
"""
Press ENTER to capture -> classify -> show on OLED, over and over.

The backend (python -m backend.app) must already be running. Run this in a
SECOND terminal:

    python tools/press.py                 # talks to http://127.0.0.1:8000
    python tools/press.py --port 8030     # if you started the server on another port

Each ENTER triggers one full cycle (the same as the web UI's "Simulate Item"
button); the classification is printed here and shown on the OLED.
"""
import argparse
import time

import requests


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    base = f"http://{args.host}:{args.port}"

    def latest_time():
        try:
            h = requests.get(f"{base}/api/history", timeout=5).json()["history"]
            return h[0]["time"] if h else None
        except Exception:
            return None

    print(f"Connected to {base}")
    print("Press ENTER to capture & classify.  Ctrl+C to quit.\n")

    while True:
        try:
            input("ENTER to capture > ")
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            return

        before = latest_time()
        try:
            requests.post(f"{base}/api/control/trigger", timeout=5)
        except Exception as exc:
            print(f"  ! could not reach the server: {exc}")
            continue

        # wait for the new result to land
        result = None
        for _ in range(40):
            try:
                h = requests.get(f"{base}/api/history", timeout=5).json()["history"]
                if h and h[0]["time"] != before:
                    result = h[0]
                    break
            except Exception:
                pass
            time.sleep(0.2)

        if not result:
            print("  (no result — is an item in front of the camera?)\n")
            continue

        if result.get("no_item"):
            print(f"  -> {result['label']}  (ignored, nothing to sort)\n")
        else:
            print(f"  -> {result['label']}  |  bin: {result['bin']}  |  "
                  f"{result['confidence'] * 100:.0f}% confident\n")


if __name__ == "__main__":
    main()
