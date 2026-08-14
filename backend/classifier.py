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
    bin_confidence: float = 0.0   # how strongly the winning BIN won (see BIN_VOTE)


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
        self._text_pad: dict = {"padding": True}
        self._proto_feats = None     # [n_proto, d] example-photo vectors
        self._proto_idx: list[int] = []   # which class each prototype belongs to
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
            from transformers import AutoModel, AutoProcessor
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
            model = AutoModel.from_pretrained(config.CLIP_MODEL)
            processor = AutoProcessor.from_pretrained(config.CLIP_MODEL)
            model.to(device).eval()

            # SigLIP is a drop-in better backbone (same two-tower API) but its
            # text tower is trained with every sequence padded to a fixed 64
            # tokens. Pad dynamically instead and the embeddings come out
            # subtly wrong — it still "works", just worse, which is the most
            # annoying kind of bug. CLIP wants ordinary padding.
            is_siglip = "siglip" in config.CLIP_MODEL.lower()
            self._text_pad = {"padding": "max_length", "max_length": 64} \
                if is_siglip else {"padding": True}

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
                    tok = processor(text=text, return_tensors="pt", **self._text_pad)
                    tok = {k: v.to(device) for k, v in tok.items()}
                    f = model.get_text_features(**tok)
                    f = f / f.norm(dim=-1, keepdim=True)
                    f = f.mean(dim=0)
                    per_class.append(f / f.norm())
                feats = torch.stack(per_class)
                feats = self._blend_prototypes(feats, classes, model, processor,
                                               device, torch)
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

    # -- few-shot prototypes -------------------------------------------------
    @staticmethod
    def _class_key(name: str) -> str:
        """'Cable / wire' -> 'cable_wire', to match a filename prefix."""
        return name.lower().replace(" / ", "_").replace(" ", "_")

    def _blend_prototypes(self, text_feats, classes, model, processor,
                          device, torch):
        """Build "what this looks like on MY camera" vectors, if any exist.

        For each class we average the embeddings of the user's example photos.
        A text prompt describes the concept; the photos describe the concept
        *as this camera renders it*, which is the part CLIP cannot guess.

        THE CATCH — read before enabling. CLIP's image and text embeddings sit
        in different regions of the space (the "modality gap"), so a class
        holding a real photo scores far higher against a live frame than any
        text-only class can. Measured with photos for 2 of 27 classes: class
        accuracy 0/7 -> 7/7, but junk rejection collapsed 50% -> 0% and every
        score pinned to 1.00. The two classes with photos swallowed everything.

        Rescaling the two score distributions onto a common scale was tried and
        does not rescue it: with only a few prototype classes the statistics are
        too noisy to standardise against, and the signal vanishes instead
        (measured: back to 0/7, stationery confidence 0.27 -> 0.16).

        So this is deliberately all-or-nothing. With EVERY class covered the gap
        shifts all classes equally and the blend is both safe and very strong;
        with partial coverage it is refused unless you insist.
        """
        import glob
        import os

        import cv2

        weight = float(getattr(config, "PROTOTYPE_WEIGHT", 0.5))
        folder = getattr(config, "PROTOTYPE_DIR", "prototypes")
        if weight <= 0 or not folder:
            return text_feats
        if not os.path.isabs(folder):
            folder = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), folder)
        if not os.path.isdir(folder):
            return text_feats

        # Bucket the example photos by the class name their filename starts
        # with. Longest name first so "plastic_bottle_01" is not claimed by a
        # hypothetical "plastic" class.
        keys = sorted(((self._class_key(c["name"]), i) for i, c in enumerate(classes)),
                      key=lambda kv: len(kv[0]), reverse=True)
        buckets: dict[int, list] = {}
        for path in sorted(glob.glob(os.path.join(folder, "*"))):
            if not path.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            stem = os.path.basename(path).lower()
            for key, idx in keys:
                if stem.startswith(key):
                    img = cv2.imread(path)
                    if img is not None:
                        buckets.setdefault(idx, []).append(img)
                    break

        if not buckets:
            return text_feats

        proto_feats, proto_idx, used = [], [], []
        with torch.no_grad():
            for idx, images in sorted(buckets.items()):
                # Embed each example exactly the way a live frame is embedded —
                # same enhancement, same crops — or the prototype describes a
                # different pipeline than the one it will be compared against.
                views = []
                for img in images:
                    rgb = cv2.cvtColor(self._enhance(img), cv2.COLOR_BGR2RGB)
                    views.extend(self._views(rgb))
                inp = processor(images=views, return_tensors="pt")
                inp = {k: v.to(device) for k, v in inp.items()}
                f = model.get_image_features(**inp)
                f = f / f.norm(dim=-1, keepdim=True)
                f = f.mean(dim=0)
                proto_feats.append(f / f.norm())
                proto_idx.append(idx)
                used.append(f"{classes[idx]['name']}×{len(images)}")

        missing = [c["name"] for i, c in enumerate(classes) if i not in set(proto_idx)]
        if missing and not getattr(config, "PROTOTYPE_ALLOW_PARTIAL", False):
            print(f"[classifier] Ignoring example photos ({', '.join(used)}): "
                  f"{len(missing)} of {len(classes)} classes have none "
                  f"({', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}).")
            print("[classifier] Photos for only SOME classes make those classes "
                  "win everything. Add photos for every class, cut the classes "
                  "you will not demo, or set PROTOTYPE_ALLOW_PARTIAL=true.")
            return text_feats

        feats = text_feats.clone()
        for slot, idx in enumerate(proto_idx):
            blended = (1.0 - weight) * feats[idx] + weight * proto_feats[slot]
            feats[idx] = blended / blended.norm()
        print(f"[classifier] Few-shot prototypes (weight {weight}): {', '.join(used)}")
        if missing:
            print(f"[classifier] WARNING: partial coverage forced on. These "
                  f"classes have no photos and will rarely win: {', '.join(missing)}")
        return feats

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

    # -- camera compensation ------------------------------------------------
    @staticmethod
    def _enhance(bgr: np.ndarray) -> np.ndarray:
        """Undo the OV2640's colour cast and crushed dynamic range.

        CLIP's whole notion of "what a photo of X looks like" comes from normal
        photographs. A pink-tinted, half-black ESP32-CAM frame is off that
        distribution, so every class scores badly and the winner is close to
        arbitrary. Neutralising the cast and recovering local contrast costs
        under a millisecond and puts the frame back in familiar territory.
        """
        import cv2

        if not getattr(config, "AUTO_ENHANCE", True):
            return bgr

        # Grey-world white balance, applied at partial strength so genuinely
        # coloured objects keep their colour.
        img = bgr.astype(np.float32)
        means = img.reshape(-1, 3).mean(axis=0)
        gain = np.clip(means.mean() / np.maximum(means, 1e-3), 0.5, 2.0)
        gain = 1.0 + (gain - 1.0) * float(getattr(config, "WB_STRENGTH", 0.7))
        img = np.clip(img * gain, 0, 255).astype(np.uint8)

        # CLAHE on lightness only — colours untouched, shadows and glare opened.
        clip_limit = float(getattr(config, "CLAHE_CLIP", 2.0))
        if clip_limit > 0:
            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            l = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8)).apply(l)
            img = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
        return img

    @staticmethod
    def _views(rgb: np.ndarray) -> list[np.ndarray]:
        """Several ways of looking at one frame — see config.TTA_VIEWS."""
        n = max(1, int(getattr(config, "TTA_VIEWS", 4)))
        h, w = rgb.shape[:2]
        s = min(h, w)
        y0, x0 = (h - s) // 2, (w - s) // 2
        centre = rgb[y0:y0 + s, x0:x0 + s]
        views = [centre]

        if n >= 2:
            # Letterbox the whole frame into a square: the centre crop above
            # discards ~25% of a 320x240 frame, and items are often off-centre.
            pad = max(h, w)
            canvas = np.full((pad, pad, 3), 127, dtype=np.uint8)
            oy, ox = (pad - h) // 2, (pad - w) // 2
            canvas[oy:oy + h, ox:ox + w] = rgb
            views.append(canvas)
        if n >= 3:
            # Zoom: a pen in a 320x240 frame is a handful of pixels once CLIP
            # has downscaled to 224. Cropping in first makes it legible.
            z = int(s * 0.7)
            zy, zx = (h - z) // 2, (w - z) // 2
            views.append(rgb[zy:zy + z, zx:zx + z])
        if n >= 4:
            views.append(np.ascontiguousarray(centre[:, ::-1]))
        return views[:n]

    def _predict_clip(self, bgr: np.ndarray) -> Prediction:
        import cv2
        import torch

        rgb = cv2.cvtColor(self._enhance(bgr), cv2.COLOR_BGR2RGB)
        views = self._views(rgb)
        inp = self._processor(images=views, return_tensors="pt")
        inp = {k: v.to(self._device) for k, v in inp.items()}
        with torch.no_grad():
            img_feats = self._clip_model.get_image_features(**inp)
            img_feats = img_feats / img_feats.norm(dim=-1, keepdim=True)
            logits = (img_feats @ self._text_feats.T) * self._clip_model.logit_scale.exp()
            # Score each view separately, then average the PROBABILITIES.
            #
            # Averaging the embeddings instead would be tempting (it is what the
            # text side does) but it is wrong here: the mean of several views
            # points somewhere between them and matches every class a bit less,
            # which flattens the softmax. Measured: correct answers fell from
            # ~0.90 to ~0.49, gutting the margin the confidence threshold needs.
            # Per-view softmax keeps each view's own sharpness, and a view that
            # happens to miss the object simply contributes an unconfident vote.
            probs = logits.softmax(dim=-1).mean(dim=0).cpu().numpy()
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

            # Which BIN wins? Either the top class's bin, or a vote where each
            # bin is backed by its strongest few classes (see config.BIN_VOTE).
            if getattr(config, "BIN_VOTE", True):
                k = max(1, int(getattr(config, "BIN_VOTE_TOPK", 3)))
                per_bin: dict[str, list[float]] = {}
                for i, c in enumerate(classes):
                    per_bin.setdefault(c["bin"], []).append(float(probs[i]))
                bin_votes = {b: float(sum(sorted(v, reverse=True)[:k]))
                             for b, v in per_bin.items()}
                best_bin = max(bin_votes, key=bin_votes.get)
                bin_conf = bin_votes[best_bin]
                # Best class *within* the winning bin, so the label the user
                # reads always agrees with the chute the item goes down.
                idx = max((i for i in range(len(classes))
                           if classes[i]["bin"] == best_bin),
                          key=lambda i: probs[i])
            else:
                idx = int(np.argmax(probs))
                best_bin = classes[idx]["bin"]
                bin_conf = float(probs[idx])

            cls = classes[idx]
            conf = float(probs[idx])
            label_display = f"{cls['name']} \u00b7 {cls['category']}"
            if conf < config.CONFIDENCE_THRESHOLD:
                label_display += " (unsure)"
            return Prediction(
                label=label_display,
                bin=best_bin,
                confidence=conf,
                scores=scores,
                source=source,
                category=cls["category"],
                bin_confidence=bin_conf,
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
