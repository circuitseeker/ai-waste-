"""
Waste classifier — local zero-shot CLIP.

Runs OpenAI's CLIP entirely on this laptop (no cloud, no per-query API call).
The captured photo is scored against every concept in `config.WASTE_CLASSES`
and the best match wins, so it can recognise items it was never explicitly
trained on (a Pepsi can -> "Aluminium can, Recyclable, Dry").

Degradation chain, automatic:
  1. CLIP (default)            -> source = "clip"
  2. trained Keras model       -> source = "model"     (legacy, if present)
  3. colour heuristic          -> source = "heuristic" (always available)
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np

from . import config


@dataclass
class Prediction:
    label: str          # human label, e.g. "Aluminium can · Recyclable"
    bin: str            # physical bin command, e.g. "DRY"
    confidence: float   # 0..1
    scores: dict        # every class name -> score
    source: str         # "clip" | "model" | "heuristic"
    category: str = ""  # waste category, e.g. "Recyclable"


class Classifier:
    def __init__(self) -> None:
        self._ready = False
        self._source = "heuristic"
        # CLIP state
        self._clip_model = None
        self._processor = None
        self._text_feats = None      # normalized text embeddings [n_cls, d]
        self._classes: list[dict] = []
        self._device = "cpu"
        # legacy Keras state
        self._keras_model = None
        self._keras_labels: list[str] = []
        self._load()

    # -- loading -----------------------------------------------------------
    def _load(self) -> None:
        if self._load_clip():
            return
        print("[classifier] CLIP unavailable, trying legacy Keras model...")
        if self._load_keras():
            return
        print("[classifier] Nothing else available -> colour heuristic mode.")

    def _load_clip(self) -> bool:
        try:
            import torch
            from transformers import CLIPModel, CLIPProcessor
        except Exception as exc:  # noqa: BLE001
            print(f"[classifier] CLIP deps missing ({exc}) -> skipping CLIP.")
            return False

        classes = list(config.WASTE_CLASSES)
        if not classes:
            print("[classifier] config.WASTE_CLASSES is empty -> skipping CLIP.")
            return False

        # NVIDIA GPU (Windows/Linux) -> Apple Silicon -> CPU. CPU is fine here:
        # one photo per item, and the servo settle dominates the loop anyway.
        if torch.cuda.is_available():
            device = "cuda"
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"
        try:
            print(f"[classifier] Loading CLIP '{config.CLIP_MODEL}' "
                  f"(first run downloads the weights, cached thereafter)...")
            model = CLIPModel.from_pretrained(config.CLIP_MODEL)
            processor = CLIPProcessor.from_pretrained(config.CLIP_MODEL)
            model.to(device).eval()

            # Prompt ensembling: render every phrase of a class through every
            # template, embed them all, and average into ONE vector per class.
            # Averaging unit vectors then re-normalising is the standard CLIP
            # zero-shot recipe — it cancels phrasing quirks and measurably beat
            # single-sentence prompts on real ESP32-CAM frames here.
            templates = getattr(config, "PROMPT_TEMPLATES", ["a photo of {}"])
            with torch.no_grad():
                per_class = []
                for c in classes:
                    phrases = c.get("prompts") or [c["prompt"]]
                    text = [t.format(p) for p in phrases for t in templates]
                    tok = processor(text=text, padding=True, return_tensors="pt")
                    tok = {k: v.to(device) for k, v in tok.items()}
                    f = model.get_text_features(**tok)
                    f = f / f.norm(dim=-1, keepdim=True)
                    f = f.mean(dim=0)
                    per_class.append(f / f.norm())
                feats = torch.stack(per_class)
        except Exception as exc:  # noqa: BLE001
            print(f"[classifier] Could not load CLIP ({exc}) -> skipping CLIP.")
            return False

        self._clip_model = model
        self._processor = processor
        self._text_feats = feats
        self._classes = classes
        self._device = device
        self._ready = True
        self._source = "clip"
        names = [c["name"] for c in classes]
        print(f"[classifier] CLIP ready on '{device}' with {len(names)} classes: {names}")
        return True

    def _load_keras(self) -> bool:
        if not os.path.exists(config.MODEL_PATH):
            return False
        try:
            from tensorflow.keras.models import load_model  # type: ignore
            self._keras_model = load_model(config.MODEL_PATH, compile=False)
            self._keras_labels = self._read_labels()
            self._ready = True
            self._source = "model"
            print(f"[classifier] Loaded Keras model with labels: {self._keras_labels}")
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"[classifier] Could not load Keras model ({exc}).")
            return False

    def _read_labels(self) -> list[str]:
        if not os.path.exists(config.LABELS_PATH):
            return ["Dry / Paper", "Wet"]
        labels = []
        with open(config.LABELS_PATH, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(" ", 1)
                labels.append(parts[1] if len(parts) == 2 and parts[0].isdigit() else line)
        return labels or ["Dry / Paper", "Wet"]

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def source(self) -> str:
        return self._source

    @property
    def labels(self) -> list[str]:
        if self._source == "clip":
            return [c["name"] for c in self._classes]
        if self._source == "model":
            return self._keras_labels or ["Dry / Paper", "Wet"]
        return ["Dry / Paper", "Wet"]

    # -- inference ---------------------------------------------------------
    def predict(self, bgr_image: np.ndarray) -> Prediction:
        """bgr_image: an OpenCV BGR frame (H, W, 3)."""
        if self._source == "clip":
            return self._predict_clip(bgr_image)
        if self._source == "model":
            return self._predict_model(bgr_image)
        return self._predict_heuristic(bgr_image)

    def _predict_clip(self, bgr: np.ndarray) -> Prediction:
        import cv2
        import torch

        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        inp = self._processor(images=rgb, return_tensors="pt")
        inp = {k: v.to(self._device) for k, v in inp.items()}
        with torch.no_grad():
            img_feats = self._clip_model.get_image_features(**inp)
            img_feats = img_feats / img_feats.norm(dim=-1, keepdim=True)
            sims = (img_feats @ self._text_feats.T).squeeze(0)
            logits = sims * self._clip_model.logit_scale.exp()
            probs = logits.softmax(dim=-1).cpu().numpy()
        return self._to_prediction(probs, source="clip")

    def _predict_model(self, bgr: np.ndarray) -> Prediction:
        import cv2

        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (config.IMG_SIZE, config.IMG_SIZE))
        x = resized.astype("float32") / 255.0
        x = np.expand_dims(x, axis=0)
        probs = self._keras_model.predict(x, verbose=0)[0]
        return self._to_prediction(probs, source="model", labels=self._keras_labels)

    def _predict_heuristic(self, bgr: np.ndarray) -> Prediction:
        """No CLIP / no model? Rough colour guess so the demo still moves."""
        import cv2

        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        h, s, v = (hsv[..., i].mean() / 255.0 for i in range(3))
        wet_score = float(np.clip(0.5 + (s - 0.5) * 0.8 - (v - 0.5) * 0.4, 0.05, 0.95))
        probs = np.array([1.0 - wet_score, wet_score], dtype="float32")
        return self._to_prediction(probs, source="heuristic",
                                   labels=["Dry / Paper", "Wet"])

    # -- formatting --------------------------------------------------------
    def _to_prediction(self, probs, source: str, labels=None) -> Prediction:
        probs = np.asarray(probs, dtype="float32").ravel()

        if source == "clip":
            classes = self._classes
            if len(probs) != len(classes):
                labels = [f"class_{i}" for i in range(len(probs))]
                idx = int(np.argmax(probs))
                return Prediction(
                    label=labels[idx], bin=config.DEFAULT_BIN,
                    confidence=float(probs[idx]),
                    scores={labels[i]: float(probs[i]) for i in range(len(probs))},
                    source=source,
                )
            scores = {classes[i]["name"]: float(probs[i]) for i in range(len(probs))}
            idx = int(np.argmax(probs))
            cls = classes[idx]
            conf = float(probs[idx])
            label_display = f"{cls['name']} \u00b7 {cls['category']}"
            if conf < config.CONFIDENCE_THRESHOLD:
                label_display += " (unsure)"
            return Prediction(
                label=label_display,
                bin=cls["bin"],
                confidence=conf,
                scores=scores,
                source=source,
                category=cls["category"],
            )

        # Keras / heuristic path (label -> bin via config.BIN_MAP)
        labels = labels or self.labels
        if len(probs) != len(labels):
            labels = [f"class_{i}" for i in range(len(probs))]
        idx = int(np.argmax(probs))
        label = labels[idx]
        conf = float(probs[idx])
        bin_cmd = config.BIN_MAP.get(label, config.BIN_MAP.get(label.lower(), config.DEFAULT_BIN))
        label_display = label if conf >= config.CONFIDENCE_THRESHOLD else f"{label} (unsure)"
        return Prediction(
            label=label_display,
            bin=bin_cmd,
            confidence=conf,
            scores={labels[i]: float(probs[i]) for i in range(len(labels))},
            source=source,
        )
