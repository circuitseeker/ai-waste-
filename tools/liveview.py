#!/usr/bin/env python3
"""
Live camera view + capture gallery for the ESP32-CAM (serial mode).

Starts a tiny zero-dependency web server that:
  - streams the camera as an MJPEG feed at /stream
  - lets you click "Capture" to freeze the current frame, save it to
    <project>/captures/, and stack thumbnails in a gallery below.

Open it in any browser:

    python tools/liveview.py                # http://127.0.0.1:8001
    python tools/liveview.py --port 9000    # custom port

Notes
-----
- Only ONE process can hold the serial port. Stop `backend.app` / Serial
  Monitor / `snap.py` before running.
- The serial capture path is byte-by-byte, so the LIVE stream is a slow
  slideshow (~0.3–1 fps). Captures are taken from the displayed frame via
  <canvas>, so the Capture button is instant and doesn't disturb the stream.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

import cv2
import numpy as np

# Make `backend` importable when run as `python tools/liveview.py` from root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.hardware import SerialHardware  # noqa: E402

BOUNDARY = "frame"
CAPTURE_LOCK = threading.Lock()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTURES_DIR = os.path.join(ROOT, "captures")
os.makedirs(CAPTURES_DIR, exist_ok=True)

HTML = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ESP32-CAM Live + Capture</title>
<style>
  :root { color-scheme: light dark; }
  body { margin:0; min-height:100vh; font-family:-apple-system,system-ui,sans-serif;
         background:radial-gradient(circle at 50% 0%,#1f2430,#0e1116); color:#eee; }
  .wrap { max-width:880px; margin:0 auto; padding:24px 16px 60px; }
  header { text-align:center; margin-bottom:14px; }
  h1 { font-weight:600; font-size:18px; margin:0 0 4px; }
  header p { color:#8a93a6; font-size:13px; margin:0; }
  .stage { position:relative; text-align:center; }
  img#cam { max-width:80vw; max-height:60vh; border-radius:14px;
            box-shadow:0 12px 40px rgba(0,0,0,.5); background:#000; }
  .controls { display:flex; gap:10px; justify-content:center; margin:16px 0 8px; flex-wrap:wrap; }
  button { font:inherit; font-size:14px; padding:9px 18px; border-radius:10px; cursor:pointer;
           border:1px solid #2c3344; background:#262d3e; color:#eee; transition:.15s; }
  button:hover { background:#303a52; }
  button.primary { background:#0a84ff; border-color:#0a84ff; color:#fff; }
  button.ghost { background:transparent; }
  button:disabled { opacity:.4; cursor:default; }
  .hint { text-align:center; color:#6b7384; font-size:12px; margin-bottom:22px; word-break:break-all; }
  .gallery-head { display:flex; justify-content:space-between; align-items:center; margin:6px 0 10px; }
  .gallery-head h2 { font-size:14px; font-weight:600; margin:0; }
  .gallery-head .count { color:#8a93a6; font-size:12px; }
  .gallery { display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:10px; }
  .empty { color:#5a6374; font-size:13px; padding:18px; text-align:center;
           border:1px dashed #2a3142; border-radius:12px; }
  .thumb { background:#161b26; border:1px solid #232a3a; border-radius:10px; overflow:hidden; }
  .thumb img { width:100%; height:120px; object-fit:cover; display:block; background:#000; }
  .tmeta { display:flex; justify-content:space-between; align-items:center; padding:6px 8px; font-size:11px; }
  .tmeta span { color:#8a93a6; }
  .tmeta a { color:#0a84ff; text-decoration:none; }
  .toast { position:fixed; left:50%; bottom:24px; transform:translateX(-50%);
           background:#0a84ff; color:#fff; padding:8px 16px; border-radius:10px;
           font-size:13px; opacity:0; transition:.2s; pointer-events:none; }
  .toast.show { opacity:1; }
</style></head>
<body><div class="wrap">
  <header>
    <h1>ESP32-CAM Live</h1>
    <p>Serial MJPEG stream — slow slideshow is expected. Click Capture to grab a frame.</p>
  </header>

  <div class="stage">
    <img id="cam" src="/stream" alt="camera feed">
  </div>

  <div class="controls">
    <button class="primary" id="btn-capture">📷 Capture</button>
    <button id="btn-clear" class="ghost">Clear all</button>
  </div>
  <p class="hint" id="hint">Saved shots go to: <span id="cdir"></span></p>

  <div class="gallery-head">
    <h2>Captures</h2>
    <span class="count" id="count">0</span>
  </div>
  <div class="gallery" id="gallery"></div>
</div>
<div class="toast" id="toast"></div>

<script>
const cam = document.getElementById('cam');
const gallery = document.getElementById('gallery');
const countEl = document.getElementById('count');
const toast = document.getElementById('toast');

function showToast(msg) {
  toast.textContent = msg; toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 1200);
}

function escapeHtml(s){ return s.replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

function addItem(it, prepend) {
  const div = document.createElement('div');
  div.className = 'thumb';
  div.innerHTML =
    '<a href="' + it.url + '" target="_blank"><img src="' + it.url + '" loading="lazy"></a>' +
    '<div class="tmeta"><span>' + escapeHtml(it.file) + '</span>' +
    '<a href="' + it.url + '" download>save</a></div>';
  if (prepend && gallery.firstChild) gallery.insertBefore(div, gallery.firstChild);
  else gallery.appendChild(div);
}

async function refresh() {
  try {
    const r = await fetch('/shots');
    // The endpoint replies {"shots": [...]}, not a bare array — reading
    // .length off the wrapper gave undefined, so the gallery showed
    // "No captures yet" even with a folder full of them.
    const items = (await r.json()).shots || [];
    gallery.innerHTML = '';
    if (!items.length) {
      gallery.innerHTML = '<div class="empty">No captures yet. Click 📷 Capture.</div>';
    } else {
      items.forEach(it => addItem(it, false));
    }
    countEl.textContent = items.length;
  } catch (e) { console.error(e); }
}

async function postSave(blob) {
  const r = await fetch('/save', {
    method: 'POST', headers: {'Content-Type': 'image/jpeg'}, body: blob
  });
  if (!r.ok) throw new Error('save failed');
  const it = await r.json();
  // remove the "empty" placeholder if present
  const empty = gallery.querySelector('.empty');
  if (empty) empty.remove();
  addItem(it, true);
  countEl.textContent = (parseInt(countEl.textContent, 10) || 0) + 1;
  showToast('saved ' + it.file);
}

async function capture() {
  document.getElementById('btn-capture').disabled = true;
  try {
    // Preferred: freeze the EXACT frame currently shown (canvas of the MJPEG img).
    const w = cam.naturalWidth || cam.width || 320;
    const h = cam.naturalHeight || cam.height || 240;
    if (w && h) {
      const cv = document.createElement('canvas');
      cv.width = w; cv.height = h;
      cv.getContext('2d').drawImage(cam, 0, 0, w, h);
      const blob = await new Promise(res => cv.toBlob(res, 'image/jpeg', 0.92));
      if (blob && blob.size > 0) { await postSave(blob); return; }
    }
    throw new Error('canvas capture empty');
  } catch (e) {
    // Fallback: ask the server for a fresh serial grab, then save that.
    try {
      const r = await fetch('/snap');
      const blob = await r.blob();
      if (blob.size > 0) { await postSave(blob); return; }
    } catch (e2) { console.error(e2); }
    showToast('capture failed');
  } finally {
    document.getElementById('btn-capture').disabled = false;
  }
}

async function clearAll() {
  if (!confirm('Delete all saved captures?')) return;
  await fetch('/clear', {method: 'POST'});
  await refresh();
  showToast('cleared');
}

document.getElementById('btn-capture').addEventListener('click', capture);
document.getElementById('btn-clear').addEventListener('click', clearAll);

// recover the stream if it stalls
let lastLoad = performance.now();
setInterval(() => { if (performance.now() - lastLoad > 8000) cam.src = '/stream?_=' + Date.now(); }, 3000);
cam.addEventListener('load', () => { lastLoad = performance.now(); });

fetch('/cdir').then(r => r.text()).then(p => document.getElementById('cdir').textContent = p);
refresh();
</script>
</body></html>
"""


