# AI Waste Segregation — Windows Setup

Download, then run **one file**. That's it.

---

## Step 1 — Install Python (one time)
1. Go to **https://www.python.org/downloads/**
2. Download **Python 3.12** and open the installer.
3. ⚠️ **Tick "Add Python to PATH"** at the bottom, then click **Install Now**.

## Step 2 — Install the USB drivers (one time)
So Windows can see the device when you plug it in:
- **CH340 driver** → https://www.wch-ic.com/downloads/CH341SER_EXE.html
- **CP210x driver** → https://www.silabs.com/developer-tools/usb-to-uart-bridge-vcp-drivers

Install both, then **restart the PC**.

## Step 3 — Download the project
- Go to **https://github.com/circuitseeker/ai-waste-**
- Click the green **Code** button → **Download ZIP**.
- **Right-click the ZIP → Extract All.**

## Step 4 — Run it
1. **Plug the device into the PC** with its USB cable(s).
2. Open the extracted folder and **double-click `START.bat`**.

That's all. The **first time**, it installs everything automatically (downloads ~2 GB — leave it running). **Every time after**, it just starts in ~15 seconds.

It shows the connected COM ports, finds the **ESP32-CAM** and the **ESP32 board** on its own, and begins. **Hold a piece of waste near the sensor** — the screen shows the type and the servos sort it into the right bin.

To stop: close the window.

---

## If something goes wrong

| What you see | What to do |
|---|---|
| "Python is not installed" | Redo **Step 1**, making sure you ticked **Add Python to PATH**. |
| "Connected COM ports: (none…)" | Redo **Step 2** (drivers), unplug/replug the USB, restart the PC. |
| "no serial port found" | Close any Arduino window (only one program can use a COM port), replug, run `START.bat` again. |
| Nothing happens at the sensor | Keep the item **within ~10 cm** of the sensor, and make sure the area is well lit. |

**Need help?** Contact circuitseeker.
