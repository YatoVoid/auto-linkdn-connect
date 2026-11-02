import sys
from pathlib import Path

root = Path(SPECPATH).parent

hidden = ["mss.windows", "pynput.keyboard._win32", "pynput.mouse._win32"]
if sys.platform.startswith("linux"):
    hidden = ["mss.linux", "pynput.keyboard._xorg", "pynput.mouse._xorg", "evdev"]

analysis = Analysis(
    [str(root / "packaging" / "entry.py")],
    pathex=[str(root / "src")],
    datas=[(str(root / "src" / "linkdn_connect" / "assets"), "linkdn_connect/assets")],
    hiddenimports=hidden,
    excludes=["matplotlib", "scipy", "pandas", "IPython", "pytest"],
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="auto-linkdn-connect",
    console=False,
    upx=False,
)
