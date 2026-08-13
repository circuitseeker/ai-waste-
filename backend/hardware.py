"""
Hardware abstraction — talks to the ESP32-CAM over Wi-Fi, or falls back to a
laptop webcam / synthetic source in SIMULATION mode.

The rest of the app only sees three operations:
    - object_present() -> bool          (ultrasonic trigger)
    - capture()        -> BGR frame     (photo of the item)
    - send_result(bin) -> None          (drive LCD + 2-axis servo + belt)
    - snapshot_jpeg()  -> bytes         (a JPEG for the live web view)
"""
from __future__ import annotations

import time

import cv2
import numpy as np
import requests

from . import config


class HardwareBase:
    mode = "base"

    def object_present(self) -> bool: ...
    def capture(self) -> np.ndarray: ...
    def send_result(self, bin_cmd: str) -> None: ...
    def snapshot_jpeg(self) -> bytes | None: ...
    def close(self) -> None: ...


# ---------------------------------------------------------------------------
# Real ESP32-CAM
# ---------------------------------------------------------------------------
class Esp32Hardware(HardwareBase):
    mode = "esp32"

    def __init__(self) -> None:
        # Fail fast if the board isn't reachable.
        requests.get(config.ESP32_STATUS_URL, timeout=2).raise_for_status()

    def object_present(self) -> bool:
        try:
            data = requests.get(config.ESP32_STATUS_URL, timeout=2).json()
        except Exception:  # noqa: BLE001
            return False
        if "object" in data:
            return bool(data["object"])
        return float(data.get("distance_cm", 999)) < config.OBJECT_DISTANCE_CM

    def capture(self) -> np.ndarray:
        resp = requests.get(config.ESP32_CAPTURE_URL, timeout=8)
        resp.raise_for_status()
        fmt = resp.headers.get("X-Format", "")
        ctype = resp.headers.get("Content-Type", "")

        if fmt == "RGB565" or "octet-stream" in ctype:
            # Raw RGB565 from a no-PSRAM / non-JPEG sensor — convert here.
            w = int(resp.headers["X-Width"])
            h = int(resp.headers["X-Height"])
            buf = np.frombuffer(resp.content, dtype=np.uint8)
            expected = w * h * 2
            if buf.size < expected:
                raise RuntimeError(f"short RGB565 frame: {buf.size} < {expected}")
            rgb565 = buf[:expected].reshape(h, w, 2)
            # The ESP32/GC0308 sends RGB565 byte-swapped vs what OpenCV expects,
            # so swap the two bytes per pixel before converting to BGR.
            rgb565 = np.ascontiguousarray(rgb565[:, :, ::-1])
            img = cv2.cvtColor(rgb565, cv2.COLOR_BGR5652BGR)
            return img

        # Fallback: a JPEG-capable sensor (e.g. real OV2640 with PSRAM).
        arr = np.frombuffer(resp.content, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError("ESP32-CAM returned an undecodable frame")
        return img

    def send_result(self, bin_cmd: str) -> None:
        try:
            requests.get(config.ESP32_RESULT_URL, params={"type": bin_cmd}, timeout=3)
        except Exception as exc:  # noqa: BLE001
            print(f"[hardware] Failed to send result to ESP32: {exc}")

    def snapshot_jpeg(self) -> bytes | None:
        # Grab a frame (converting raw RGB565 if needed) and JPEG-encode it on
        # the laptop for the browser view.
        try:
            frame = self.capture()
        except Exception:  # noqa: BLE001
            return None
        ok, buf = cv2.imencode(".jpg", frame)
        return buf.tobytes() if ok else None

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# ESP32-CAM over USB / SERIAL  (no Wi-Fi)
# ---------------------------------------------------------------------------
class SerialHardware(HardwareBase):
    mode = "serial"

    def __init__(self) -> None:
        import serial  # pyserial
        from serial.tools import list_ports

        port = config.SERIAL_PORT
        if not port:
            port = self._autodetect(list_ports)
        if not port:
            raise RuntimeError("no serial port found (set SERIAL_PORT)")

        self._ser = serial.Serial()
        self._ser.port = port
        self._ser.baudrate = config.SERIAL_BAUD
        self._ser.timeout = 5
        # Don't drive DTR/RTS — on this board RTS is wired to EN (reset) and
        # DTR to GPIO0, so asserting them would hold the ESP32 in reset.
        self._ser.dtr = False
        self._ser.rts = False
        self._ser.open()
        self._port = port
        time.sleep(2.0)                 # allow the ESP32 to reset & boot
        self._ser.reset_input_buffer()
        # Confirm it's our firmware.
        self._ser.write(b"P")
        if b"PONG" not in self._ser.readline():
            # give it one more shot after boot noise
            self._ser.reset_input_buffer()
            self._ser.write(b"P")
            if b"PONG" not in self._ser.readline():
                raise RuntimeError(f"no ESP32 serial firmware responding on {port}")
        print(f"[hardware] ESP32-CAM (serial) on {port} @ {config.SERIAL_BAUD} baud.")

    @staticmethod
    def _autodetect(list_ports) -> str:
        candidates = []
        for p in list_ports.comports():
            name = (p.device or "")
            low = name.lower()
            if any(k in low for k in ("usbserial", "wchusbserial", "slab",
                                      "usbmodem", "ttyusb", "ttyacm")) or \
               low.startswith("com"):
                candidates.append(name)
        return candidates[0] if candidates else ""

    def _read_exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self._ser.read(n - len(buf))
            if not chunk:
                raise RuntimeError("serial read timeout")
            buf += chunk
        return buf

    def _read_any_marker(self, markers: tuple[bytes, ...], limit: int = 200000) -> bytes:
        """Scan the stream until one of the 4-byte markers appears; return it."""
        window = b""
        for _ in range(limit):
            b = self._ser.read(1)
            if not b:
                raise RuntimeError("serial timeout waiting for image marker")
            window = (window + b)[-4:]
            for m in markers:
                if window == m:
                    return m
        raise RuntimeError("image marker not found")

    def object_present(self) -> bool:
        try:
            self._ser.reset_input_buffer()
            self._ser.write(b"S")
            line = self._ser.readline().decode(errors="ignore").strip()
            if line.startswith("DIST"):
                mm = float(line.split()[1])
                return mm / 10.0 < config.OBJECT_DISTANCE_CM
        except Exception:  # noqa: BLE001
            pass
        return False

    def capture(self) -> np.ndarray:
        self._ser.reset_input_buffer()
        self._ser.write(b"C")
        marker = self._read_any_marker((b"JPG0", b"IMG0"))
        header = self._read_exact(8)
        length = int.from_bytes(header[0:4], "little")
        w = int.from_bytes(header[4:6], "little")
        h = int.from_bytes(header[6:8], "little")
        if length == 0:
            raise RuntimeError("camera returned empty frame")
        payload = self._read_exact(length)

        if marker == b"JPG0":
            arr = np.frombuffer(payload, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                raise RuntimeError("undecodable JPEG from ESP32")
            return img

        # Raw RGB565 fallback (byte-swapped).
        if length != w * h * 2:
            raise RuntimeError(f"bad RGB565 header len={length} w={w} h={h}")
        rgb565 = np.frombuffer(payload, dtype=np.uint8).reshape(h, w, 2)
        rgb565 = np.ascontiguousarray(rgb565[:, :, ::-1])
        return cv2.cvtColor(rgb565, cv2.COLOR_BGR5652BGR)

    def send_result(self, bin_cmd: str) -> None:
        try:
            self._ser.write(b"W" if bin_cmd.upper() == "WET" else b"D")
            self._ser.readline()   # consume "OK"
        except Exception as exc:  # noqa: BLE001
            print(f"[hardware] serial send_result failed: {exc}")

    def snapshot_jpeg(self) -> bytes | None:
        try:
            frame = self.capture()
        except Exception:  # noqa: BLE001
            return None
        ok, buf = cv2.imencode(".jpg", frame)
        return buf.tobytes() if ok else None

    def close(self) -> None:
        try:
            self._ser.close()
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Simulation (no hardware needed)
# ---------------------------------------------------------------------------
class SimHardware(HardwareBase):
    mode = "simulation"

    def __init__(self) -> None:
        self._cam = None
        if config.USE_WEBCAM:
            try:
                cam = cv2.VideoCapture(0)
                if cam.isOpened():
                    self._cam = cam
                    print("[hardware] Simulation using laptop webcam.")
            except Exception:  # noqa: BLE001
                self._cam = None
        if self._cam is None:
            print("[hardware] Simulation using synthetic frames (no webcam).")
        self._last_trigger = 0.0

    def object_present(self) -> bool:
        # Pretend an object arrives roughly every 6 seconds.
        now = time.time()
        if now - self._last_trigger > 6:
            self._last_trigger = now
            return True
        return False

    def capture(self) -> np.ndarray:
        if self._cam is not None:
            ok, frame = self._cam.read()
            if ok:
                return frame
        # Synthetic coloured frame so the heuristic has something to chew on.
        color = np.random.randint(0, 255, size=3)
        frame = np.full((240, 320, 3), color, dtype=np.uint8)
        return frame

    def send_result(self, bin_cmd: str) -> None:
        print(f"[hardware:sim] Would drive servo/belt -> bin {bin_cmd}")

    def snapshot_jpeg(self) -> bytes | None:
        frame = self.capture() if self._cam is not None else None
        if frame is None:
            frame = np.full((240, 320, 3), (40, 44, 52), dtype=np.uint8)
            cv2.putText(frame, "SIM", (120, 130), cv2.FONT_HERSHEY_SIMPLEX,
                        1.2, (200, 200, 200), 2)
        ok, buf = cv2.imencode(".jpg", frame)
        return buf.tobytes() if ok else None

    def close(self) -> None:
        if self._cam is not None:
            self._cam.release()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def make_hardware() -> HardwareBase:
    # Explicit simulation override always wins.
    if config.SIMULATION == "on":
        return SimHardware()

    cam = config.CAMERA_MODE

    def try_serial():
        hw = SerialHardware()
        return hw

    def try_wifi():
        hw = Esp32Hardware()
        print(f"[hardware] ESP32-CAM reachable at {config.ESP32_IP}.")
        return hw

    order = {
        "serial": [try_serial],
        "wifi": [try_wifi],
        "auto": [try_serial, try_wifi],
    }.get(cam, [try_serial])

    for attempt in order:
        try:
            return attempt()
        except Exception as exc:  # noqa: BLE001
            print(f"[hardware] {attempt.__name__} failed: {exc}")

    if config.SIMULATION == "off":
        raise RuntimeError("no camera hardware available and SIMULATION=off")
    print("[hardware] falling back to simulation mode.")
    return SimHardware()
