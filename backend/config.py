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
# OLED status display (second ESP32 running firmware/oled_display)
# ---------------------------------------------------------------------------
# Shows the category / waste type / bin for each detected item.
OLED_ENABLED = _env("OLED_ENABLED", "true").lower() == "true"
# Leave empty to auto-detect (a serial port that replies "OLED" to PING, other
# than the camera's port). Example: /dev/cu.usbserial-0001 or COM6.
OLED_PORT = _env("OLED_PORT", "")
OLED_BAUD = int(_env("OLED_BAUD", "115200"))


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
    # --- Stationery / DRY ---------------------------------------------------
    # Small, thin, low-contrast objects — the hardest thing for a 320x240 OV2640
    # frame. Lots of phrasings here on purpose: a pen photographed badly reads to
    # CLIP as "a thin dark stick", so we give it every wording that could match.
    {"prompts": ["a ballpoint pen", "a plastic pen", "a used biro pen",
                 "a marker pen", "a highlighter", "a felt tip pen",
                 "a pen lying on a table", "an empty pen refill"],
     "name": "Pen",            "category": "Stationery",      "bin": "DRY"},
    {"prompts": ["a pencil", "a wooden pencil", "a sharpened pencil",
                 "a short pencil stub", "pencil shavings", "a coloured pencil"],
     "name": "Pencil",         "category": "Stationery",      "bin": "DRY"},
    {"prompts": ["a rubber eraser", "a pencil eraser", "a small white eraser",
                 "a used dirty eraser", "a block of rubber"],
     "name": "Eraser",         "category": "Stationery",      "bin": "DRY"},
    # Keep every phrase a CONCRETE object. Vague catch-alls ("a small
    # stationery item", "desk stationery") measurably drag this class towards
    # the empty-scene reject classes, because vague text sits near everything.
    {"prompts": ["a pencil sharpener", "a plastic ruler", "a stapler",
                 "paper clips", "a glue stick", "a pen holder full of pens",
                 "a plastic pencil case"],
     "name": "Stationery",     "category": "Stationery",      "bin": "DRY"},
    # --- Textile / DRY ---
    {"prompts": ["a piece of cloth", "folded fabric", "an old t-shirt",
                 "a rag", "a piece of clothing", "a towel"],
     "name": "Cloth",          "category": "Textile",         "bin": "DRY"},
    # --- E-waste / DRY -----------------------------------------------------
    # Electronics genuinely belong in neither bin — they need separate hazardous
    # collection. With only two physical bins, DRY is the least-wrong chute, and
    # the label says "E-waste" so a human can pull it back out.
    {"prompts": ["a mobile phone", "a smartphone", "a broken cell phone",
                 "a computer mouse", "a circuit board", "a remote control",
                 "an LED bulb", "a resistor and a capacitor",
                 "a broken pair of headphones", "a computer keyboard"],
     "name": "Electronics",    "category": "E-waste",         "bin": "DRY"},
    {"prompts": ["a battery", "AA batteries", "a button cell battery"],
     "name": "Battery",        "category": "E-waste",         "bin": "DRY"},
    {"prompts": ["a charging cable", "a tangled usb cable", "earphones",
                 "a power adapter", "a bundle of electrical wires",
                 "a coil of copper wire", "a cut piece of electrical wire",
                 "jumper wires", "a stripped wire"],
     "name": "Cable / wire",   "category": "E-waste",         "bin": "DRY"},
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
# Making a bad camera behave — image preprocessing
# ---------------------------------------------------------------------------
# The OV2640 on the ESP32-CAM has no decent auto-white-balance and a tiny
# sensor: frames come out with heavy colour casts (pink/green), crushed shadows
# and blown highlights. CLIP was trained on normal photographs, so the further
# a frame drifts from "a normal photo" the worse it scores. These two steps pull
# it back towards normal BEFORE it ever reaches the model.
AUTO_ENHANCE = _env("AUTO_ENHANCE", "true").lower() == "true"

# Grey-world white balance: assume the average of the scene should be neutral
# grey and scale each channel towards that. 1.0 = full correction, 0.0 = off.
# 0.7 is deliberately partial — full correction washes the colour out of
# genuinely coloured objects (a red Coca-Cola can should stay red).
WB_STRENGTH = float(_env("WB_STRENGTH", "0.7"))

