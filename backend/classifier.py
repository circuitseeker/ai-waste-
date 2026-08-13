"""
Waste classifier — loads a local Keras model and predicts Dry vs Wet.

Designed to run on an ordinary Mac or Windows laptop CPU. Works with any model
exported from Google Teachable Machine ("TensorFlow / Keras") or trained with
train/train_model.py (MobileNetV2 transfer learning).

If TensorFlow or a trained model isn't available yet, it degrades gracefully to
a lightweight colour-heuristic so the rest of the system still runs.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np

from . import config


@dataclass
class Prediction:
    label: str          # human label, e.g. "Wet"
    bin: str            # physical bin command, e.g. "WET"
    confidence: float   # 0..1
    scores: dict        # every label -> score
    source: str         # "model" | "heuristic"


class Classifier:
    def __init__(self) -> None:
        self._model = None
        self._labels: list[str] = []
        self._ready = False
        self._load()

    # -- loading -----------------------------------------------------------
    def _load(self) -> None:
        model_ok = os.path.exists(config.MODEL_PATH)
        if not model_ok:
            print(f"[classifier] No model at {config.MODEL_PATH} -> heuristic mode.")
            return
        try:
            # Imported lazily so the app still starts without TensorFlow.
            from tensorflow.keras.models import load_model  # type: ignore

            self._model = load_model(config.MODEL_PATH, compile=False)
            self._labels = self._read_labels()
            self._ready = True
            print(f"[classifier] Loaded model with labels: {self._labels}")
        except Exception as exc:  # noqa: BLE001
            print(f"[classifier] Could not load model ({exc}) -> heuristic mode.")

    def _read_labels(self) -> list[str]:
        if not os.path.exists(config.LABELS_PATH):
            return ["Dry / Paper", "Wet"]
        labels = []
        with open(config.LABELS_PATH, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                # Teachable Machine writes "0 Dry", strip the leading index.
                parts = line.split(" ", 1)
                labels.append(parts[1] if len(parts) == 2 and parts[0].isdigit() else line)
        return labels or ["Dry / Paper", "Wet"]

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def labels(self) -> list[str]:
        return self._labels or ["Dry / Paper", "Wet"]

    # -- inference ---------------------------------------------------------
    def predict(self, bgr_image: np.ndarray) -> Prediction:
        """bgr_image: an OpenCV BGR frame (H, W, 3)."""
        if self._ready:
            return self._predict_model(bgr_image)
        return self._predict_heuristic(bgr_image)

    def _predict_model(self, bgr: np.ndarray) -> Prediction:
        import cv2  # local import keeps module import cheap

        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (config.IMG_SIZE, config.IMG_SIZE))
        x = resized.astype("float32") / 255.0
        x = np.expand_dims(x, axis=0)
        probs = self._model.predict(x, verbose=0)[0]
        return self._to_prediction(probs, source="model")

    def _predict_heuristic(self, bgr: np.ndarray) -> Prediction:
        """
        No model yet? Make a rough guess from colour so the demo still moves:
        greener / darker, saturated frames lean 'Wet' (organic), brighter and
        less saturated lean 'Dry / Paper'. This is ONLY a placeholder.
        """
        import cv2

        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        h, s, v = (hsv[..., i].mean() / 255.0 for i in range(3))
        wet_score = float(np.clip(0.5 + (s - 0.5) * 0.8 - (v - 0.5) * 0.4, 0.05, 0.95))
        probs = np.array([1.0 - wet_score, wet_score], dtype="float32")
        return self._to_prediction(probs, source="heuristic",
                                   labels=["Dry / Paper", "Wet"])

    def _to_prediction(self, probs, source: str, labels=None) -> Prediction:
        labels = labels or self.labels
        probs = np.asarray(probs, dtype="float32").ravel()
        if len(probs) != len(labels):  # be forgiving about label/model mismatch
            labels = [f"class_{i}" for i in range(len(probs))]
        idx = int(np.argmax(probs))
        label = labels[idx]
        conf = float(probs[idx])
        bin_cmd = config.BIN_MAP.get(label, config.BIN_MAP.get(label.lower(), config.DEFAULT_BIN))
        if conf < config.CONFIDENCE_THRESHOLD:
            label_display = f"{label} (unsure)"
        else:
            label_display = label
        return Prediction(
            label=label_display,
            bin=bin_cmd,
            confidence=conf,
            scores={labels[i]: float(probs[i]) for i in range(len(labels))},
            source=source,
        )
