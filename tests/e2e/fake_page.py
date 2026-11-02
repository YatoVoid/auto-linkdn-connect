"""A scrolling people grid with Connect buttons, for end-to-end runs and the demo recording.

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
ROLES = ["Product Designer", "Software Engineer", "Recruiter", "Data Analyst", "Studio Producer", "QA Lead",
         "Art Director", "Engineering Manager", "Technical Artist", "Sound Designer", "Game Designer", "Animator"]
CARD_W, GAP, BTN_W, BTN_H = 286, 40, 246, 42
TOP, ROW_H = 190, 260
BG, CARD_BG = "#f3f2ef", "white"


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
    root.title("demo page")
    if args.cover:
        root.overrideredirect(True)
        root.attributes("-topmost", True)
    width, height = (int(v) for v in args.geometry.split("+")[0].split("x"))
    rows = (len(kinds) + 1) // 2
    page_h = TOP + rows * row_h + 200
    left = (width - (2 * CARD_W + GAP)) // 2
    columns = (left + 20, left + CARD_W + GAP + 20)

    canvas = tk.Canvas(root, width=width, height=height, bg=BG, highlightthickness=0, yscrollincrement=100,
                       scrollregion=(0, 0, width, page_h))
    canvas.pack(fill="both", expand=True)
    connect_img = tk.PhotoImage(file=str(ASSETS / "connect_button.png"))
    send_img = tk.PhotoImage(file=str(ASSETS / "send_button.png"))

    buttons = []
    for i, kind in enumerate(kinds):
        x, y = columns[i % 2], TOP + (i // 2) * row_h
        cx = x + BTN_W // 2
        canvas.create_rectangle(x - 20, y - 150, x - 20 + CARD_W, y + 62, fill=CARD_BG, outline="#e0dfdc")
        canvas.create_rectangle(x - 19, y - 149, x - 20 + CARD_W, y - 100, fill="#a0b4b7", outline="")
        canvas.create_oval(cx - 30, y - 128, cx + 30, y - 68, fill="#c7cdd1", outline="white", width=3)
        canvas.create_text(cx, y - 52, text=f"Sample Person {i + 1}", fill="#191919", font=("Helvetica", 13, "bold"))
        canvas.create_text(cx, y - 28, text=ROLES[i % len(ROLES)], fill="#666666", font=("Helvetica", 10))
        buttons.append({"i": i, "kind": kind, "x": x, "y": y, "state": "pending" if kind == "pending" else "connect", "clicks": 0})

    canvas.create_rectangle(0, 0, width, 56, fill="white", outline="#e0dfdc", tags="bar")
    bar_text = canvas.create_text(width // 2, 28, text="Demo page, not LinkedIn", fill="#444444", font=("Helvetica", 13, "bold"))

    modal = {"open": None, "ids": []}
    order = []

    def draw_buttons():
        for b in buttons:
            for key in ("id", "id2"):
                if key in b:
                    canvas.delete(b.pop(key))
            if b["state"] == "connect":
                b["id"] = canvas.create_image(b["x"], b["y"], anchor="nw", image=connect_img)
            else:
                b["id"] = canvas.create_rectangle(b["x"], b["y"], b["x"] + BTN_W, b["y"] + BTN_H, outline="#555555", width=2)
                b["id2"] = canvas.create_text(b["x"] + BTN_W // 2, b["y"] + BTN_H // 2, text="Pending", fill="#444444", font=("Helvetica", 14, "bold"))
        pin_bar()

    def pin_bar():
        view_y = canvas.canvasy(0)
        canvas.coords("bar", 0, view_y, width, view_y + 56)
        canvas.coords(bar_text, width // 2, view_y + 28)
        canvas.tag_raise("bar")
        canvas.tag_raise(bar_text)

    def save():
        Path(args.result).write_text(json.dumps({
            "states": {b["i"]: b["state"] for b in buttons},
            "clicks": {b["i"]: b["clicks"] for b in buttons},
            "order": order,
        }))

    def close_modal():
        for item in modal["ids"]:
            canvas.delete(item)
        modal["ids"] = []
        modal["open"] = None

    def open_modal(button):
        view_y = canvas.canvasy(0)
        modal["open"] = button
        bx, by = width // 2 - 230, view_y + height // 2 - 130
        dim = canvas.create_rectangle(0, view_y, width, view_y + height, fill="#000000", stipple="gray12", outline="")
        box = canvas.create_rectangle(bx, by, bx + 460, by + 260, fill="white", outline="#999999")
        modal["ids"] = [dim, box]
        if button["kind"] == "stuck":
            modal["ids"].append(canvas.create_text(bx + 230, by + 130, text="Weekly invitation limit reached", font=("Helvetica", 16)))
            modal["send_box"] = None
        else:
            modal["ids"].append(canvas.create_text(bx + 230, by + 60, text="Add a note to your invitation?", fill="#191919", font=("Helvetica", 15, "bold")))
            modal["ids"].append(canvas.create_rectangle(bx + 30, by + 200, bx + 190, by + 240, outline="#0a66c2", width=2))
            modal["ids"].append(canvas.create_text(bx + 110, by + 220, text="Add a note", fill="#0a66c2", font=("Helvetica", 13, "bold")))
            sx, sy = bx + 220, by + 195
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
            if b["state"] == "connect" and b["x"] <= x <= b["x"] + BTN_W and b["y"] <= y <= b["y"] + BTN_H:
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
            canvas.yview_scroll(direction, "units")
            pin_bar()

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
