from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .platform_info import is_wayland


class ScreenError(RuntimeError):
    pass


@dataclass
class Frame:
    image: np.ndarray
    left: int = 0
    top: int = 0
    scale: float = 1.0

    @property
    def size(self) -> tuple[int, int]:
        return self.image.shape[1], self.image.shape[0]


def _check_not_blank(image: np.ndarray) -> None:
    if not image.any():
        raise ScreenError(
            "The screen capture is completely black. On Linux this means the session is "
            "Wayland and the capture tool cannot see it."
        )


class MssScreen:
    """Windows and X11. The grabber is created lazily so it lives in the thread that uses it."""

    def __init__(self, monitor: int = 1):
        self.monitor = monitor
        self._sct = None

    def grab(self) -> Frame:
        import mss

        if self._sct is None:
            self._sct = mss.MSS() if hasattr(mss, "MSS") else mss.mss()
        monitors = self._sct.monitors
        if not 1 <= self.monitor < len(monitors):
            raise ScreenError(f"Monitor {self.monitor} does not exist, found {len(monitors) - 1}.")
        area = monitors[self.monitor]
        shot = self._sct.grab(area)
        image = cv2.cvtColor(np.asarray(shot), cv2.COLOR_BGRA2BGR)
        _check_not_blank(image)
        scale = image.shape[1] / area["width"] if area["width"] else 1.0
        return Frame(image, area["left"], area["top"], scale)

    def close(self) -> None:
        if self._sct is not None:
            self._sct.close()
            self._sct = None


_TOOLS = {
    "grim": lambda out: ["grim", out],
    "spectacle": lambda out: ["spectacle", "-b", "-n", "-f", "-o", out],
    "gnome-screenshot": lambda out: ["gnome-screenshot", "-f", out],
}


class CommandScreen:
    """Wayland. Asks a screenshot tool for the whole desktop."""

    def __init__(self, tool: str):
        self.tool = tool
        self._dir = Path(tempfile.mkdtemp(prefix="linkdn-"))

    def grab(self) -> Frame:
        out = self._dir / "shot.png"
        out.unlink(missing_ok=True)
        try:
            subprocess.run(_TOOLS[self.tool](str(out)), check=True, timeout=15, capture_output=True)
        except (subprocess.SubprocessError, OSError) as exc:
            raise ScreenError(f"{self.tool} failed: {exc}") from exc
        image = cv2.imread(str(out), cv2.IMREAD_COLOR)
        out.unlink(missing_ok=True)
        if image is None:
            raise ScreenError(f"{self.tool} did not produce a screenshot.")
        _check_not_blank(image)
        return Frame(image, 0, 0)

    def close(self) -> None:
        shutil.rmtree(self._dir, ignore_errors=True)


def create_screen(monitor: int = 1):
    if not is_wayland():
        return MssScreen(monitor)
    for tool in _TOOLS:
        if shutil.which(tool):
            return CommandScreen(tool)
    raise ScreenError(
        "This is a Wayland session and no screenshot tool was found. "
        "Install grim, spectacle or gnome-screenshot."
    )
