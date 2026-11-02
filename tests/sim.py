"""A fake LinkedIn-like page that renders real frames and reacts to input."""
from __future__ import annotations

import threading

import cv2
import numpy as np

from linkdn_connect.screen import Frame
from linkdn_connect.vision import ASSETS

VIEW_W, VIEW_H = 960, 540
SCROLL_PER_CLICK = 100
CONNECT_IMG = cv2.imread(str(ASSETS / "connect_button.png"))
SEND_IMG = cv2.imread(str(ASSETS / "send_button.png"))
BTN_H, BTN_W = CONNECT_IMG.shape[:2]


class Button:
    def __init__(self, x: int, y: int, kind: str):
        self.x, self.y, self.kind = x, y, kind
        self.state = "pending" if kind == "pending" else "connect"
        self.clicks = 0

    def contains(self, px: int, py: int, scroll: int) -> bool:
        top = self.y - scroll
        return self.x <= px < self.x + BTN_W and top <= py < top + BTN_H


class SimWorld:
    def __init__(self, buttons: list[Button], page_height: int):
        self.buttons = buttons
        self.page_height = page_height
        self.scroll = 0
        self.modal: tuple[str, Button] | None = None
        self.pos = (0, 0)
        self.order: list[Button] = []
        self.escapes = 0
        self.grabs = 0

    def render(self) -> np.ndarray:
        img = np.full((VIEW_H, VIEW_W, 3), 255, np.uint8)
        cv2.rectangle(img, (0, 0), (VIEW_W, 50), (240, 240, 240), -1)
        for b in self.buttons:
            top = b.y - self.scroll
            if top + BTN_H <= 0 or top >= VIEW_H:
                continue
            if b.state == "connect":
                self._paste(img, CONNECT_IMG, b.x, top)
            else:
                cv2.rectangle(img, (b.x, top), (b.x + BTN_W, top + BTN_H), (90, 90, 90), 2)
                cv2.putText(img, "Pending", (b.x + 80, top + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (60, 60, 60), 2)
        if self.modal:
            img = (img * 0.4).astype(np.uint8)
            cv2.rectangle(img, (250, 150), (710, 390), (255, 255, 255), -1)
            if self.modal[0] == "send":
                cv2.rectangle(img, (280, 330), (440, 370), (200, 120, 20), 2)
                cv2.putText(img, "Add a note", (295, 358), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 120, 20), 2)
                self._paste(img, SEND_IMG, 470, 325)
            else:
                cv2.putText(img, "Weekly limit reached", (290, 270), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (30, 30, 30), 2)
        return img

    @staticmethod
    def _paste(img, patch, x, y):
        h, w = patch.shape[:2]
        h = min(h, img.shape[0] - y)
        if h > 0:
            img[y : y + h, x : x + w] = patch[:h]

    def click(self):
        px, py = self.pos
        if self.modal:
            kind, button = self.modal
            if kind == "send" and 470 <= px < 470 + SEND_IMG.shape[1] and 325 <= py < 325 + SEND_IMG.shape[0]:
                button.state = "pending"
                self.modal = None
            return
        for b in self.buttons:
            if b.state == "connect" and b.contains(px, py, self.scroll):
                b.clicks += 1
                self.order.append(b)
                if b.kind == "direct":
                    b.state = "pending"
                elif b.kind == "stuck":
                    self.modal = ("other", b)
                else:
                    self.modal = ("send", b)
                return

    def remaining(self) -> list[Button]:
        return [b for b in self.buttons if b.state == "connect"]


class SimScreen:
    def __init__(self, world: SimWorld, scale: float = 1.0):
        self.world = world
        self.scale = scale

    def grab(self) -> Frame:
        self.world.grabs += 1
        return Frame(self.world.render(), 0, 0, self.scale)

    def close(self):
        pass


class SimPointer:
    def __init__(self, world: SimWorld, scale: float = 1.0):
        self.world = world
        self.scale = scale
        self.drift = (0, 0)
        self.size = None

    def configure(self, w, h):
        self.size = (w, h)

    def move_to(self, x, y):
        self.world.pos = (round(x * self.scale), round(y * self.scale))

    def click(self):
        self.world.click()

    def scroll_down(self, clicks):
        w = self.world
        w.scroll = min(w.scroll + clicks * SCROLL_PER_CLICK, max(0, w.page_height - VIEW_H))

    def escape(self):
        self.world.escapes += 1
        self.world.modal = None

    def position(self):
        return round(self.world.pos[0] / self.scale) + self.drift[0], round(self.world.pos[1] / self.scale) + self.drift[1]

    def close(self):
        pass


class FakeClock:
    def __init__(self, stop: threading.Event):
        self.t = 0.0
        self.stop = stop

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


def grid(rows: int, kinds=None, spacing: int = 220, first: int = 120):
    """Two columns of buttons, one row every `spacing` pixels."""
    buttons = []
    for r in range(rows):
        for c, x in enumerate((60, 520)):
            kind = (kinds or {}).get((r, c), "normal")
            buttons.append(Button(x, first + r * spacing, kind))
    return buttons, first + rows * spacing + 200
