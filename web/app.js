// Front-end for the AI Waste Segregation dashboard.
// Talks to the local FastAPI backend over WebSocket + a few REST calls.

const $ = (id) => document.getElementById(id);

const el = {
  pillHardware: $("pill-hardware"),
  pillModel: $("pill-model"),
  pillConn: $("pill-conn"),
  camSource: $("cam-source"),
  cam: $("cam"),
  overlay: $("cam-overlay"),
  resultIcon: $("result-icon"),
  resultLabel: $("result-label"),
  confFill: $("confbar-fill"),
  confText: $("conf-text"),
  resultTime: $("result-time"),
  countDry: $("count-dry"),
  countWet: $("count-wet"),
  countTotal: $("count-total"),
  btnToggle: $("btn-toggle"),
  btnTrigger: $("btn-trigger"),
  btnReset: $("btn-reset"),
  hint: $("hint"),
  history: $("history"),
};

let running = true;

// ---------- Live camera (polled snapshots) ----------
function refreshCamera() {
  el.cam.src = `/api/snapshot?t=${Date.now()}`;
}
el.cam.addEventListener("error", () => {
  // keep trying; hardware/model may still be warming up
});
setInterval(refreshCamera, 900);
refreshCamera();

// ---------- WebSocket ----------
let ws;
function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => setConn(true);
  ws.onclose = () => { setConn(false); setTimeout(connect, 1500); };
  ws.onmessage = (e) => handle(JSON.parse(e.data));
}

function setConn(ok) {
  el.pillConn.textContent = ok ? "● Live" : "Reconnecting…";
  el.pillConn.className = "pill " + (ok ? "pill-live" : "pill-warn");
}

function handle(msg) {
  switch (msg.type) {
    case "status": applyStatus(msg); break;
    case "processing": showScanning(); break;
    case "result": showResult(msg); break;
    case "error": el.hint.textContent = "⚠ " + msg.message; break;
  }
}

function applyStatus(s) {
  running = s.running;
  el.btnToggle.textContent = running ? "Pause" : "Resume";

  el.pillHardware.textContent =
    s.hardware_mode === "esp32" ? "ESP32-CAM connected" : "Simulation mode";
  el.pillHardware.className =
    "pill " + (s.hardware_mode === "esp32" ? "pill-ok" : "pill-warn");
  el.camSource.textContent =
    s.hardware_mode === "esp32" ? "ESP32-CAM" : "Simulated";

  el.pillModel.textContent =
    s.model_source === "model" ? "Local model loaded" : "Heuristic (no model)";
  el.pillModel.className =
    "pill " + (s.model_source === "model" ? "pill-ok" : "pill-warn");

  if (s.counts) updateCounts(s.counts);

  if (s.hardware_mode !== "esp32") {
    el.hint.textContent =
      "No ESP32 detected — running in simulation. Use “Simulate Item” to test the flow.";
  } else if (s.model_source !== "model") {
    el.hint.textContent =
      "ESP32 connected, but no trained model found. Drop a model into model/ (see model/README).";
  } else {
    el.hint.textContent = "System ready.";
  }
}

function showScanning() {
  el.overlay.className = "cam-overlay scanning";
  el.resultIcon.textContent = "🔍";
  el.resultLabel.textContent = "Scanning…";
  el.confFill.style.width = "0%";
  el.confText.textContent = "—";
}

function binKind(bin) { return bin === "WET" ? "wet" : "dry"; }

function showResult(r) {
  const kind = binKind(r.bin);
  const isWet = kind === "wet";

  el.overlay.className = "cam-overlay " + kind;
  el.resultIcon.textContent = isWet ? "🍎" : "📄";
  el.resultIcon.classList.remove("pop");
  void el.resultIcon.offsetWidth;            // restart animation
  el.resultIcon.classList.add("pop");

  el.resultLabel.textContent = r.label;

  const pct = Math.round(r.confidence * 100);
  el.confFill.style.width = pct + "%";
  el.confFill.style.background = isWet
    ? "var(--wet)" : "var(--dry)";
  el.confText.textContent =
    `${pct}% confidence · ${r.source === "model" ? "local model" : "heuristic"}`;
  el.resultTime.textContent = r.time.replace("T", " ");

  if (r.counts) updateCounts(r.counts);
  addHistory(r);
}

function updateCounts(counts) {
  const dry = counts.DRY || 0;
  const wet = counts.WET || 0;
  el.countDry.textContent = dry;
  el.countWet.textContent = wet;
  el.countTotal.textContent = dry + wet;
}

function addHistory(r) {
  const empty = el.history.querySelector(".history-empty");
  if (empty) empty.remove();
  const kind = binKind(r.bin);
  const li = document.createElement("li");
  li.innerHTML =
    `<span class="dot ${kind}"></span>` +
    `<span class="h-label">${r.label}</span>` +
    `<span class="h-conf">${Math.round(r.confidence * 100)}%</span>` +
    `<span class="h-time">${r.time.split("T")[1] || ""}</span>`;
  el.history.prepend(li);
  while (el.history.children.length > 30) el.history.lastChild.remove();
}

// ---------- Controls ----------
async function control(action) {
  await fetch(`/api/control/${action}`, { method: "POST" });
}
el.btnToggle.onclick = () => control(running ? "pause" : "resume");
el.btnTrigger.onclick = () => control("trigger");
el.btnReset.onclick = () => {
  control("reset");
  updateCounts({});
  el.history.innerHTML = '<li class="history-empty">No activity yet.</li>';
};

// Load any history the server already has, then connect live.
fetch("/api/history")
  .then((r) => r.json())
  .then((d) => (d.history || []).slice().reverse().forEach(addHistory))
  .catch(() => {});

connect();
