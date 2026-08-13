"""
Central configuration for the AI Waste Segregation system.

Everything you might need to tweak lives here. Values can also be overridden
with environment variables (handy on Windows vs macOS without editing code).
"""
import os


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


# ---------------------------------------------------------------------------
# Camera connection mode
# ---------------------------------------------------------------------------
#   serial -> ESP32-CAM plugged into the laptop over USB/FTDI (NO Wi-Fi). Best
#             for this project — one photo per item, no network needed.
#   wifi   -> ESP32-CAM reachable over the network at ESP32_IP.
#   auto   -> try serial, then wifi, then simulation.
CAMERA_MODE = _env("CAMERA_MODE", "serial").lower()

# Serial port of the FTDI/USB adapter. Leave empty to auto-detect a usbserial /
# wchusbserial / SLAB / usbmodem port. Example: /dev/cu.usbserial-A5069RR4 (mac)
# or COM5 (Windows).
SERIAL_PORT = _env("SERIAL_PORT", "")
# MUST match SERIAL_BAUD in the esp32cam_serial firmware.
SERIAL_BAUD = int(_env("SERIAL_BAUD", "921600"))


# ---------------------------------------------------------------------------
# ESP32-CAM (Wi-Fi mode)
# ---------------------------------------------------------------------------
# The IP address the ESP32-CAM prints to the Serial Monitor when it connects
# to your Wi-Fi. Update this to match your board.
ESP32_IP = _env("ESP32_IP", "192.168.68.55")
ESP32_BASE = f"http://{ESP32_IP}"

# Endpoints exposed by the firmware (see firmware/esp32cam_waste)
ESP32_CAPTURE_URL = f"{ESP32_BASE}/capture"     # returns a single JPEG
ESP32_STATUS_URL = f"{ESP32_BASE}/status"       # returns {"object":bool,"distance_cm":float}
ESP32_RESULT_URL = f"{ESP32_BASE}/result"       # GET ?type=WET  -> drives LCD + servo + belt

# How often the control loop asks the ESP32 whether an object is present.
POLL_INTERVAL_S = float(_env("POLL_INTERVAL_S", "0.25"))

# Distance (cm) below which the ultrasonic sensor considers an object "present".
OBJECT_DISTANCE_CM = float(_env("OBJECT_DISTANCE_CM", "12"))


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
# Path to a trained Keras model. The default matches a Google Teachable Machine
# "TensorFlow / Keras" export dropped into the model/ folder.
MODEL_PATH = _env("MODEL_PATH", "model/keras_model.h5")
LABELS_PATH = _env("LABELS_PATH", "model/labels.txt")

# Input size the model expects (Teachable Machine + MobileNetV2 both use 224).
IMG_SIZE = int(_env("IMG_SIZE", "224"))

# Minimum confidence before we trust a prediction. Below this we mark UNSURE.
CONFIDENCE_THRESHOLD = float(_env("CONFIDENCE_THRESHOLD", "0.60"))


# ---------------------------------------------------------------------------
# Bin mapping
# ---------------------------------------------------------------------------
# Maps every model label to a physical bin the 2-axis servo will target.
# The value is what the firmware receives via /result?type=...
# Add classes here (plastic, metal, glass...) as your model grows.
BIN_MAP = {
    "Dry / Paper": "DRY",
    "Wet": "WET",
    # common Teachable-Machine label variants:
    "dry": "DRY",
    "paper": "DRY",
    "wet": "WET",
    "organic": "WET",
}
DEFAULT_BIN = "DRY"


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
# SIMULATION mode lets the whole UI + pipeline run with NO hardware and NO
# trained model. It uses the laptop webcam (or a random guess) so you can see
# everything working before the ESP32 / model are ready.
#   auto  -> use hardware if reachable, else simulate
#   on    -> always simulate
#   off   -> require the ESP32
SIMULATION = _env("SIMULATION", "auto").lower()

# In simulation, use the laptop webcam as the "camera". Set to false to use
# synthetic frames only (useful for headless testing / no camera permission).
USE_WEBCAM = _env("USE_WEBCAM", "true").lower() == "true"

HOST = _env("HOST", "127.0.0.1")
PORT = int(_env("PORT", "8000"))

# Optional Firebase logging (see firebase_logger.py). Off by default.
FIREBASE_ENABLED = _env("FIREBASE_ENABLED", "false").lower() == "true"
FIREBASE_DB_URL = _env("FIREBASE_DB_URL", "")
FIREBASE_KEY_PATH = _env("FIREBASE_KEY_PATH", "model/firebase_key.json")
