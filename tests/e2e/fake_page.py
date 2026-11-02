"""A scrolling page of Connect buttons for end-to-end runs on a real screen.

    python fake_page.py --geometry 1280x800+0+0 --result out.json

Click a Connect button and a dialog with "Send without a note" opens. Escape
closes any dialog. The outcome is written to the result file on every change.
"""
import argparse
import json
import tkinter as tk
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[2] / "src" / "linkdn_connect" / "assets"
KINDS = ["normal", "normal", "pending", "normal", "direct", "normal", "stuck", "normal", "normal", "normal", "pending", "normal"]
COLUMN_X = (60, 520)
ROW_H = 240
TOP = 120


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--geometry", default="1280x800+0+0")
    ap.add_argument("--result", required=True)
    ap.add_argument("--kinds", default=",".join(KINDS))
    ap.add_argument("--row-h", type=int, default=ROW_H)
    ap.add_argument("--cover", action="store_true", help="borderless and on top")
    args = ap.parse_args()
    kinds = args.kinds.split(",")
    row_h = args.row_h

    root = tk.Tk()
    root.geometry(args.geometry)
    root.title("fake page")
    if args.cover:
        root.overrideredirect(True)
        root.attributes("-topmost", True)
    width, height = (int(v) for v in args.geometry.split("+")[0].split("x"))
    rows = (len(kinds) + 1) // 2
    page_h = TOP + rows * row_h + 300

    canvas = tk.Canvas(root, width=width, height=height, bg="white", highlightthickness=0, yscrollincrement=100,
                       scrollregion=(0, 0, width, page_h))
    canvas.pack(fill="both", expand=True)
    connect_img = tk.PhotoImage(file=str(ASSETS / "connect_button.png"))
    send_img = tk.PhotoImage(file=str(ASSETS / "send_button.png"))

    buttons = []
    for i, kind in enumerate(kinds):
        x, y = COLUMN_X[i % 2], TOP + (i // 2) * row_h
        canvas.create_rectangle(x - 20, y - 60, x + 266, y + 100, outline="#dddddd")
        item = {"i": i, "kind": kind, "x": x, "y": y, "state": "pending" if kind == "pending" else "connect", "clicks": 0}
        buttons.append(item)

    modal = {"open": None, "ids": []}
    overlay = {"ids": []}

    def draw_buttons():
        for b in buttons:
            for key in ("id", "id2"):
                if key in b:
                    canvas.delete(b.pop(key))
            if b["state"] == "connect":
                b["id"] = canvas.create_image(b["x"], b["y"], anchor="nw", image=connect_img)
            else:
                b["id"] = canvas.create_rectangle(b["x"], b["y"], b["x"] + 246, b["y"] + 42, outline="#555555", width=2)
                b["id2"] = canvas.create_text(b["x"] + 123, b["y"] + 21, text="Pending", fill="#444444", font=("Helvetica", 14, "bold"))

    def save():
        Path(args.result).write_text(json.dumps({
            "states": {b["i"]: b["state"] for b in buttons},
            "clicks": {b["i"]: b["clicks"] for b in buttons},
            "order": order,
        }))

    order = []

    def close_modal():
        for item in modal["ids"]:
            canvas.delete(item)
        modal["ids"] = []
        modal["open"] = None

    def open_modal(button):
        view_y = canvas.canvasy(0)
        modal["open"] = button
        dim = canvas.create_rectangle(0, view_y, width, view_y + height, fill="#555555", stipple="gray50", outline="")
        box = canvas.create_rectangle(250, view_y + 200, 710, view_y + 460, fill="white", outline="#999999")
        modal["ids"] = [dim, box]
        if button["kind"] == "stuck":
            modal["ids"].append(canvas.create_text(480, view_y + 320, text="Weekly invitation limit reached", font=("Helvetica", 16)))
            modal["send_box"] = None
        else:
            modal["ids"].append(canvas.create_rectangle(280, view_y + 400, 440, view_y + 440, outline="#0a66c2", width=2))
            modal["ids"].append(canvas.create_text(360, view_y + 420, text="Add a note", fill="#0a66c2", font=("Helvetica", 13, "bold")))
            sx, sy = 470, view_y + 395
            modal["ids"].append(canvas.create_image(sx, sy, anchor="nw", image=send_img))
            modal["send_box"] = (sx, sy, sx + send_img.width(), sy + send_img.height())

    def on_click(event):
        x, y = canvas.canvasx(event.x), canvas.canvasy(event.y)
        if modal["open"]:
            box = modal.get("send_box")
            if box and box[0] <= x <= box[2] and box[1] <= y <= box[3]:
                modal["open"]["state"] = "pending"
                close_modal()
                draw_buttons()
                save()
            return
        for b in buttons:
            if b["state"] == "connect" and b["x"] <= x <= b["x"] + 246 and b["y"] <= y <= b["y"] + 42:
                b["clicks"] += 1
                order.append(b["i"])
                if b["kind"] == "direct":
                    b["state"] = "pending"
                    draw_buttons()
                else:
                    open_modal(b)
                save()
                return

    def scroll(direction):
        if not modal["open"]:
            canvas.yview_scroll(direction * 1, "units")

    canvas.bind("<Button-1>", on_click)
    root.bind("<Button-4>", lambda e: scroll(-1))
    root.bind("<Button-5>", lambda e: scroll(1))
    root.bind("<MouseWheel>", lambda e: scroll(-1 if e.delta > 0 else 1))
    root.bind("<Escape>", lambda e: (close_modal(), save()))
    draw_buttons()
    save()
    root.mainloop()


if __name__ == "__main__":
    main()
