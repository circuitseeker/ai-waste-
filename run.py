#!/usr/bin/env python3
"""
ONE command, ONE terminal.

    python run.py

Loads the camera, the CLIP model and the OLED, then:
    press ENTER  -> capture -> classify -> drive servo -> show on OLED
    type q + ENTER (or Ctrl+C) to quit.

Optional: auto mode (no key presses), capture every N seconds:
    python run.py --auto 3
"""
import argparse
import sys

# make `backend` importable when run from the project root
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))

from backend import config              # noqa: E402
from backend.classifier import Classifier  # noqa: E402
from backend.hardware import make_hardware  # noqa: E402
from backend.oled import OledDisplay    # noqa: E402


def route_for(pred) -> str:
    """Physical destination: WET, DRY or EWASTE.

    E-waste (phone, laptop, battery, cable, electronics) goes to its own bin via
    servo 2; everything else is WET or DRY via servo 1.
    """
    if (pred.category or "").lower() == "e-waste":
        return "EWASTE"
    return pred.bin      # WET or DRY


def one_cycle(hw, clf, oled) -> None:
    oled.scanning()
    frame = hw.capture()
    pred = clf.predict(frame)
    no_item = pred.bin == getattr(config, "NO_ITEM_BIN", "NONE")
    if no_item:
        oled.idle()
        print(f"  -> {pred.label}   (ignored — nothing to sort)")
        return
    route = route_for(pred)
    # oled.show() displays the result AND moves the sorting servos on the DevKit
    # (the firmware actuates on SHOW): servo 1 = WET/DRY, servo 2 = E-WASTE.
    oled.show(pred.name or pred.label, pred.category or "Waste", route)
    print(f"  -> {pred.label}   |  ROUTE: {route}  |  {pred.confidence * 100:.0f}%")


def sensor_loop(hw, clf, oled, distance_cm: float) -> None:
    """Auto-capture whenever the ultrasonic sees an object closer than distance_cm.

    The HC-SR04 is wired to the OLED board, so we poll its distance. Falls back
    to the camera board's sensor if the OLED isn't connected. Debounced: one
    capture per object; re-arms only after the object leaves.
    """
    import time

    if oled.connected:
        source = "OLED board"
        read_cm = oled.distance_cm
    else:
        source = "camera board"
        read_cm = hw.distance_cm

    print(f"Sensor mode ({source}): capturing when something is closer "
          f"than {distance_cm:.0f} cm.")
    print("Place an item under the sensor. Ctrl+C to stop.\n")
    armed = True
    last_print = 0.0
    while True:
        d = read_cm()
        now = time.time()
        if now - last_print > 0.4:                     # live readout, throttled
            bar = "OBJECT!" if d < distance_cm else ""
            print(f"\rdistance: {d:6.1f} cm  {bar:8s}", end="", flush=True)
            last_print = now
        if d < distance_cm and armed:
            print()                                    # newline before result
            one_cycle(hw, clf, oled)
            armed = False                              # wait for it to be removed
        elif d >= distance_cm:
            armed = True
        time.sleep(0.12)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sensor", action="store_true",
                    help="auto-capture from the ultrasonic sensor (no key presses)")
    ap.add_argument("--distance", type=float, default=10.0,
                    help="trigger distance in cm for --sensor (default 10)")
    ap.add_argument("--auto", type=float, default=0,
                    help="auto-capture every N seconds instead of on ENTER")
    args = ap.parse_args()

    print("Starting up (loading camera, model, OLED)...")
    hw = make_hardware()
    oled = OledDisplay(exclude_port=getattr(hw, "_port", None))
    clf = Classifier()
    print(f"\nReady.  camera={hw.mode}  model={clf.source}  "
          f"oled={'yes' if oled.connected else 'no'}\n")

    try:
        if args.sensor:
            sensor_loop(hw, clf, oled, args.distance)
        elif args.auto > 0:
            import time
            print(f"Auto mode: capturing every {args.auto}s. Ctrl+C to stop.\n")
            while True:
                one_cycle(hw, clf, oled)
                time.sleep(args.auto)
        else:
            while True:
                key = input("Press ENTER to capture (q to quit) > ").strip().lower()
                if key == "q":
                    break
                one_cycle(hw, clf, oled)
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        print("\nshutting down...")
        hw.close()
        oled.close()


if __name__ == "__main__":
    main()