# CLAHE (local contrast) on the lightness channel only, so colours are
# untouched. Recovers detail from under-exposed corners and glare. Above ~3.0
# it starts amplifying sensor noise into fake texture.
CLAHE_CLIP = float(_env("CLAHE_CLIP", "2.0"))

# ---------------------------------------------------------------------------
# Test-time augmentation (TTA)
# ---------------------------------------------------------------------------
# CLIP sees one 224x224 square. Feeding it the centre crop of a 320x240 frame
# throws away the left and right edges, and a small item (a pen, an eraser) can
# end up as a few pixels in a big frame. Instead we look at the SAME photo
# several ways and average the embeddings:
#   1 -> centre square crop            (the plain, default behaviour)
#   2 -> + whole frame letterboxed     (nothing cropped away)
#   3 -> + 70% centre zoom             (rescues small items)
#   4 -> + mirrored centre crop        (cancels left/right framing luck)
# Cost is roughly linear: each extra view is one more forward pass (~200 ms on
# CPU with large-patch14). Set TTA_VIEWS=1 if you need the loop faster.
TTA_VIEWS = int(_env("TTA_VIEWS", "4"))

# ---------------------------------------------------------------------------
# How the physical bin is decided
# ---------------------------------------------------------------------------
# Naive: take the single highest-scoring class and use its bin. That is fragile
# with ~25 classes, because a pen at 0.20, an eraser at 0.18 and plastic cutlery
# at 0.15 can all lose to one unrelated class at 0.22 — even though the photo is
# overwhelmingly "something dry".
#
# With BIN_VOTE on we instead add up the strongest few classes PER BIN and let
# the bins compete. The displayed label is still the best class inside the
# winning bin, so the label and the servo can never contradict each other.
#
# Top-K rather than a full sum on purpose: DRY has far more classes than WET, so
# summing everything would hand DRY a permanent head start just for being a
# bigger list. K=3 keeps the vote about strong evidence, not class counts.
BIN_VOTE = _env("BIN_VOTE", "true").lower() == "true"
BIN_VOTE_TOPK = int(_env("BIN_VOTE_TOPK", "3"))

# ---------------------------------------------------------------------------
# Few-shot prototypes — the single biggest upgrade available, and still no
# training
# ---------------------------------------------------------------------------
# Zero-shot CLIP compares your photo against a SENTENCE ("a photo of a pen").
# That sentence describes a pen in general, not a pen as YOUR camera sees one,
# under YOUR lighting, on YOUR belt. The gap between those two is most of the
# error left in this system.
#
# Drop a few real photos in `prototypes/` and each class also gets an "this is
# what it actually looks like here" vector, averaged from your images and mixed
# with the text one. No training, no labels beyond the filename, no GPU — it is
# just an extra average, computed once at startup.
#
#   prototypes/
#     pen_01.jpg  pen_02.jpg  pen_03.jpg
#     cardboard_01.jpg  cardboard_02.jpg
#     fruit_peel_01.jpg  ...
#
# Name each file with the class name in lowercase, spaces as underscores, then
# anything you like. Classes you have no photos for keep working on text alone,
# so you can add them a few at a time. 3-5 photos per class is plenty.
PROTOTYPE_DIR = _env("PROTOTYPE_DIR", "prototypes")

# How much to trust your photos vs the text description, 0.0-1.0.
# 0.0 = ignore photos entirely (pure zero-shot, the old behaviour)
# 0.5 = balanced, a good default
# 1.0 = photos only, which overfits hard if you gave it 3 images of one angle
PROTOTYPE_WEIGHT = float(_env("PROTOTYPE_WEIGHT", "0.5"))

# ALL-OR-NOTHING, and it matters. Photos for only some classes make those
# classes beat everything else regardless of what is in front of the camera —
# measured, class accuracy 0/7 -> 7/7 but junk rejection 50% -> 0%. So example
# photos are ignored unless EVERY class in WASTE_CLASSES has some. Two ways to
# get there: photograph all of them (including the easy ones — "No item" is a
# picture of the empty belt, "Hand" is your hand), or delete the classes you
# are never going to demo. Set this true only if you know what you are trading.
PROTOTYPE_ALLOW_PARTIAL = _env("PROTOTYPE_ALLOW_PARTIAL", "false").lower() == "true"

# Note: with prototypes on, scores saturate near 1.00 and CONFIDENCE_THRESHOLD
# stops being a useful reject signal — the model becomes very decisive. Good
# for a live demo, worse for spotting an empty belt.

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
