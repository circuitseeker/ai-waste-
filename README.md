# ♻️ AI Waste Segregation

A smart bin that sorts **dry/paper** vs **wet** waste automatically.

An **ESP32-CAM** does the vision capture and drives the hardware (ultrasonic
trigger, 2-axis servo, conveyor belt, LCD). The **ML model runs locally on your
Mac or Windows laptop**, and a clean **web dashboard** shows the live camera,
classification result, counts, and history in real time.

```
Browser UI  ◄──WebSocket──►  Python backend (FastAPI + TensorFlow)  ◄──Wi-Fi──►  ESP32-CAM
 live feed, result,            local model inference + control loop     camera + HC-SR04
 counts, history, controls    (detect → capture → classify → divert)   + 2-axis servo + belt
```

## Highlights
- **Model runs locally** — no GPU, no paid cloud inference (MobileNetV2, ~1s/image on CPU).
- **Web UI** — Apple-style dashboard, live feed, live results over WebSocket.
- **Runs with zero hardware** — built-in *simulation mode* uses your laptop webcam so you can try the whole flow before the ESP32 or model are ready.
- **Swappable model** — drop in a Google Teachable Machine export or train your own.
- **Optional Firebase** logging for remote monitoring.

---

## Quick start

### 1. Install
```bash
cd waste-segregation
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# Apple Silicon Mac: pip install tensorflow-macos  (instead of the tensorflow line)
```

### 2. Run (works immediately, even with no hardware/model)
```bash
python -m backend.app
```
Open **http://127.0.0.1:8000**. With no ESP32/model it starts in **simulation
mode** — click **“Simulate Item”** to watch detect → classify → sort.

### 3. Add the model
Train or export a model into [`model/`](model/README.md) (Teachable Machine is
the fastest path). Restart the server — the UI will show *“Local model loaded.”*

### 4. Connect the ESP32-CAM
1. Open `firmware/esp32cam_waste/esp32cam_waste.ino` in Arduino IDE.
2. Set your Wi-Fi SSID/password, select board **“AI Thinker ESP32-CAM”**, flash it.
3. Read the printed IP from the Serial Monitor and set it in `backend/config.py`
   (`ESP32_IP`) — or `export ESP32_IP=192.168.x.x` before running.
4. Restart the server. It auto-detects the board; the UI shows
   *“ESP32-CAM connected.”*

---

## Configuration
All settings live in [`backend/config.py`](backend/config.py) and can be
overridden with environment variables, e.g.:
```bash
ESP32_IP=192.168.1.50 CONFIDENCE_THRESHOLD=0.7 SIMULATION=off python -m backend.app
```
| Variable | Meaning | Default |
|---|---|---|
| `ESP32_IP` | ESP32-CAM address | `192.168.1.50` |
| `SIMULATION` | `auto` / `on` / `off` | `auto` |
| `CONFIDENCE_THRESHOLD` | below this → *unsure* | `0.60` |
| `OBJECT_DISTANCE_CM` | ultrasonic trigger distance | `12` |
| `FIREBASE_ENABLED` | cloud logging | `false` |

## Project layout
```
backend/    FastAPI server, control loop, model + hardware glue
web/        dashboard (HTML / CSS / JS)
firmware/   ESP32-CAM Arduino sketch
train/      MobileNetV2 training script
model/      drop your trained model here (git-ignored)
```

## Hardware
ESP32-CAM (AI-Thinker) · HC-SR04 ultrasonic · 2× SG90/MG90S servos (2-axis
drop) · DC gear motor + belt + L298N driver · 16×2 I²C LCD · 5 V supply · laptop.

> **Note:** the AI-Thinker ESP32-CAM has very few free GPIOs (the camera uses
> most). Pin assignments in the firmware are camera-safe but should be verified
> for your board revision; for a robust build, offload the servos/motor/LCD to a
> small companion MCU driven over serial. See comments in the `.ino`.

## API (for reference)
| Route | What |
|---|---|
| `GET /` | dashboard |
| `GET /api/status` | current state (JSON) |
| `GET /api/snapshot` | latest camera JPEG (proxied) |
| `GET /api/history` | recent events |
| `POST /api/control/{pause\|resume\|reset\|trigger}` | controls |
| `WS /ws` | live event stream |
