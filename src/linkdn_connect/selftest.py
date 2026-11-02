from __future__ import annotations

import sys
import traceback
from pathlib import Path


def _core_checks(lines: list[str]) -> bool:
    import cv2
    import numpy as np

    from .vision import ASSETS, Finder, default_show_more, default_templates

    connect, send = default_templates()
    more = default_show_more()
    lines.append(f"templates: ok ({connect.gray.shape}, {send.gray.shape}, {more.gray.shape})")
    page = np.full((400, 700, 3), 255, np.uint8)
    button = cv2.imread(str(ASSETS / "connect_button.png"))
    page[150 : 150 + button.shape[0], 200 : 200 + button.shape[1]] = button
    found = Finder().find(page, connect, 0.75)
    lines.append(f"vision: {'ok' if len(found) == 1 else 'FAILED'} ({len(found)} match)")
    return len(found) == 1


def _optional_checks(lines: list[str]) -> None:
    """Parts that need a desktop session. Reported but not fatal."""
    for name, check in (
        ("screen capture", _screen),
        ("mouse and keyboard", _input),
    ):
        try:
            check()
            lines.append(f"{name}: ok")
        except Exception as exc:
            lines.append(f"{name}: unavailable ({exc})")


def _screen() -> None:
    from .screen import create_screen

    screen = create_screen()
    try:
        screen.grab()
    finally:
        screen.close()


def _input() -> None:
    from .pointer import create_pointer

    create_pointer().close()


def run(report: str | Path | None = None) -> int:
    lines = [f"python {sys.version.split()[0]} on {sys.platform}"]
    try:
        ok = _core_checks(lines)
    except Exception:
        lines.append("core checks crashed:\n" + traceback.format_exc())
        ok = False
    _optional_checks(lines)
    lines.append("RESULT: " + ("PASS" if ok else "FAIL"))
    text = "\n".join(lines) + "\n"
    if report:
        Path(report).write_text(text, encoding="utf-8")
    elif sys.stdout is not None:
        sys.stdout.write(text)
    return 0 if ok else 1
