# AI Waste Segregation — Windows Setup

A simple, 5-step setup. Do steps 1–4 **once**. After that you only ever use **step 5**.

---

## Step 1 — Install Python (one time)
1. Go to **https://www.python.org/downloads/**
2. Download **Python 3.12** and open the installer.
3. ⚠️ **Tick the box "Add Python to PATH"** at the bottom, then click **Install Now**.

## Step 2 — Install the USB drivers (one time)
So Windows can see the device when you plug it in:
- **CH340 driver** → https://www.wch-ic.com/downloads/CH341SER_EXE.html
- **CP210x driver** → https://www.silabs.com/developer-tools/usb-to-uart-bridge-vcp-drivers

Install both, then **restart the PC**.

## Step 3 — Get the project
- Go to **https://github.com/circuitseeker/ai-waste-**
- Click the green **Code** button → **Download ZIP**.
- **Right-click the ZIP → Extract All.** Remember the folder.

## Step 4 — Install (one time)
Open the extracted folder and **double-click `setup.bat`**.
- A black window opens and installs everything (first time downloads ~2 GB — leave it running).
- Wait until it says **"Setup complete!"**, then close it.

## Step 5 — Run it (every time)
1. **Plug the device into the PC** with its USB cable(s).
2. **Double-click `run.bat`.**
3. Wait ~15 seconds for **"Ready"**.
4. **Hold a piece of waste in front of the sensor** — the camera reads it, the screen shows the type, and the servos sort it into the right bin.

To stop: close the window.

---

## If something goes wrong

| What you see | What to do |
|---|---|
| "Python was not found" | Redo **Step 1** and make sure you ticked **Add Python to PATH**. |
| The device isn't detected | Redo **Step 2** (drivers), unplug and replug the USB, restart. |
| "no serial port found" | Close any Arduino window, unplug/replug the device, run `run.bat` again. |
| Nothing happens at the sensor | Make sure the item is **within ~10 cm** of the sensor and the area is well lit. |

**Need help?** Contact circuitseeker.
