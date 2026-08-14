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
# Classifier — zero-shot CLIP (runs fully on your laptop, no cloud)
# ---------------------------------------------------------------------------
# We use OpenAI's CLIP, downloaded once as open weights and cached locally
# (at ~/.cache/huggingface). It scores the captured photo against a list of
# waste "concepts" and picks the best match — so it can recognise arbitrary
# items (a Pepsi can -> "Aluminium can, Recyclable, Dry") without you having
# to train anything. Add / edit classes freely in WASTE_CLASSES.
#
# large-patch14 (~1.7 GB, ~200 ms/frame) is the default because it was
# measurably better on real ESP32-CAM frames than base-patch32 (~600 MB,
# ~6 ms): 7/7 vs 5/7 correct, and it puts junk frames below the confidence
# threshold instead of guessing confidently. 200 ms is irrelevant here — the
# serial capture alone costs ~180 ms and the servo settle ~1.1 s.
# Set CLIP_MODEL=openai/clip-vit-base-patch32 if you want the small one.
CLIP_MODEL = _env("CLIP_MODEL", "openai/clip-vit-large-patch14")

# CLIP is noticeably more accurate when you average several phrasings of the
# same concept ("prompt ensembling") instead of scoring one sentence. Each
# class phrase below is rendered through EVERY template, and the resulting
# embeddings are averaged into one vector per class.
#
# These templates deliberately describe the conditions the ESP32-CAM actually
# produces — blurry, close-up, handheld, badly lit — not clean studio shots.
PROMPT_TEMPLATES = [
    "a photo of {}",
    "a blurry photo of {}",
    "a close-up photo of {}",
    "a low quality webcam photo of {}",
    "a photo of {} on a table",
    "a badly lit photo of {}",
    "a cropped photo of {} filling the frame",
]

