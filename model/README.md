# Model folder

The backend loads a local model from here. You have **two easy options**:

## Option A — Google Teachable Machine (no code)
1. Go to <https://teachablemachine.withgoogle.com> → **Image Project → Standard**.
2. Create two classes: **Dry / Paper** and **Wet**. Add images to each
   (webcam or uploads — 100+ per class is a good start).
3. **Train**, then **Export Model → TensorFlow → Keras → Download**.
4. Unzip and copy the two files here, renaming if needed:
   - `keras_model.h5`
   - `labels.txt`

## Option B — Train locally (MobileNetV2)
See [`../train/train_model.py`](../train/train_model.py). It writes
`keras_model.h5` and `labels.txt` into this folder automatically.

---

**No model yet?** That's fine — the system still runs. Without a model the
backend uses a simple colour heuristic and the UI shows *“Heuristic (no model)”*
so you can test the whole pipeline before training.

`labels.txt` format (one per line, optional leading index):
```
0 Dry / Paper
1 Wet
```

> Files in this folder (`keras_model.h5`, `labels.txt`, `firebase_key.json`)
> are git-ignored so you don't commit large binaries or secrets.
