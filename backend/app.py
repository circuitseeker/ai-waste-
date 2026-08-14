"""
AI Waste Segregation — local server.

Runs on your Mac or Windows laptop. It:
  1. serves the web dashboard (single origin, no CORS headaches),
  2. runs the local ML model inference,
  3. runs the control loop that talks to the ESP32-CAM,
  4. streams live events to the browser over a WebSocket.

Run it with:   python -m backend.app        (from the project root)
Then open:     http://127.0.0.1:8000
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import json
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import config
from .classifier import Classifier
from .firebase_logger import FirebaseLogger
from .hardware import make_hardware

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="AI Waste Segregation")


# ---------------------------------------------------------------------------
# Shared application state
# ---------------------------------------------------------------------------
class State:
    def __init__(self) -> None:
        self.classifier = Classifier()
        self.hardware = make_hardware()
        self.firebase = FirebaseLogger()
        self.counts: dict[str, int] = {}
        self.history: list[dict] = []
        self.running = True          # control loop enabled?
        self.busy = False            # currently processing an item?
        self.clients: set[WebSocket] = set()
        self.last_event: dict | None = None

    def status(self) -> dict:
        return {
            "type": "status",
            "hardware_mode": self.hardware.mode,
            "model_source": self.classifier.source,
            "labels": self.classifier.labels,
            "running": self.running,
            "busy": self.busy,
            "counts": self.counts,
            "firebase": self.firebase.enabled,
        }


state: State | None = None


# ---------------------------------------------------------------------------
# WebSocket broadcast
# ---------------------------------------------------------------------------
async def broadcast(message: dict) -> None:
    assert state is not None
    dead = []
    data = json.dumps(message)
    for ws in list(state.clients):
        try:
            await ws.send_text(data)
        except Exception:  # noqa: BLE001
            dead.append(ws)
    for ws in dead:
        state.clients.discard(ws)


# ---------------------------------------------------------------------------
# The control loop: detect -> capture -> classify -> divert -> log
# ---------------------------------------------------------------------------
async def process_item() -> None:
    assert state is not None
    state.busy = True
    await broadcast({"type": "processing"})
    try:
        loop = asyncio.get_running_loop()
        frame = await loop.run_in_executor(None, state.hardware.capture)
        pred = await loop.run_in_executor(None, state.classifier.predict, frame)

        # "Not waste" frames (empty belt, a hand, background clutter) must not
        # move the servo or inflate the counters — the classifier decided there
        # is nothing to sort, so treat this as a no-op observation.
        no_item = pred.bin == getattr(config, "NO_ITEM_BIN", "NONE")

        if not no_item:
            # Drive the physical bin.
            await loop.run_in_executor(None, state.hardware.send_result, pred.bin)
            state.counts[pred.bin] = state.counts.get(pred.bin, 0) + 1

        event = {
            "type": "result",
            "label": pred.label,
            "bin": pred.bin,
            "no_item": no_item,
            "confidence": round(pred.confidence, 4),
            "scores": {k: round(v, 4) for k, v in pred.scores.items()},
            "source": pred.source,
            "time": dt.datetime.now().isoformat(timespec="seconds"),
            "counts": dict(state.counts),
        }
        state.last_event = event
        state.history.insert(0, event)
        state.history = state.history[:50]

        await broadcast(event)
        state.firebase.log_event(event)
        state.firebase.update_counts(state.counts)
    except Exception as exc:  # noqa: BLE001
        await broadcast({"type": "error", "message": str(exc)})
    finally:
        # brief settle time so the belt/servo can finish before the next item
        await asyncio.sleep(1.0)
        state.busy = False
        await broadcast(state.status())


async def control_loop() -> None:
    assert state is not None
    while True:
        try:
            if state.running and not state.busy:
                loop = asyncio.get_running_loop()
                present = await loop.run_in_executor(None, state.hardware.object_present)
                if present:
                    await process_item()
        except Exception as exc:  # noqa: BLE001
            await broadcast({"type": "error", "message": f"loop: {exc}"})
        await asyncio.sleep(config.POLL_INTERVAL_S)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def _startup() -> None:
    global state
    state = State()
    app.state.loop_task = asyncio.create_task(control_loop())
    print(f"[app] Ready on http://{config.HOST}:{config.PORT}")


@app.on_event("shutdown")
async def _shutdown() -> None:
    task = getattr(app.state, "loop_task", None)
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    if state:
        state.hardware.close()


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------
@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/status")
async def api_status() -> dict:
    assert state is not None
    return state.status()


@app.get("/api/history")
async def api_history() -> dict:
    assert state is not None
    return {"history": state.history}


@app.get("/api/snapshot")
async def api_snapshot() -> Response:
    """Proxy a fresh JPEG from the camera so the browser stays single-origin."""
    assert state is not None
    loop = asyncio.get_running_loop()
    jpeg = await loop.run_in_executor(None, state.hardware.snapshot_jpeg)
    if not jpeg:
        return Response(status_code=503)
    return Response(content=jpeg, media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


@app.post("/api/control/{action}")
async def api_control(action: str) -> dict:
    """pause | resume | reset | trigger"""
    assert state is not None
    if action == "pause":
        state.running = False
    elif action == "resume":
        state.running = True
    elif action == "reset":
        state.counts = {}
        state.history = []
    elif action == "trigger":            # manual "an item arrived" for testing
        if not state.busy:
            asyncio.create_task(process_item())
    await broadcast(state.status())
    return state.status()


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    assert state is not None
    await ws.accept()
    state.clients.add(ws)
    await ws.send_text(json.dumps(state.status()))
    if state.last_event:
        await ws.send_text(json.dumps(state.last_event))
    try:
        while True:
            await ws.receive_text()   # we don't expect messages; keeps it open
    except WebSocketDisconnect:
        pass
    finally:
        state.clients.discard(ws)


# Static assets (css/js). Mounted last so it doesn't shadow the API routes.
app.mount("/", StaticFiles(directory=str(WEB_DIR)), name="web")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app:app", host=config.HOST, port=config.PORT, reload=False)
