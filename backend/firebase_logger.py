"""
Optional Firebase Realtime Database logging.

Completely optional: if FIREBASE_ENABLED is false (default) this is a no-op, so
the system runs fine without any cloud account. Enable it in config.py once you
have a Firebase project + service-account key.
"""
from __future__ import annotations

from . import config


class FirebaseLogger:
    def __init__(self) -> None:
        self._db = None
        if not config.FIREBASE_ENABLED:
            return
        try:
            import firebase_admin
            from firebase_admin import credentials, db

            cred = credentials.Certificate(config.FIREBASE_KEY_PATH)
            firebase_admin.initialize_app(cred, {"databaseURL": config.FIREBASE_DB_URL})
            self._db = db
            print("[firebase] Connected.")
        except Exception as exc:  # noqa: BLE001
            print(f"[firebase] Disabled ({exc}).")

    @property
    def enabled(self) -> bool:
        return self._db is not None

    def log_event(self, event: dict) -> None:
        if self._db is None:
            return
        try:
            self._db.reference("waste_system/log").push(event)
            self._db.reference("waste_system/live").update({
                "last_type": event.get("bin"),
                "last_confidence": event.get("confidence"),
                "updated_at": event.get("time"),
            })
        except Exception as exc:  # noqa: BLE001
            print(f"[firebase] log failed: {exc}")

    def update_counts(self, counts: dict) -> None:
        if self._db is None:
            return
        try:
            self._db.reference("waste_system/counts").set(counts)
        except Exception as exc:  # noqa: BLE001
            print(f"[firebase] counts failed: {exc}")
