"""End to end on a Wayland desktop: screenshot tool capture and virtual evdev pointer.

Covers the page with a borderless white test page first and refuses to run if
the screen does not look like only that page, so nothing else can be clicked.
"""
import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from linkdn_connect.engine import Callbacks, Engine  # noqa: E402
from linkdn_connect.pointer import EvdevPointer  # noqa: E402
from linkdn_connect.screen import create_screen  # noqa: E402
from linkdn_connect.settings import Settings  # noqa: E402
from linkdn_connect.vision import Finder, default_templates  # noqa: E402

KINDS = ["normal", "normal", "direct", "normal", "normal", "normal"]
result = Path(tempfile.mkdtemp()) / "result.json"
page = subprocess.Popen([
    sys.executable, str(HERE / "fake_page.py"), "--geometry", "1920x1080+0+0", "--cover",
    "--kinds", ",".join(KINDS), "--row-h", "420", "--result", str(result),
])
try:
    time.sleep(3.0)
    screen = create_screen()
    templates = default_templates()
    first = screen.grab()
    white = (first.image[:1000] > 235).all(axis=2).mean()
    connects = len(Finder().find(first.image, templates[0], 0.75))
    print(f"precondition: white fraction {white:.2f}, connect buttons visible {connects}")
    if white < 0.85 or connects > 6:
        print("ABORT: the screen does not look like only the test page")
        sys.exit(2)

    pointer = EvdevPointer()
    stop = threading.Event()
    threading.Timer(150, stop.set).start()
    engine = Engine(Settings(pause_min=0.5, pause_max=1.0), screen, pointer, *templates, stop,
                    Callbacks(log=lambda t: print("  ", t, flush=True)))
    t0 = time.time()
    reason = engine.run()
    print("reason:", reason, f"({time.time() - t0:.0f}s)")
    pointer.close()
    screen.close()

    time.sleep(0.5)
    data = json.loads(result.read_text())
    states = {int(k): v for k, v in data["states"].items()}
    print("order:", data["order"], "states:", states)
    ok = engine.sent == len(KINDS) and all(v == "pending" for v in states.values()) \
        and data["order"] == sorted(data["order"]) and reason == "Reached the end of the page."
    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
finally:
    page.terminate()
