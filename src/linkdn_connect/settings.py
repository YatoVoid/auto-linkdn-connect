from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .hotkey import KEYS
from .platform_info import is_windows


@dataclass
class Settings:
    max_invites: int = 30
    pause_min: float = 3.0
    pause_max: float = 7.0
    threshold: float = 0.75
    hotkey: str = "F8"
    scroll_clicks: int = 5
    monitor: int = 1
    connect_image: str = ""
    send_image: str = ""
    more_image: str = ""

    def normalized(self) -> "Settings":
        s = Settings(**asdict(self))
        s.max_invites = min(max(int(s.max_invites), 1), 500)
        s.pause_min = min(max(float(s.pause_min), 0.5), 120.0)
        s.pause_max = min(max(float(s.pause_max), s.pause_min), 180.0)
        s.threshold = min(max(float(s.threshold), 0.5), 0.98)
        s.scroll_clicks = min(max(int(s.scroll_clicks), 1), 20)
        s.monitor = max(int(s.monitor), 1)
        if s.hotkey not in KEYS:
            s.hotkey = "F8"
        return s


def config_path() -> Path:
    if is_windows():
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "linkdn-connect" / "settings.json"


def load(path: Path | None = None) -> Settings:
    path = path or config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    known = {f.name for f in fields(Settings)}
    try:
        return Settings(**{k: v for k, v in raw.items() if k in known}).normalized()
    except (TypeError, ValueError):
        return Settings()


def save(settings: Settings, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(settings.normalized()), indent=2), encoding="utf-8")
