"""Records docs/demo.mp4 and docs/demo.gif.

The real app runs inside a nested X server (Xephyr) next to a local demo page.
Nothing on your own desktop is touched. Needs Xephyr and ffmpeg.

    python tools/record_demo.py
"""
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST_DISPLAY = os.environ.get("DISPLAY", ":0")
DISPLAY = ":7"
SCREEN_W, SCREEN_H = 1500, 740
PAGE_W = 1000
KINDS = "normal,normal,pending,normal,normal,normal"

config = Path(tempfile.mkdtemp())
(config / "linkdn-connect").mkdir()
(config / "linkdn-connect" / "settings.json").write_text(
    '{"max_invites": 30, "pause_min": 0.8, "pause_max": 1.5, "hotkey": "F8"}'
)
os.environ.update(DISPLAY=DISPLAY, XDG_SESSION_TYPE="x11", XDG_CONFIG_HOME=str(config))
os.environ.pop("WAYLAND_DISPLAY", None)
sys.path.insert(0, str(ROOT / "src"))

raw = Path(tempfile.mkdtemp()) / "raw.mp4"
xephyr = subprocess.Popen(
    ["Xephyr", DISPLAY, "-screen", f"{SCREEN_W}x{SCREEN_H}", "-ac", "-br", "-nolisten", "tcp"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={**os.environ, "DISPLAY": HOST_DISPLAY},
)
page = recorder = None
try:
    for _ in range(50):
        if Path("/tmp/.X11-unix/X7").exists():
            break
        time.sleep(0.1)
    time.sleep(1.0)

    from Xlib import X, display

    nested = display.Display(DISPLAY)
    root_window = nested.screen().root
    glyphs = nested.open_font("cursor")
    arrow = glyphs.create_glyph_cursor(glyphs, 68, 69, (0, 0, 0), (65535, 65535, 65535))
    root_window.change_attributes(background_pixel=0xF3F2EF, cursor=arrow)
    root_window.clear_area(0, 0, 0, 0, False)
    nested.flush()

    page = subprocess.Popen([
        sys.executable, str(ROOT / "tests/e2e/fake_page.py"), "--geometry", f"{PAGE_W}x{SCREEN_H}+0+0",
        "--kinds", KINDS, "--row-h", "260", "--result", str(config / "result.json"),
    ])
    time.sleep(1.5)

    from linkdn_connect import app as appmod

    app = appmod.App()
    app.root.geometry("+1040+30")
    finished = threading.Event()
    failed = threading.Event()

    def drive() -> None:
        global recorder
        from pynput.keyboard import Controller, Key

        time.sleep(1.5)
        recorder = subprocess.Popen(
            ["ffmpeg", "-loglevel", "error", "-y", "-f", "x11grab", "-framerate", "15", "-draw_mouse", "1",
             "-video_size", f"{SCREEN_W}x{SCREEN_H}", "-i", DISPLAY, "-c:v", "libx264", "-preset", "ultrafast",
             "-crf", "16", "-pix_fmt", "yuv420p", str(raw)],
            stdin=subprocess.PIPE,
        )
        time.sleep(2.0)
        keys = Controller()
        keys.press(Key.f8)
        keys.release(Key.f8)
        started = time.time() + 10
        while app.state == "idle" and time.time() < started:
            time.sleep(0.1)
        if app.state == "idle":
            failed.set()
        deadline = time.time() + 240
        while app.state != "idle" and time.time() < deadline:
            time.sleep(0.2)
        time.sleep(3.0)
        recorder.communicate(b"q")
        finished.set()

    threading.Thread(target=drive, daemon=True).start()

    def check() -> None:
        if finished.is_set():
            app._quit()
        else:
            app.root.after(300, check)

    app.root.after(300, check)
    app.run()
finally:
    if page:
        page.terminate()
    xephyr.terminate()

if failed.is_set():
    sys.exit("The run did not start, nothing written.")

out = ROOT / "docs"
out.mkdir(exist_ok=True)
subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(raw), "-c:v", "libx264", "-crf", "24",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out / "demo.mp4")], check=True)
subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(raw), "-vf",
                "fps=12,scale=1000:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer:bayer_scale=4",
                "-loop", "0", str(out / "demo.gif")], check=True)
print("wrote", out / "demo.mp4", out / "demo.gif")
