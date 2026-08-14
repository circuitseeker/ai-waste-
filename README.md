# ♻️ AI Waste Segregation

Point an ESP32-CAM at a piece of rubbish; it tells you what it is and which bin
it belongs in, then drives a servo to sort it.

Classification runs **locally** with zero-shot CLIP — no training, no API key,
no cloud. It recognises 27 item types — banana peel, soda can, chocolate
wrapper, cloth, mobile phone, pens, pencils, erasers, wires, tissues, plastic
bags — and says *"not sure"* rather than guessing.

**Runs with no hardware at all** — it falls back to your laptop webcam, so you
can try the whole flow before touching the ESP32.

---

## Quick start

### 1. Install

<details open>
<summary><b>macOS / Linux</b></summary>

```bash
git clone https://github.com/circuitseeker/ai-waste-.git
cd ai-waste-
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```
</details>

<details>
<summary><b>Windows (PowerShell)</b></summary>

```powershell
git clone https://github.com/circuitseeker/ai-waste-.git
cd ai-waste-
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If activation is blocked, run once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
</details>

### 2. Run

```bash
python -m backend.app
```

Open **<http://127.0.0.1:8000>**.

> First launch downloads the CLIP weights (~1.7 GB) and takes a few minutes.
> Every later start takes ~10 s. Nothing else to download or train.

### 3. Plug in the ESP32-CAM (optional)

Flash `firmware/esp32cam_serial/` with [PlatformIO](https://platformio.org/):

```bash
cd firmware
pio run -t upload        # hold GPIO0 -> GND and reset to enter bootloader
```

Then restart the server. The port is auto-detected on all three OSes; the UI
shows *"ESP32-CAM connected"*.

---

## Common problems

| Symptom | Fix |
|---|---|
| `no serial port found` | Close Arduino Serial Monitor / `liveview.py` — only one program can hold the port. Still stuck? Set it manually (below). |
| Wrong / no device picked | `SERIAL_PORT=COM5` (Windows), `SERIAL_PORT=/dev/ttyUSB0` (Linux), `SERIAL_PORT=/dev/cu.usbserial-XXXX` (macOS) |
| Linux: permission denied on port | `sudo usermod -aG dialout $USER`, then log out and back in |
| UI says "Heuristic (no model)" | `pip install torch transformers` |
| Everything sorted as one class | Improve the lighting first — glare is the top cause. Then see *Tuning*. |

## Tuning

Everything lives in [`backend/config.py`](backend/config.py). Add an item type
by adding one line to `WASTE_CLASSES` — no retraining:

```python
{"prompts": ["a pizza box", "a greasy cardboard food box"],
 "name": "Pizza box", "category": "Non-recyclable", "bin": "DRY"},
```

Any setting can be overridden per-run:

```bash
CONFIDENCE_THRESHOLD=0.5 SIMULATION=on python -m backend.app
```

| Variable | Meaning | Default |
|---|---|---|
| `SERIAL_PORT` | ESP32 port; empty = auto-detect | `""` |
| `CONFIDENCE_THRESHOLD` | below this → *"unsure"* | `0.30` |
| `CLIP_MODEL` | swap in `openai/clip-vit-base-patch32` for a 600 MB / 6 ms model | `…large-patch14` |
| `TTA_VIEWS` | how many crops of each photo to average (1 = fastest) | `4` |
| `AUTO_ENHANCE` | white-balance + contrast fix for the OV2640's colour cast | `true` |
| `BIN_VOTE` | pick the bin by vote across classes, not just the top-1 | `true` |
| `SIMULATION` | `auto` / `on` / `off` | `auto` |

### Why it copes with a bad camera

The OV2640 gives blurry, colour-cast, badly-framed 320×240 frames, and CLIP
only sees one 224×224 square of that. Three things compensate, all in
[`backend/classifier.py`](backend/classifier.py):

- **`AUTO_ENHANCE`** — grey-world white balance + CLAHE, so the frame looks
  like a normal photograph before the model ever sees it.
- **`TTA_VIEWS`** — the same photo is scored as a centre crop, the whole frame
  letterboxed, a 70% zoom (small items like a pen survive this) and a mirror;
  the probabilities are averaged. Worth **+10% accuracy** on real captures.
- **`BIN_VOTE`** — the bin is decided by the strongest few classes per bin, not
  by one top-1 guess, so several weak "dry-ish" votes still sort correctly.

### Teach it your camera (biggest single upgrade, still no training)

Zero-shot CLIP matches your photo against a *sentence*. A few real photos from
your own camera beat any sentence. Measured on held-out frames: **0/7 → 7/7**.

```
prototypes/
  cardboard_01.jpg  cardboard_02.jpg  cardboard_03.jpg
  pen_01.jpg        pen_02.jpg        pen_03.jpg
  no_item_01.jpg    hand_01.jpg       ...
```

Name each file with the class name (lowercase, `_` for spaces), 3–5 photos
each. It is read once at startup — no training step.

> **It is all-or-nothing on purpose.** Photos for only *some* classes make
> those classes win everything (measured: junk rejection 50% → 0%). So it is
> ignored until every class in `WASTE_CLASSES` has photos. Either shoot them
> all — `No item` is a picture of the empty belt, `Hand` is your hand — or
> delete the classes you will never demo. Scores also saturate near 1.00, so
> `CONFIDENCE_THRESHOLD` stops flagging junk: very decisive, less cautious.

## Check accuracy

```bash
python tools/bench.py                 # scores against real ESP32-CAM photos
python tools/bench.py --dir my_pics/  # …or your own (name files by class)
```

## Layout

```
backend/    FastAPI server, CLIP classifier, control loop
web/        dashboard (HTML/CSS/JS)
firmware/   ESP32-CAM sketch (PlatformIO)
tools/      bench.py (accuracy), liveview.py (live view + capture)
```

## Hardware

ESP32-CAM (AI-Thinker) · HC-SR04 ultrasonic · 2× SG90/MG90S servos · DC gear
motor + belt + L298N · 16×2 I²C LCD · 5 V supply · laptop.
