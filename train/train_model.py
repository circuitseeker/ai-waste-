"""
Train a Dry-vs-Wet waste classifier with MobileNetV2 transfer learning.

Runs on a plain Mac/Windows laptop CPU (a few minutes for a small dataset).
Produces model/keras_model.h5 + model/labels.txt that the backend loads
automatically.

DATA LAYOUT — put images into class folders:

    train/data/
        Dry_Paper/    img1.jpg img2.jpg ...
        Wet/          img1.jpg img2.jpg ...

You can seed Dry_Paper from the public TrashNet dataset (paper/cardboard/
plastic/metal/glass) and capture your own Wet (food/organic) photos with the
ESP32-CAM so lighting matches. ~150+ images per class is a reasonable start.

USAGE:
    pip install tensorflow            # or tensorflow-macos on Apple Silicon
    python train/train_model.py
"""
import pathlib

import tensorflow as tf
from tensorflow.keras import layers, models

DATA_DIR = pathlib.Path(__file__).parent / "data"
OUT_DIR = pathlib.Path(__file__).parent.parent / "model"
IMG_SIZE = 224
BATCH = 16
EPOCHS = 12


def load_datasets():
    train_ds = tf.keras.utils.image_dataset_from_directory(
        DATA_DIR, validation_split=0.2, subset="training", seed=123,
        image_size=(IMG_SIZE, IMG_SIZE), batch_size=BATCH)
    val_ds = tf.keras.utils.image_dataset_from_directory(
        DATA_DIR, validation_split=0.2, subset="validation", seed=123,
        image_size=(IMG_SIZE, IMG_SIZE), batch_size=BATCH)
    class_names = train_ds.class_names
    autotune = tf.data.AUTOTUNE
    return (train_ds.prefetch(autotune), val_ds.prefetch(autotune), class_names)


def build_model(num_classes: int) -> tf.keras.Model:
    base = tf.keras.applications.MobileNetV2(
        input_shape=(IMG_SIZE, IMG_SIZE, 3), include_top=False, weights="imagenet")
    base.trainable = False  # transfer learning: freeze the backbone

    augment = tf.keras.Sequential([
        layers.RandomFlip("horizontal"),
        layers.RandomRotation(0.1),
        layers.RandomBrightness(0.15),
    ])

    inputs = tf.keras.Input(shape=(IMG_SIZE, IMG_SIZE, 3))
    x = augment(inputs)
    x = layers.Rescaling(1.0 / 255)(x)
    x = base(x, training=False)
    x = layers.GlobalAveragePooling2D()(x)
    x = layers.Dropout(0.2)(x)
    outputs = layers.Dense(num_classes, activation="softmax")(x)

    model = models.Model(inputs, outputs)
    model.compile(optimizer="adam",
                  loss="sparse_categorical_crossentropy",
                  metrics=["accuracy"])
    return model


def main() -> None:
    if not DATA_DIR.exists():
        raise SystemExit(f"Put class folders of images in: {DATA_DIR}")

    train_ds, val_ds, class_names = load_datasets()
    print("Classes:", class_names)

    model = build_model(len(class_names))
    model.fit(train_ds, validation_data=val_ds, epochs=EPOCHS)

    OUT_DIR.mkdir(exist_ok=True)
    model.save(OUT_DIR / "keras_model.h5")
    with open(OUT_DIR / "labels.txt", "w", encoding="utf-8") as fh:
        for i, name in enumerate(class_names):
            fh.write(f"{i} {name.replace('_', ' / ')}\n")

    print(f"\nSaved model to {OUT_DIR/'keras_model.h5'}")
    print(f"Saved labels to {OUT_DIR/'labels.txt'}")


if __name__ == "__main__":
    main()