# Each class is a thing CLIP compares the photo to. Fields:
#   prompts   -> noun phrases for the concept. MORE PHRASINGS = BETTER. Include
#                brand names (a Pepsi can) and synonyms; they all collapse to
#                the one `name`, so adding them costs nothing at runtime.
#   name      -> short label shown in the UI / scores
#   category  -> waste category, e.g. "Biodegradable", "Recyclable"
#   bin       -> physical bin the servo targets: "WET" or "DRY"
WASTE_CLASSES = [
    # --- Biodegradable / WET ---
    {"prompts": ["fruit peel", "a banana peel", "an orange peel", "vegetable peelings"],
     "name": "Fruit peel",     "category": "Biodegradable",   "bin": "WET"},
    {"prompts": ["food scraps", "leftover food", "food waste", "a plate of leftovers"],
     "name": "Food scraps",    "category": "Biodegradable",   "bin": "WET"},
    {"prompts": ["a used tea bag", "coffee grounds", "wet tea leaves"],
     "name": "Tea / coffee",   "category": "Biodegradable",   "bin": "WET"},
    {"prompts": ["eggshells", "a broken eggshell"],
     "name": "Eggshells",      "category": "Biodegradable",   "bin": "WET"},
    # --- Recyclable / DRY ---
    {"prompts": ["an aluminium drinks can", "a soda can", "a Pepsi can",
                 "a Coca-Cola can", "a crushed beverage can"],
     "name": "Aluminium can",  "category": "Recyclable",      "bin": "DRY"},
    {"prompts": ["a plastic bottle", "a clear plastic water bottle", "a PET bottle"],
     "name": "Plastic bottle", "category": "Recyclable",      "bin": "DRY"},
    {"prompts": ["a glass bottle", "a glass jar"],
     "name": "Glass bottle",   "category": "Recyclable",      "bin": "DRY"},
    {"prompts": ["a sheet of paper", "crumpled paper", "a paper cup", "a newspaper"],
     "name": "Paper",          "category": "Recyclable",      "bin": "DRY"},
    {"prompts": ["a cardboard box", "corrugated cardboard", "a brown shipping carton",
                 "a cardboard parcel with printed logo"],
     "name": "Cardboard",      "category": "Recyclable",      "bin": "DRY"},
    {"prompts": ["a steel food tin", "a tin can", "a metal food can"],
     "name": "Steel can",      "category": "Recyclable",      "bin": "DRY"},
    {"prompts": ["a juice carton", "a milk carton", "a Tetra Pak drinks carton"],
     "name": "Carton",         "category": "Recyclable",      "bin": "DRY"},
    # --- Non-recyclable / DRY ---
    {"prompts": ["a crisp packet", "a foil snack wrapper", "a shiny plastic wrapper",
                 "a chocolate bar wrapper", "a candy wrapper",
                 "a torn open snack packet"],
     "name": "Wrapper",        "category": "Non-recyclable",  "bin": "DRY"},
    {"prompts": ["a polystyrene foam cup", "a styrofoam container",
                 "a piece of thermocol packing foam"],
     "name": "Foam / thermocol", "category": "Non-recyclable", "bin": "DRY"},
    {"prompts": ["a plastic carrier bag", "a crumpled plastic bag",
                 "a polythene bag"],
     "name": "Plastic bag",    "category": "Non-recyclable",  "bin": "DRY"},
    {"prompts": ["a used paper tissue", "a crumpled napkin", "a paper towel"],
     "name": "Tissue",         "category": "Non-recyclable",  "bin": "DRY"},
    {"prompts": ["a plastic straw", "disposable plastic cutlery",
                 "a plastic spoon and fork"],
     "name": "Plastic cutlery", "category": "Non-recyclable", "bin": "DRY"},
    # --- Textile / DRY ---
    {"prompts": ["a piece of cloth", "folded fabric", "an old t-shirt",
                 "a rag", "a piece of clothing", "a towel"],
     "name": "Cloth",          "category": "Textile",         "bin": "DRY"},
    # --- E-waste / DRY -----------------------------------------------------
    # Electronics genuinely belong in neither bin — they need separate hazardous
    # collection. With only two physical bins, DRY is the least-wrong chute, and
    # the label says "E-waste" so a human can pull it back out.
    {"prompts": ["a mobile phone", "a smartphone", "a broken cell phone",
                 "a computer mouse", "a circuit board", "a remote control"],
     "name": "Electronics",    "category": "E-waste",         "bin": "DRY"},
    {"prompts": ["a battery", "AA batteries", "a button cell battery"],
     "name": "Battery",        "category": "E-waste",         "bin": "DRY"},
    {"prompts": ["a charging cable", "a tangled usb cable", "earphones",
                 "a power adapter"],
     "name": "Cable / charger", "category": "E-waste",        "bin": "DRY"},
    # --- Not waste / no item -> bin NONE, the servo does NOT fire -----------
    # Without these, EVERY frame is forced into one of the waste classes, so an
    # empty belt or a hand in shot gets sorted as whatever it least resembles.
    # These compete in the same softmax, so "nothing there" can simply win.
    # Verified: real desk-clutter frames flipped from a confident 0.5x
    # "Plastic bottle" to a correct no-item reject once these were added.
    {"prompts": ["an empty conveyor belt", "an empty plastic tray",
                 "an empty table top", "a plain empty surface",
                 "an empty cardboard bin interior"],
     "name": "No item",        "category": "Not waste",       "bin": "NONE"},
    {"prompts": ["a human hand", "a person's fingers", "an arm reaching in"],
     "name": "Hand",           "category": "Not waste",       "bin": "NONE"},
    # Keep these prompts about EMPTY SCENES, not about objects. Naming an
    # object here (e.g. "a pile of clothes") makes this reject class compete
    # with the real class for it and swallow genuine items.
    {"prompts": ["an empty room interior", "a bare wall or floor",
                 "a wide shot of a room with no clear subject",
                 "an out of focus dark blurry photo of nothing"],
     "name": "Background",     "category": "Not waste",       "bin": "NONE"},
]

# Bin value meaning "do not actuate" — the control loop skips the servo, the
# belt, and the counters when a frame lands in one of the "Not waste" classes.
NO_ITEM_BIN = "NONE"

# Minimum confidence before we trust a prediction. Below this we mark "(unsure)"
# and the servo still fires on the best guess — "unsure" is a label, not a veto.
#
# Set to 0.30 for DEMO USE: decisive. On real ESP32-CAM frames correct answers
# land at 0.94-0.99, so 0.30 never blocks a genuine item — the system always
# commits and never freezes mid-presentation, which reads far better in front
# of an audience than a silent no-op.
#
# The tradeoff, measured: junk frames (empty belt, glare, clutter) score
# 0.25-0.45, so at 0.30 most of them are NOT flagged and will be sorted as
# whatever they least resemble. That is fine when you are hand-feeding items
# and the belt is never empty. For unattended running raise this to 0.50,
# where the measured gap cleanly separates real items from junk.
CONFIDENCE_THRESHOLD = float(_env("CONFIDENCE_THRESHOLD", "0.30"))

# ---------------------------------------------------------------------------
# Legacy: local Keras model (Teachable Machine / train_model.py)
# ---------------------------------------------------------------------------
# Kept only so an old trained model still loads if CLIP can't run. Unused when
# CLIP is active. Drop keras_model.h5 + labels.txt into model/ to re-enable.
MODEL_PATH = _env("MODEL_PATH", "model/keras_model.h5")
LABELS_PATH = _env("LABELS_PATH", "model/labels.txt")
IMG_SIZE = int(_env("IMG_SIZE", "224"))


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
