import json

import pytest

from linkdn_connect import platform_info, screen, settings


def test_normalized_clamps_values():
    s = settings.Settings(max_invites=0, pause_min=-4, pause_max=1, threshold=5, hotkey="X", scroll_clicks=99, monitor=0)
    n = s.normalized()
    assert n.max_invites == 1
    assert n.pause_min == 0.5 and n.pause_max >= n.pause_min
    assert n.threshold == 0.98
    assert n.hotkey == "F8"
    assert n.scroll_clicks == 20
    assert n.monitor == 1


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "s.json"
    settings.save(settings.Settings(max_invites=12, hotkey="F9", more_image="/x/more.png"), path)
    loaded = settings.load(path)
    assert loaded.max_invites == 12 and loaded.hotkey == "F9"
    assert loaded.more_image == "/x/more.png"


def test_load_survives_missing_and_corrupt_files(tmp_path):
    assert settings.load(tmp_path / "missing.json") == settings.Settings()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert settings.load(bad) == settings.Settings()
    odd = tmp_path / "odd.json"
    odd.write_text(json.dumps({"max_invites": "many", "unknown": 1}))
    assert settings.load(odd) == settings.Settings()


def test_wayland_detection(monkeypatch):
    monkeypatch.setattr(platform_info.sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("DISPLAY", ":0")
    assert platform_info.is_wayland()
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert not platform_info.is_wayland()
    monkeypatch.delenv("XDG_SESSION_TYPE")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.delenv("DISPLAY")
    assert platform_info.is_wayland()


def test_never_wayland_off_linux(monkeypatch):
    monkeypatch.setattr(platform_info.sys, "platform", "win32")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert not platform_info.is_wayland()


def test_wayland_screen_prefers_installed_tool(monkeypatch):
    monkeypatch.setattr(screen, "is_wayland", lambda: True)
    monkeypatch.setattr(screen.shutil, "which", lambda name: "/usr/bin/" + name if name == "spectacle" else None)
    made = screen.create_screen()
    assert isinstance(made, screen.CommandScreen) and made.tool == "spectacle"
    made.close()


def test_wayland_without_a_screenshot_tool_is_an_error(monkeypatch):
    monkeypatch.setattr(screen, "is_wayland", lambda: True)
    monkeypatch.setattr(screen.shutil, "which", lambda name: None)
    with pytest.raises(screen.ScreenError):
        screen.create_screen()


def test_x11_and_windows_use_mss(monkeypatch):
    monkeypatch.setattr(screen, "is_wayland", lambda: False)
    assert isinstance(screen.create_screen(2), screen.MssScreen)
