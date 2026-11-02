from __future__ import annotations

import time

from .platform_info import is_wayland

WHEEL_NOTCH = 120
ABS_MAX = 32767


class PointerError(RuntimeError):
    pass


class PynputPointer:
    """Windows and X11. Coordinates are desktop pixels."""

    def __init__(self) -> None:
        from pynput import keyboard, mouse

        self._mouse = mouse.Controller()
        self._keyboard = keyboard.Controller()
        self._button = mouse.Button.left
        self._esc = keyboard.Key.esc

    def configure(self, width: int, height: int) -> None:
        pass

    def move_to(self, x: int, y: int) -> None:
        sx, sy = self._mouse.position
        steps = 8
        for i in range(1, steps + 1):
            self._mouse.position = (round(sx + (x - sx) * i / steps), round(sy + (y - sy) * i / steps))
            time.sleep(0.008)
        self._mouse.position = (x, y)
        time.sleep(0.06)

    def click(self) -> None:
        self._mouse.press(self._button)
        time.sleep(0.05)
        self._mouse.release(self._button)

    def scroll_down(self, clicks: int) -> None:
        for _ in range(clicks):
            self._mouse.scroll(0, -1)
            time.sleep(0.05)

    def escape(self) -> None:
        self._keyboard.press(self._esc)
        self._keyboard.release(self._esc)

    def position(self) -> tuple[int, int] | None:
        x, y = self._mouse.position
        return int(x), int(y)

    def close(self) -> None:
        pass


class EvdevPointer:
    """Wayland. Virtual input devices through /dev/uinput.

    The pointer is an absolute device, so a screen position maps straight to
    a fraction of the desktop and fractional scaling does not matter.
    """

    def __init__(self) -> None:
        try:
            from evdev import AbsInfo, UInput
            from evdev import ecodes as e
        except ImportError as exc:
            raise PointerError("The evdev package is not installed.") from exc

        self._e = e
        self._width = self._height = 0
        try:
            absinfo = AbsInfo(0, 0, ABS_MAX, 0, 0, 0)
            self._abs = UInput(
                {e.EV_KEY: [e.BTN_LEFT], e.EV_ABS: [(e.ABS_X, absinfo), (e.ABS_Y, absinfo)]},
                name="linkdn-connect pointer",
                bustype=e.BUS_USB,
            )
            self._wheel = UInput(
                {e.EV_KEY: [e.BTN_LEFT], e.EV_REL: [e.REL_X, e.REL_Y, e.REL_WHEEL, e.REL_WHEEL_HI_RES]},
                name="linkdn-connect wheel",
                bustype=e.BUS_USB,
            )
            self._keys = UInput({e.EV_KEY: [e.KEY_ESC]}, name="linkdn-connect keys", bustype=e.BUS_USB)
        except (PermissionError, OSError) as exc:
            raise PointerError(
                "Cannot open /dev/uinput. Add your user to the 'input' group "
                "(sudo usermod -aG input $USER), then log out and back in."
            ) from exc
        time.sleep(1.0)

    def configure(self, width: int, height: int) -> None:
        self._width, self._height = width, height

    def move_to(self, x: int, y: int) -> None:
        if self._width < 2 or self._height < 2:
            raise PointerError("Screen size is not known yet.")
        e = self._e
        self._abs.write(e.EV_ABS, e.ABS_X, round(x * ABS_MAX / (self._width - 1)))
        self._abs.write(e.EV_ABS, e.ABS_Y, round(y * ABS_MAX / (self._height - 1)))
        self._abs.syn()
        time.sleep(0.15)

    def click(self) -> None:
        e = self._e
        self._abs.write(e.EV_KEY, e.BTN_LEFT, 1)
        self._abs.syn()
        time.sleep(0.05)
        self._abs.write(e.EV_KEY, e.BTN_LEFT, 0)
        self._abs.syn()

    def scroll_down(self, clicks: int) -> None:
        e = self._e
        for _ in range(clicks):
            self._wheel.write(e.EV_REL, e.REL_WHEEL, -1)
            self._wheel.write(e.EV_REL, e.REL_WHEEL_HI_RES, -WHEEL_NOTCH)
            self._wheel.syn()
            time.sleep(0.05)

    def escape(self) -> None:
        e = self._e
        self._keys.write(e.EV_KEY, e.KEY_ESC, 1)
        self._keys.syn()
        self._keys.write(e.EV_KEY, e.KEY_ESC, 0)
        self._keys.syn()

    def position(self) -> tuple[int, int] | None:
        return None

    def close(self) -> None:
        for device in (self._abs, self._wheel, self._keys):
            device.close()


def create_pointer():
    return EvdevPointer() if is_wayland() else PynputPointer()
