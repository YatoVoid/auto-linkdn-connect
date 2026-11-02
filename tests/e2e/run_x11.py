"""End to end on a real X server (Xephyr): real capture, real XTest clicks, real scrolling."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HOST_DISPLAY = os.environ.get("DISPLAY", ":0")
DISPLAY = ":7"
os.environ["DISPLAY"] = DISPLAY
os.environ["XDG_SESSION_TYPE"] = "x11"
os.environ.pop("WAYLAND_DISPLAY", None)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from linkdn_connect.engine import Callbacks, Engine  # noqa: E402
from linkdn_connect.hotkey import create_hotkey  # noqa: E402
from linkdn_connect.pointer import PynputPointer  # noqa: E402
from linkdn_connect.screen import MssScreen  # noqa: E402
from linkdn_connect.settings import Settings  # noqa: E402
from linkdn_connect.vision import default_templates  # noqa: E402

xephyr = subprocess.Popen(["Xephyr", DISPLAY, "-screen", "1024x640", "-ac", "-br", "-nolisten", "tcp"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={**os.environ, "DISPLAY": HOST_DISPLAY})
try:
    for _ in range(50):
        if Path("/tmp/.X11-unix/X7").exists():
            break
        time.sleep(0.1)
    time.sleep(1.0)

    result = Path(tempfile.mkdtemp()) / "result.json"
    page = subprocess.Popen([sys.executable, str(HERE / "fake_page.py"), "--geometry", "1024x640+0+0", "--result", str(result)])
    time.sleep(2.0)

    pressed = []
    hotkey = create_hotkey("F8", lambda: pressed.append(1))
    hotkey.start()
    time.sleep(0.5)
    from pynput.keyboard import Controller, Key
    kb = Controller()
    kb.press(Key.f8)
    kb.release(Key.f8)
    time.sleep(0.5)
    hotkey.stop()
    print("hotkey fired:", bool(pressed))

    stop = threading.Event()
    threading.Timer(180, stop.set).start()
    log = []
    screen, pointer = MssScreen(1), PynputPointer()
    templates = default_templates()
    engine = Engine(Settings(pause_min=0.5, pause_max=1.0), screen, pointer, *templates, stop,
                    Callbacks(log=lambda t: (log.append(t), print("  ", t))))
    t0 = time.time()
    reason = engine.run()
    print("reason:", reason, f"({time.time() - t0:.0f}s)")
    screen.close()

    time.sleep(0.5)
    data = json.loads(result.read_text())
    states = {int(k): v for k, v in data["states"].items()}
    clicks = {int(k): v for k, v in data["clicks"].items()}
    print("order:", data["order"])
    print("states:", states)
    expected_sent = {i for i, k in enumerate(["normal", "normal", "pending", "normal", "direct", "normal", "stuck", "normal", "normal", "normal", "pending", "normal"]) if k in ("normal", "direct")}
    ok = (
        pressed
        and engine.sent == len(expected_sent)
        and all(states[i] == "pending" for i in expected_sent)
        and states[6] == "connect"
        and data["order"] == sorted(data["order"])
        and clicks[2] == 0 and clicks[10] == 0
        and reason == "Reached the end of the page."
    )
    print("RESULT:", "PASS" if ok else "FAIL")
    page.terminate()
    sys.exit(0 if ok else 1)
finally:
    xephyr.terminate()
