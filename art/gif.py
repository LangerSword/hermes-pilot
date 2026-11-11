#!/usr/bin/env python3
"""Record a real Pilot pane typing into vim, then render it as MP4 + GIF.

Frames are actual `capture-pane` snapshots taken while keystrokes are sent —
not a mockup. The chrome around them is drawn with PIL.

    python3 art/gif.py
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import threading
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "hermes_pilot", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
)
pkg = importlib.util.module_from_spec(spec)
sys.modules["hermes_pilot"] = pkg
spec.loader.exec_module(pkg)

from hermes_pilot import pilot_tmux as tmux  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
FRAMES = HERE / "frames"
FRAMES.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

W, H = 1200, 676  # even height: yuv420p/H.264 requires it
BG = (8, 9, 10)
PANEL = (14, 15, 17)
BAR = (20, 21, 24)
PAPER = (237, 231, 218)
DIM = (138, 135, 126)
FAINT = (74, 72, 66)
HOT = (255, 106, 26)
SCREEN = (217, 211, 199)

MONO = "/usr/share/fonts/TTF/JetBrainsMonoNerdFontMono-Regular.ttf"
MONO_B = "/usr/share/fonts/TTF/JetBrainsMonoNerdFontMono-Bold.ttf"
DISP = "/usr/share/fonts/TTF/LeagueGothic-Regular.ttf"

LINE = "written by an agent, one keystroke at a time"


def fonts():
    return {
        "mono": ImageFont.truetype(MONO, 13),
        "mono_s": ImageFont.truetype(MONO, 11),
        "mono_xs": ImageFont.truetype(MONO, 9),
        "mono_b": ImageFont.truetype(MONO_B, 13),
        "disp": ImageFont.truetype(DISP, 40),
        "disp_big": ImageFont.truetype(DISP, 96),
    }


def record() -> list[str]:
    tmux.close_all()
    Path("/tmp/pilot-reel.txt").unlink(missing_ok=True)
    tmux.open_session("vim -Nu NONE -n /tmp/pilot-reel.txt", name="reel", cols=100, rows=28, wait_ms=1200)
    frames: list[str] = []
    stop = threading.Event()

    def grab() -> None:
        last = None
        while not stop.is_set():
            try:
                shot = tmux.screen("reel", lines=30)
            except tmux.PilotError:
                break
            if shot != last:
                frames.append(shot)
                last = shot
            time.sleep(0.04)

    thread = threading.Thread(target=grab, daemon=True)
    thread.start()
    time.sleep(0.3)

    tmux.send("reel", keys=["i"], enter=False)
    time.sleep(0.25)
    for ch in LINE:
        tmux.send("reel", text=ch, enter=False)
        time.sleep(0.05)
    time.sleep(0.55)
    tmux.send("reel", keys=["Escape"], enter=False)
    time.sleep(0.35)
    for ch in ":wq":
        tmux.send("reel", text=ch, enter=False)
        time.sleep(0.12)
    tmux.send("reel", keys=["Enter"], enter=False)
    time.sleep(0.9)

    stop.set()
    thread.join(timeout=2)
    tmux.close("reel")
    return frames


def chrome(f: dict, screen_text: str, progress: float) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # frame
    d.rounded_rectangle([24, 20, W - 24, H - 20], radius=14, fill=PANEL, outline=(38, 40, 45), width=1)
    d.rounded_rectangle([24, 20, W - 24, 66], radius=14, fill=BAR)
    d.rectangle([24, 46, W - 24, 66], fill=BAR)
    for i, x in enumerate((44, 60, 76)):
        d.ellipse([x - 4, 39, x + 4, 47], fill=(43, 45, 50))
    d.text((100, 34), "vim  /tmp/pilot-reel.txt", font=f["mono_s"], fill=DIM)
    d.text((W - 250, 34), "pilot · real pane · 100×28", font=f["mono_xs"], fill=(81, 79, 72))

    # screen
    lines = screen_text.splitlines()[:27]
    y = 82
    for line in lines:
        d.text((44, y), line, font=f["mono"], fill=SCREEN)
        y += 19
    # cursor block while inserting
    if "-- INSERT --" in screen_text:
        target = next((ln for ln in lines if ln.strip().startswith(LINE[:3])), "")
        if target:
            idx = lines.index(target)
            x = 44 + int(len(target.rstrip()) * 7.83)
            d.rectangle([x, 82 + idx * 19 - 1, x + 7, 82 + idx * 19 + 14], fill=HOT)

    # footer
    d.rectangle([24, H - 74, W - 24, H - 20], fill=(11, 12, 14))
    d.text((44, H - 58), "the agent typed this", font=f["disp"], fill=PAPER)
    d.text((300, H - 50), "PILOT · a real TTY for a coding agent", font=f["mono_s"], fill=DIM)
    d.text((W - 300, H - 50), "hermes plugins enable pilot", font=f["mono_xs"], fill=HOT)
    # progress
    d.rectangle([44, H - 28, W - 44, H - 26], fill=(28, 30, 34))
    d.rectangle([44, H - 28, 44 + int((W - 88) * max(0.0, min(1.0, progress))), H - 26], fill=HOT)
    return img


def cards() -> list[Image.Image]:
    f = fonts()
    intro = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(intro)
    d.text((64, 150), "THE AGENT", font=f["disp_big"], fill=PAPER)
    d.text((64, 236), "TYPED THIS", font=f["disp_big"], fill=PAPER)
    d.rectangle([70, 350, 130, 356], fill=HOT)
    d.text((64, 390), "a real terminal, not a mockup", font=f["mono_s"], fill=DIM)
    d.text((64, H - 80), "$ pilot open vim", font=f["mono"], fill=SCREEN)
    outro = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(outro)
    d.text((64, 170), "PILOT", font=f["disp_big"], fill=PAPER)
    d.text((66, 280), "every agent can run a command.", font=f["mono"], fill=DIM)
    d.text((66, 310), "pilot lets it use a program.", font=f["mono"], fill=HOT)
    d.rectangle([70, 380, 130, 386], fill=HOT)
    d.text((64, 420), "github.com/LangerSword/hermes-pilot", font=f["mono_s"], fill=SCREEN)
    d.text((64, H - 80), "tmux · no api key · 21 tests", font=f["mono_xs"], fill=FAINT)
    return [intro, outro]


def main() -> int:
    if not tmux.available():
        print("tmux required")
        return 1
    shots = record()
    if not shots:
        print("no frames captured")
        return 1
    for old in FRAMES.glob("*.png"):
        old.unlink()

    f = fonts()
    intro, outro = cards()
    seq: list[Image.Image] = [intro] * 10
    for i, shot in enumerate(shots):
        seq.append(chrome(f, shot, i / max(1, len(shots) - 1)))
    seq += [seq[-1]] * 8 + [outro] * 24

    for idx, img in enumerate(seq):
        img.save(FRAMES / f"f{idx:04d}.png")

    mp4 = OUT / "pilot-vim.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-framerate", "12",
         "-i", str(FRAMES / "f%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-crf", "20", "-movflags", "+faststart", str(mp4)],
        check=True,
    )
    gif = OUT / "pilot-vim.gif"
    subprocess.run(
        ["magick", "-delay", "8", "-loop", "0", str(FRAMES / "f*.png"),
         "-layers", "Optimize", "-colors", "128", str(gif)],
        check=True,
    )
    print(f"frames: {len(seq)} · mp4: {mp4.stat().st_size // 1024} KB · gif: {gif.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
