"""
OLED status display driver — talks to the second ESP32 (firmware/oled_display)
over USB serial and shows the category / waste type / bin for each item.

Auto-detects the OLED board by pinging candidate serial ports and looking for
the "OLED" reply, skipping the camera's port. No-op if disabled or not found,
so the rest of the system runs fine without it.
"""
from __future__ import annotations

import time

from . import config


class OledDisplay:
    def __init__(self, exclude_port: str | None = None) -> None:
        self._ser = None
        if not config.OLED_ENABLED:
            return
        try:
            import serial
            from serial.tools import list_ports
        except Exception as exc:  # noqa: BLE001
            print(f"[oled] pyserial missing ({exc}) -> OLED disabled.")
            return

        if config.OLED_PORT:
            try:
                self._ser = self._open(serial, config.OLED_PORT)
            except Exception as exc:  # noqa: BLE001
                print(f"[oled] could not open {config.OLED_PORT} ({exc}).")
                return
        else:
            self._ser = self._autodetect(serial, list_ports, exclude_port)

        if self._ser is None:
            print("[oled] no OLED display found -> skipping.")
            return
        self.idle()
        print(f"[oled] Display connected on {self._ser.port}.")

    # -- connection --------------------------------------------------------
    @staticmethod
    def _open(serial, port: str):
        s = serial.Serial()
        s.port = port
        s.baudrate = config.OLED_BAUD
        s.timeout = 1
        s.dtr = False
        s.rts = False
        s.open()
        time.sleep(1.8)          # let the ESP32 boot after the port opens
        s.reset_input_buffer()
        return s

    def _autodetect(self, serial, list_ports, exclude_port):
        """Return an OPEN serial to the board that replies 'OLED', else None."""
        for p in list_ports.comports():
            dev = p.device or ""
            low = dev.lower()
            if exclude_port and dev == exclude_port:
                continue
            if not (any(k in low for k in ("usbserial", "wchusbserial", "slab",
                                           "usbmodem", "ttyusb", "ttyacm"))
                    or low.startswith("com")):
                continue
            try:
                s = self._open(serial, dev)
                s.write(b"PING\n")
                # read a few lines; the board may emit boot noise first
                for _ in range(4):
                    if s.readline().decode(errors="ignore").strip() == "OLED":
                        return s
                s.close()
            except Exception:  # noqa: BLE001
                continue
        return None

    @property
    def connected(self) -> bool:
        return self._ser is not None

    # -- messages ----------------------------------------------------------
    def _send(self, line: str) -> None:
        if self._ser is None:
            return
        try:
            self._ser.write((line + "\n").encode())
        except Exception as exc:  # noqa: BLE001
            print(f"[oled] write failed: {exc}")

    def show(self, name: str, category: str, bin_cmd: str) -> None:
        # Keep it clean for a 128px line; the firmware just renders what we send.
        self._send(f"SHOW:{name}|{category}|{bin_cmd}")

    def scanning(self) -> None:
        self._send("SCAN")

    def idle(self) -> None:
        self._send("IDLE")

    def close(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:  # noqa: BLE001
                pass
