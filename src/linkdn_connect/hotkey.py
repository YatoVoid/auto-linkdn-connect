from __future__ import annotations

import select
import threading
import time
from typing import Callable

from .platform_info import is_wayland

KEYS = ("F6", "F7", "F8", "F9", "F10", "F11", "F12")


class HotkeyError(RuntimeError):
    pass


class Gate:
    """Drops repeat triggers. One tap can reach the listener as several key events."""

    def __init__(self, hold: float = 0.35, clock: Callable[[], float] = time.monotonic):
        self._hold = hold
        self._clock = clock
        self._last: float | None = None

    def allow(self) -> bool:
        now = self._clock()
        if self._last is not None and now - self._last < self._hold:
            return False
        self._last = now
        return True


class PynputHotkey:
    def __init__(self, name: str, callback: Callable[[], None]):
        from pynput import keyboard

        self._target = getattr(keyboard.Key, name.lower())
        self._callback = callback
        self._held = False
        self._gate = Gate()
        self._listener = keyboard.Listener(on_press=self._press, on_release=self._release)

    def _press(self, key) -> None:
        if key == self._target and not self._held:
            self._held = True
            if self._gate.allow():
                self._callback()

    def _release(self, key) -> None:
        if key == self._target:
            self._held = False

    def start(self) -> None:
        self._listener.start()

    def stop(self) -> None:
        self._listener.stop()


class EvdevHotkey:
    """Wayland has no global hotkeys for ordinary apps, so read the keyboards directly."""

    def __init__(self, name: str, callback: Callable[[], None]):
        try:
            import evdev
            from evdev import ecodes as e
        except ImportError as exc:
            raise HotkeyError("The evdev package is not installed.") from exc

        self._code = e.ecodes["KEY_" + name.upper()]
        self._callback = callback
        self._stop = threading.Event()
        self._gate = Gate()
        self._devices = []
        for path in evdev.list_devices():
            try:
                device = evdev.InputDevice(path)
            except OSError:
                continue
            if self._code in device.capabilities().get(e.EV_KEY, []):
                self._devices.append(device)
        if not self._devices:
            raise HotkeyError(
                "No keyboard can be read. Add your user to the 'input' group "
                "(sudo usermod -aG input $USER), then log out and back in."
            )
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        from evdev import ecodes as e

        devices = list(self._devices)
        while not self._stop.is_set() and devices:
            ready, _, _ = select.select(devices, [], [], 0.2)
            for device in ready:
                try:
                    for event in device.read():
                        if event.type == e.EV_KEY and event.code == self._code and event.value == 1:
                            if self._gate.allow():
                                self._callback()
                except OSError:
                    devices.remove(device)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        for device in self._devices:
            device.close()


def create_hotkey(name: str, callback: Callable[[], None]):
    if name not in KEYS:
        raise HotkeyError(f"Unsupported hotkey {name}.")
    return EvdevHotkey(name, callback) if is_wayland() else PynputHotkey(name, callback)
