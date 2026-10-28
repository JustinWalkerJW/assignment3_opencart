"""Real PNG evidence and a machine-readable record; never synthesize screenshots."""

import json
import re
from dataclasses import asdict
from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class Evidence:
    def __init__(self, folder, scenario_id):
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)
        self.scenario_id = scenario_id
        self.driver = None
        self.images = []
        self.events = []
        self.warnings = []
        self.environment = {}

    def record(self, action, **details):
        self.events.append({"time_utc": utc_now(), "action": action, **details})

    def capture(self, label, element=None):
        if self.driver is None:
            raise RuntimeError("Browser unavailable; no screenshot can be captured")
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", label)
        path = self.folder / f"{len(self.images) + 1:02d}_{safe}.png"
        saved = (self.driver.save_screenshot(str(path)) if element is None
                 else element.screenshot(str(path)))
        if not saved or not path.is_file() or path.stat().st_size == 0:
            raise OSError(f"Screenshot not saved: {path}")
        self.images.append(path.name)
        self.record("screenshot", file=path.name, url=self.driver.current_url)

    def cart(self, shop, label):
        # Include all main-content quantities/totals, even below the viewport.
        self.record(label, cart_state=asdict(shop.snapshot()))
        self.capture(label, element=shop.content())

    def write(self, result):
        payload = {**result, "scenario_id": self.scenario_id,
                   "environment": self.environment, "screenshots": self.images,
                   "events": self.events, "warnings": self.warnings}
        (self.folder / "result.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
