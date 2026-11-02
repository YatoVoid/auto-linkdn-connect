from __future__ import annotations

import math
import random
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable

import cv2
import numpy as np

from .settings import Settings
from .vision import Finder, Match, Template

DIALOG_TIMEOUT = 4.0
POLL = 0.5
CLOSE_SETTLE = 1.0
SCROLL_SETTLE = 1.2
SCROLL_RETRY_WAIT = 1.5
SCROLL_TRIES = 3
MAX_FAIL_STREAK = 4
STUCK_RADIUS = 20
HAND_MOVE_LIMIT = 40
MOVED_THRESHOLD = 1.5


class Outcome(Enum):
    SENT = "sent"
    FAILED = "failed"


class Stopped(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class SystemClock:
    def __init__(self, stop: threading.Event):
        self._stop = stop

    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        self._stop.wait(seconds)


@dataclass
class Callbacks:
    log: Callable[[str], None] = lambda text: None
    progress: Callable[[int], None] = lambda sent: None


def _gray_small(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    width = 320
    height = max(1, round(gray.shape[0] * width / gray.shape[1]))
    return cv2.resize(gray, (width, height), interpolation=cv2.INTER_AREA)


def screen_changed(before: np.ndarray, after: np.ndarray) -> bool:
    if before.shape != after.shape:
        return True
    a, b = _gray_small(before), _gray_small(after)
    return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean()) > MOVED_THRESHOLD


class Engine:
    def __init__(
        self,
        settings: Settings,
        screen,
        pointer,
        connect: Template,
        send: Template,
        stop: threading.Event,
        callbacks: Callbacks | None = None,
        clock=None,
        rng: random.Random | None = None,
    ):
        self.s = settings.normalized()
        self.screen = screen
        self.pointer = pointer
        self.connect = connect
        self.send = send
        self.stop = stop
        self.cb = callbacks or Callbacks()
        self.clock = clock or SystemClock(stop)
        self.rng = rng or random.Random()
        self.finder = Finder()
        self.sent = 0
        self._origin = (0, 0)
        self._scale = 1.0
        self._expected: tuple[int, int] | None = None
        self._stuck: list[tuple[int, int]] = []

    def _check(self) -> None:
        if self.stop.is_set():
            raise Stopped("Stopped.")
        if self._expected is None:
            return
        pos = self.pointer.position()
        if pos is not None and math.dist(pos, self._expected) > HAND_MOVE_LIMIT:
            raise Stopped("Stopped because the mouse was moved.")

    def _wait(self, seconds: float) -> None:
        self.clock.sleep(seconds)
        self._check()

    def _grab(self):
        frame = self.screen.grab()
        self._origin = (frame.left, frame.top)
        self._scale = frame.scale
        self.pointer.configure(*frame.size)
        return frame

    def _desktop(self, point: tuple[int, int]) -> tuple[int, int]:
        """Image pixels to desktop coordinates. They differ on high-density macOS screens."""
        return round(point[0] / self._scale) + self._origin[0], round(point[1] / self._scale) + self._origin[1]

    def _click_at(self, point: tuple[int, int], box: Match) -> None:
        jitter_x = int(box.w * 0.25)
        jitter_y = int(box.h * 0.2)
        target = (
            point[0] + self.rng.randint(-jitter_x, jitter_x),
            point[1] + self.rng.randint(-jitter_y, jitter_y),
        )
        x, y = self._desktop(target)
        self.pointer.move_to(x, y)
        self._expected = (x, y)
        self.pointer.click()

    def _visible(self, image: np.ndarray, template: Template, threshold: float | None = None) -> list[Match]:
        return self.finder.find(image, template, threshold or self.s.threshold)

    def _is_stuck(self, match: Match) -> bool:
        cx, cy = match.center
        return any(math.dist((cx, cy), p) <= STUCK_RADIUS for p in self._stuck)

    def _invite(self, match: Match) -> Outcome:
        self._click_at(match.center, match)
        deadline = self.clock.now() + DIALOG_TIMEOUT
        send_button = None
        while self.clock.now() < deadline:
            self._wait(POLL)
            frame = self._grab()
            found = self._visible(frame.image, self.send)
            if found:
                send_button = found[0]
                break

        if send_button is not None:
            self._click_at(send_button.center, send_button)
            self._wait(CLOSE_SETTLE)
            frame = self._grab()
            if self._visible(frame.image, self.send):
                self.pointer.escape()
                self._wait(CLOSE_SETTLE)
                return Outcome.FAILED
            return Outcome.SENT

        self.pointer.escape()
        self._wait(CLOSE_SETTLE)
        frame = self._grab()
        still_there = any(
            math.dist(m.center, match.center) <= STUCK_RADIUS for m in self._visible(frame.image, self.connect)
        )
        return Outcome.FAILED if still_there else Outcome.SENT

    def _scroll(self, before: np.ndarray):
        """Scrolls one step and returns the new frame, or None once the page stops moving."""
        h, w = before.shape[:2]
        for attempt in range(SCROLL_TRIES):
            x, y = self._desktop((w // 2, h // 2))
            self.pointer.move_to(x, y)
            self._expected = (x, y)
            self.pointer.scroll_down(self.s.scroll_clicks)
            self._wait(SCROLL_SETTLE if attempt == 0 else SCROLL_RETRY_WAIT)
            after = self._grab()
            if screen_changed(before, after.image):
                return after
        return None

    def run(self) -> str:
        reason = "Done."
        fail_streak = 0
        try:
            frame = self._grab()
            while True:
                self._check()
                if self.sent >= self.s.max_invites:
                    reason = f"Reached the limit of {self.s.max_invites} invitations."
                    break

                candidates = [m for m in self._visible(frame.image, self.connect) if not self._is_stuck(m)]
                if candidates:
                    match = candidates[0]
                    outcome = self._invite(match)
                    if outcome is Outcome.SENT:
                        self.sent += 1
                        fail_streak = 0
                        self.cb.progress(self.sent)
                        self.cb.log(f"Invitation {self.sent} sent.")
                        if self.sent < self.s.max_invites:
                            self._wait(self.rng.uniform(self.s.pause_min, self.s.pause_max))
                    else:
                        fail_streak += 1
                        self._stuck.append(match.center)
                        self.cb.log("A Connect button did not lead to the expected dialog. Skipped it.")
                        if fail_streak >= MAX_FAIL_STREAK:
                            reason = (
                                f"Stopped after {MAX_FAIL_STREAK} failed attempts in a row. "
                                "LinkedIn may be showing a limit or a different dialog."
                            )
                            break
                    frame = self._grab()
                    continue

                self.cb.log("No Connect button on screen. Scrolling down.")
                scrolled = self._scroll(frame.image)
                if scrolled is None:
                    reason = "Reached the end of the page."
                    break
                self._stuck.clear()
                frame = scrolled
        except Stopped as stopped:
            reason = stopped.reason
        return reason

    def detect_once(self) -> list[str]:
        """Reports what the matcher sees, including near misses, without clicking."""
        frame = self._grab()
        finder = Finder()
        lines = []
        for label, template in (("Connect", self.connect), ("Send without a note", self.send)):
            found = finder.find(frame.image, template, 0.5)
            accepted = [m for m in found if m.score >= self.s.threshold]
            lines.append(f"{label}: {len(accepted)} found")
            for m in found[:6]:
                verdict = "accepted" if m.score >= self.s.threshold else "below threshold"
                lines.append(f"  score {m.score:.2f} at ({m.center[0]}, {m.center[1]}), {verdict}")
        return lines
