from __future__ import annotations

import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk

from . import __version__, settings as settings_store
from .engine import Callbacks, Engine
from .hotkey import KEYS, HotkeyError, create_hotkey
from .platform_info import enable_dpi_awareness, is_linux
from .pointer import PointerError, create_pointer
from .screen import ScreenError, create_screen
from .settings import Settings
from .vision import Template, TemplateError, default_show_more, default_templates

COUNTDOWN = 3
SETTLE = 0.8


class NullPointer:
    def configure(self, width, height):
        pass

    def close(self):
        pass


class App:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Auto Connect")
        self.root.resizable(False, False)
        if is_linux():
            ttk.Style(self.root).theme_use("clam")

        self.events: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.state = "idle"
        self.hotkey = None
        self.worker: threading.Thread | None = None
        self._countdown_job = None

        saved = settings_store.load()
        self.v_max = tk.StringVar(value=str(saved.max_invites))
        self.v_pause_min = tk.StringVar(value=f"{saved.pause_min:g}")
        self.v_pause_max = tk.StringVar(value=f"{saved.pause_max:g}")
        self.v_threshold = tk.DoubleVar(value=saved.threshold)
        self.v_hotkey = tk.StringVar(value=saved.hotkey)
        self.v_scroll = tk.StringVar(value=str(saved.scroll_clicks))
        self.v_monitor = tk.StringVar(value=str(saved.monitor))
        self.v_connect = tk.StringVar(value=saved.connect_image)
        self.v_send = tk.StringVar(value=saved.send_image)
        self.v_more = tk.StringVar(value=saved.more_image)
        self.v_status = tk.StringVar(value="Ready")
        self.v_count = tk.StringVar(value="0 sent")
        self.v_button = tk.StringVar()

        self._build()
        self._bind_hotkey()
        self.root.protocol("WM_DELETE_WINDOW", self._quit)
        self.root.after(100, self._poll)

    def _build(self) -> None:
        pad = {"padx": 14}
        outer = ttk.Frame(self.root, padding=(0, 14, 0, 14))
        outer.grid()

        head = ttk.Frame(outer)
        head.grid(row=0, column=0, sticky="ew", **pad)
        head.columnconfigure(0, weight=1)
        ttk.Label(head, textvariable=self.v_status, font=("TkDefaultFont", 13, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(head, textvariable=self.v_count).grid(row=0, column=1, sticky="e")

        self.button = ttk.Button(outer, textvariable=self.v_button, command=self.toggle)
        self.button.grid(row=1, column=0, sticky="ew", padx=14, pady=(10, 4), ipady=8)
        self._refresh_button()
        ttk.Label(outer, text="Open the LinkedIn page first, then start.", foreground="#555555").grid(
            row=2, column=0, sticky="w", **pad
        )

        box = ttk.LabelFrame(outer, text="Settings", padding=10)
        box.grid(row=3, column=0, sticky="ew", padx=14, pady=(12, 0))
        box.columnconfigure(1, weight=1)
        ttk.Label(box, text="Invitations per run").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Spinbox(box, from_=1, to=500, width=6, textvariable=self.v_max).grid(row=0, column=1, sticky="e")

        ttk.Label(box, text="Pause between (seconds)").grid(row=1, column=0, sticky="w", pady=3)
        pause = ttk.Frame(box)
        pause.grid(row=1, column=1, sticky="e")
        ttk.Spinbox(pause, from_=0.5, to=120, increment=0.5, width=5, textvariable=self.v_pause_min).grid(row=0, column=0)
        ttk.Label(pause, text=" to ").grid(row=0, column=1)
        ttk.Spinbox(pause, from_=0.5, to=180, increment=0.5, width=5, textvariable=self.v_pause_max).grid(row=0, column=2)

        ttk.Label(box, text="Match strictness").grid(row=2, column=0, sticky="w", pady=3)
        strict = ttk.Frame(box)
        strict.grid(row=2, column=1, sticky="e")
        self.threshold_label = ttk.Label(strict, width=4)
        ttk.Scale(strict, from_=0.55, to=0.95, variable=self.v_threshold, length=130, command=self._threshold_moved).grid(
            row=0, column=0
        )
        self.threshold_label.grid(row=0, column=1, padx=(6, 0))
        self._threshold_moved()

        ttk.Label(box, text="Start / stop key").grid(row=3, column=0, sticky="w", pady=3)
        keys = ttk.Combobox(box, values=KEYS, textvariable=self.v_hotkey, width=5, state="readonly")
        keys.grid(row=3, column=1, sticky="e")
        keys.bind("<<ComboboxSelected>>", lambda _e: self._bind_hotkey())

        self.more_button = ttk.Button(box, text="More options", command=self._toggle_more)
        self.more_button.grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.more = ttk.Frame(box)
        self.more.columnconfigure(1, weight=1)
        ttk.Label(self.more, text="Scroll step (wheel clicks)").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Spinbox(self.more, from_=1, to=20, width=6, textvariable=self.v_scroll).grid(row=0, column=1, sticky="e")
        ttk.Label(self.more, text="Monitor").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Spinbox(self.more, from_=1, to=8, width=6, textvariable=self.v_monitor).grid(row=1, column=1, sticky="e")
        self._image_row(self.more, 2, "Connect image", self.v_connect)
        self._image_row(self.more, 3, "Send image", self.v_send)
        self._image_row(self.more, 4, "More results image", self.v_more)

        self.log = tk.Text(outer, height=8, width=10, state="disabled", wrap="word", relief="flat", background="#f4f4f4")
        self.log.grid(row=4, column=0, sticky="ew", padx=14, pady=(12, 0))

        foot = ttk.Frame(outer)
        foot.grid(row=5, column=0, sticky="ew", padx=14, pady=(8, 0))
        foot.columnconfigure(0, weight=1)
        ttk.Button(foot, text="Test detection", command=self.test_detection).grid(row=0, column=1)
        ttk.Label(foot, text=f"v{__version__}", foreground="#777777").grid(row=0, column=0, sticky="w")

    def _image_row(self, parent, row: int, label: str, var: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        cell = ttk.Frame(parent)
        cell.grid(row=row, column=1, sticky="e")
        name = ttk.Label(cell, width=16, anchor="e")
        name.grid(row=0, column=0)

        def show(*_):
            path = var.get()
            name.configure(text=path.replace("\\", "/").split("/")[-1] if path else "built in")

        def choose():
            path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp")])
            if path:
                var.set(path)

        var.trace_add("write", show)
        show()
        ttk.Button(cell, text="Choose", width=7, command=choose).grid(row=0, column=1, padx=(4, 0))
        ttk.Button(cell, text="Reset", width=6, command=lambda: var.set("")).grid(row=0, column=2, padx=(4, 0))

    def _toggle_more(self) -> None:
        if self.more.winfo_ismapped():
            self.more.grid_remove()
            self.more_button.configure(text="More options")
        else:
            self.more.grid(row=5, column=0, columnspan=2, sticky="ew")
            self.more_button.configure(text="Fewer options")

    def _threshold_moved(self, _value=None) -> None:
        self.threshold_label.configure(text=f"{self.v_threshold.get():.2f}")

    def _refresh_button(self) -> None:
        running = self.state != "idle"
        self.v_button.set(f"Stop ({self.v_hotkey.get()})" if running else f"Start ({self.v_hotkey.get()})")

    def _bind_hotkey(self) -> None:
        if self.hotkey is not None:
            self.hotkey.stop()
            self.hotkey = None
        try:
            self.hotkey = create_hotkey(self.v_hotkey.get(), lambda: self.events.put(("hotkey",)))
            self.hotkey.start()
        except Exception as exc:
            self._log(f"Hotkey unavailable: {exc}")
        self._refresh_button()

    def _log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", f"{time.strftime('%H:%M:%S')}  {text}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _read_settings(self) -> Settings:
        try:
            raw = Settings(
                max_invites=int(self.v_max.get()),
                pause_min=float(self.v_pause_min.get()),
                pause_max=float(self.v_pause_max.get()),
                threshold=float(self.v_threshold.get()),
                hotkey=self.v_hotkey.get(),
                scroll_clicks=int(self.v_scroll.get()),
                monitor=int(self.v_monitor.get()),
                connect_image=self.v_connect.get(),
                send_image=self.v_send.get(),
                more_image=self.v_more.get(),
            )
        except ValueError as exc:
            raise ValueError("Settings need whole numbers where a count is expected.") from exc
        if raw.pause_max < raw.pause_min:
            raise ValueError("The longest pause must not be shorter than the shortest.")
        return raw.normalized()

    def _templates(self, s: Settings) -> tuple[Template, Template, Template]:
        connect, send = default_templates()
        more = default_show_more()
        if s.connect_image:
            connect = Template.from_file(s.connect_image)
        if s.send_image:
            send = Template.from_file(s.send_image)
        if s.more_image:
            more = Template.from_file(s.more_image, label_only=True)
        return connect, send, more

    def toggle(self) -> None:
        if self.state == "idle":
            self.start()
        else:
            self.stop()

    def _prepare(self):
        if self.hotkey is None:
            self._set_status("Start key unavailable. See the log.")
            self._log("Not started: without a working start/stop key there would be no way to stop it.")
            return None
        try:
            s = self._read_settings()
            templates = self._templates(s)
        except (ValueError, TemplateError) as exc:
            self._set_status("Check the settings")
            self._log(str(exc))
            return None
        settings_store.save(s)
        return s, templates

    def start(self) -> None:
        prepared = self._prepare()
        if prepared is None:
            return
        self._begin_countdown(lambda: self._launch(*prepared))

    def test_detection(self) -> None:
        if self.state != "idle":
            return
        try:
            s = self._read_settings()
            templates = self._templates(s)
        except (ValueError, TemplateError) as exc:
            self._log(str(exc))
            return
        self._begin_countdown(lambda: self._launch_test(s, templates), seconds=2)

    def _begin_countdown(self, then, seconds: int = COUNTDOWN) -> None:
        self.state = "countdown"
        self.stop_event.clear()
        self.v_count.set("0 sent")
        self._refresh_button()

        def tick(n: int) -> None:
            if self.state != "countdown":
                return
            if n == 0:
                then()
                return
            self.v_status.set(f"Starting in {n}")
            self._countdown_job = self.root.after(1000, tick, n - 1)

        tick(seconds)

    def _set_status(self, text: str) -> None:
        self.v_status.set(text)

    def _launch(self, s: Settings, templates) -> None:
        self.state = "running"
        self.v_status.set("Running")
        self.root.iconify()
        self.worker = threading.Thread(target=self._work, args=(s, templates, False), daemon=True)
        self.worker.start()

    def _launch_test(self, s: Settings, templates) -> None:
        self.state = "running"
        self.v_status.set("Looking at the screen")
        self.root.iconify()
        self.worker = threading.Thread(target=self._work, args=(s, templates, True), daemon=True)
        self.worker.start()

    def _work(self, s: Settings, templates, test_only: bool) -> None:
        screen = pointer = None
        reason = "Done."
        try:
            self.stop_event.wait(SETTLE)
            screen = create_screen(s.monitor)
            pointer = NullPointer() if test_only else create_pointer()
            engine = Engine(
                s,
                screen,
                pointer,
                *templates[:2],
                self.stop_event,
                Callbacks(
                    log=lambda text: self.events.put(("log", text)),
                    progress=lambda n: self.events.put(("count", n)),
                ),
                show_more=templates[2],
            )
            if test_only:
                for line in engine.detect_once():
                    self.events.put(("log", line))
                reason = "Detection test finished."
            else:
                reason = engine.run()
        except (ScreenError, PointerError) as exc:
            reason = str(exc)
        except Exception as exc:
            reason = f"Unexpected error: {exc}"
        finally:
            for closable in (pointer, screen):
                if closable is not None:
                    try:
                        closable.close()
                    except Exception:
                        pass
            self.events.put(("done", reason))

    def stop(self) -> None:
        if self.state == "countdown":
            if self._countdown_job is not None:
                self.root.after_cancel(self._countdown_job)
            self.state = "idle"
            self.v_status.set("Cancelled")
            self._refresh_button()
            return
        self.stop_event.set()
        self.v_status.set("Stopping")

    def _poll(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "hotkey":
                    self.toggle()
                elif kind == "log":
                    self._log(event[1])
                elif kind == "count":
                    self.v_count.set(f"{event[1]} sent")
                elif kind == "done":
                    self.state = "idle"
                    self.v_status.set("Ready")
                    self._log(event[1])
                    self._refresh_button()
                    self.root.deiconify()
                    self.root.lift()
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _quit(self) -> None:
        self.stop_event.set()
        if self.hotkey is not None:
            self.hotkey.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    if "--self-test" in sys.argv:
        from .selftest import run

        index = sys.argv.index("--self-test")
        report = sys.argv[index + 1] if index + 1 < len(sys.argv) else None
        sys.exit(run(report))
    enable_dpi_awareness()
    App().run()