def grab_jpeg(hw: SerialHardware) -> bytes | None:
    """Capture one frame, stamp a timestamp, return JPEG bytes (or None)."""
    with CAPTURE_LOCK:
        try:
            frame = hw.capture()
        except Exception as exc:  # noqa: BLE001
            print(f"[liveview] capture failed: {exc}")
            return None
    ts = dt.datetime.now().strftime("%H:%M:%S")
    cv2.putText(frame, ts, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return buf.tobytes() if ok else None


def list_shots() -> list[dict]:
    out = []
    try:
        names = [n for n in os.listdir(CAPTURES_DIR)
                 if n.lower().endswith((".jpg", ".jpeg", ".png"))]
    except FileNotFoundError:
        return out
    for n in names:
        p = os.path.join(CAPTURES_DIR, n)
        try:
            st = os.stat(p)
        except OSError:
            continue
        out.append({"file": n, "url": "/shots/" + n,
                    "size": st.st_size, "mtime": st.st_mtime})
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter
        return

    # -- GET ----------------------------------------------------------------
    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith("/stream"):
            self.serve_stream()
        elif path == "/" or path.startswith("/?"):
            self.send_html(HTML)
        elif path == "/snap":
            self.serve_snap()
        elif path == "/shots":
            self.send_json({"shots": list_shots()})
        elif path == "/cdir":
            self.send_text(CAPTURES_DIR)
        elif path.startswith("/shots/"):
            self.serve_file(unquote(path[len("/shots/"):]))
        else:
            self.send_error(404)

    # -- POST ---------------------------------------------------------------
    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/save":
            self.handle_save()
        elif path == "/clear":
            self.handle_clear()
        else:
            self.send_error(404)

    # -- helpers ------------------------------------------------------------
    def send_html(self, data: str):
        b = data.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def send_text(self, data: str):
        b = data.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def send_json(self, obj: dict, code: int = 200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def serve_snap(self):
        jpg = grab_jpeg(HW)
        if not jpg:
            self.send_error(503, "camera capture failed")
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(jpg)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(jpg)

    def serve_file(self, name: str):
        # strict basename only — no path traversal
        name = os.path.basename(name)
        p = os.path.join(CAPTURES_DIR, name)
        if not name or not os.path.isfile(p):
            self.send_error(404)
            return
        with open(p, "rb") as fh:
            data = fh.read()
        ctype = "image/jpeg" if name.lower().endswith((".jpg", ".jpeg")) else "image/png"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def handle_save(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0:
            self.send_json({"error": "no data"}, 400)
            return
        data = self.rfile.read(length)
        name = "shot_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".jpg"
        with open(os.path.join(CAPTURES_DIR, name), "wb") as fh:
            fh.write(data)
        self.send_json({"file": name, "url": "/shots/" + name, "size": len(data)})

    def handle_clear(self):
        for n in list_shots():
            try:
                os.remove(os.path.join(CAPTURES_DIR, n["file"]))
            except OSError:
                pass
        self.send_json({"cleared": True})

    def serve_stream(self):
        self.send_response(200)
        self.send_header("Age", "0")
        self.send_header("Cache-Control", "no-store, private")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Type",
                         f"multipart/x-mixed-replace; boundary={BOUNDARY}")
        self.end_headers()
        last_sent = b""
        while True:
            jpg = grab_jpeg(HW)
            if jpg:
                last_sent = jpg
            elif not last_sent:
                time.sleep(0.5)
                continue
            part = (
                b"--" + BOUNDARY.encode() + b"\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(last_sent)).encode() + b"\r\n\r\n"
                + last_sent + b"\r\n"
            )
            try:
                self.wfile.write(part)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return  # client closed the tab


def main():
    ap = argparse.ArgumentParser(description="ESP32-CAM serial live view + capture.")
    ap.add_argument("--port", type=int, default=8001)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    global HW
    print("[liveview] opening ESP32-CAM serial connection...")
    HW = SerialHardware()          # uses config.SERIAL_PORT / SERIAL_BAUD
    print(f"[liveview] captures -> {CAPTURES_DIR}")
    print(f"[liveview] streaming on http://{args.host}:{args.port}  (Ctrl-C to quit)")

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[liveview] stopping.")
    finally:
        HW.close()


if __name__ == "__main__":
    main()
