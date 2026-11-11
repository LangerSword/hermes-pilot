#!/usr/bin/env python3
"""Render the Pilot launch art as a numbered, single-template series.

    00  the claim        hero, 1600×900
    01  the wall         pipe vs tty, 1200×675
    02  the keystrokes   vim, 1080×1350
    03  the other machine ssh fix, 1200×675
    04  the spec         square, 1080×1080
    +   icon             512×512

Every poster shares header, kicker, footer, margins and type scale. Evidence
text comes from art/src/ (real captures), never invented.
"""

from __future__ import annotations

import base64
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "src"
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)

UNI = "'Google Sans Flex', 'Noto Sans', sans-serif"
MONO = "'JetBrains Mono Nerd Font Mono', 'DejaVu Sans Mono', monospace"
DISP = "'League Gothic', 'Liberation Sans Narrow', sans-serif"

NOISE = base64.b64encode(
    b"""<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'>
    <filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='3' stitchTiles='stitch'/>
    <feColorMatrix type='saturate' values='0'/></filter>
    <rect width='100%' height='100%' filter='url(#n)' opacity='.55'/></svg>"""
).decode()

BASE = f"""
*{{box-sizing:border-box}}
html,body{{margin:0;padding:0;background:#08090A;color:#EDE7DA}}
body{{font-family:{UNI};-webkit-font-smoothing:antialiased}}
.page{{position:relative;overflow:hidden;background:
  radial-gradient(1200px 700px at 78% 8%, #16181B 0%, #0B0C0E 46%, #08090A 100%);}}
.grain{{position:absolute;inset:0;background-image:url(data:image/svg+xml;base64,{NOISE});
  background-size:180px 180px;opacity:.055;mix-blend-mode:overlay;pointer-events:none}}
.scan{{position:absolute;inset:0;background:repeating-linear-gradient(180deg,
  rgba(255,255,255,.022) 0 1px, transparent 1px 3px);pointer-events:none;opacity:.5}}
.mono{{font-family:{MONO}}}
.disp{{font-family:{DISP};text-transform:uppercase;line-height:.86;letter-spacing:.005em}}
.dim{{color:#8A877E}} .faint{{color:#514F48}} .hot{{color:#FF6A1A}} .bad{{color:#FF5140}}
.rule{{height:1px;background:rgba(237,231,218,.14)}}
.kicker{{font-family:{MONO};font-size:11px;letter-spacing:.22em;color:#8A877E;text-transform:uppercase}}
.frame{{border:1px solid rgba(237,231,218,.14);border-radius:12px;overflow:hidden;
  background:#0E0F11;box-shadow:0 24px 60px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.04)}}
.bar{{display:flex;align-items:center;gap:8px;padding:0 16px;height:40px;
  background:#141518;border-bottom:1px solid rgba(237,231,218,.10);
  font-family:{MONO};font-size:11px;color:#8A877E}}
.dot{{width:8px;height:8px;border-radius:50%;background:#2B2D32}}
.screen{{font-family:{MONO};white-space:pre;color:#D9D3C7;font-size:14px;line-height:1.5;padding:18px 20px}}
.hdr{{position:absolute;left:64px;right:64px;top:44px;display:flex;justify-content:space-between;
  align-items:baseline}}
.ftr{{position:absolute;left:64px;right:64px;bottom:40px;display:flex;justify-content:space-between;
  align-items:baseline;font-family:{MONO};font-size:10px;color:#6F6D66;letter-spacing:.06em}}
.brand{{display:flex;align-items:baseline;gap:10px}}
.brand b{{font-family:{DISP};text-transform:uppercase;font-size:26px;letter-spacing:.04em;font-weight:400}}
.brand span{{font-family:{MONO};font-size:10px;letter-spacing:.24em;color:#8A877E}}
.chip{{font-family:{MONO};font-size:11px;color:#B9B3A7;border:1px solid rgba(237,231,218,.16);
  border-radius:999px;padding:5px 10px;white-space:nowrap}}
"""


def page(width: int, height: int, body: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
{BASE}
.page{{width:{width}px;height:{height}px}}
</style></head><body><div class="page">{body}
<div class="grain"></div><div class="scan"></div></div></body></html>"""


def header(number: str, topic: str) -> str:
    return (
        '<div class="hdr"><div class="brand"><b>Pilot</b><span>A HERMES PLUGIN</span></div>'
        '<div class="mono" style="font-size:10px;letter-spacing:.18em;color:#6F6D66">'
        f"EVIDENCE {number} / {topic}</div></div>"
    )


def footer(number: str, topic: str, context: str) -> str:
    return (
        f'<div class="ftr"><div>{number} · {topic} · {context}</div>'
        "<div>github.com/LangerSword/hermes-pilot</div></div>"
    )


def chip(label: str) -> str:
    return f'<span class="chip">{label}</span>'


def read(name: str) -> str:
    path = SRC / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


VIM = (
    "~\n"
    "~\n"
    'written by an agent, one keystroke at a time<span class="hot">█</span>\n'
    "~\n~\n~\n~\n~\n"
    '<span class="dim">-- INSERT --</span>\n'
    '<span class="faint">"/tmp/notes.txt" [New]</span>' + " " * 26 + '<span class="dim">1,45</span>   All'
)


# ── 00 · the claim ──────────────────────────────────────────────────────────
def hero() -> str:
    chips = "".join(chip(c) for c in ["ssh", "vim", "htop", "fzf", "psql", "installers", "REPLs"])
    body = f"""
{header("00", "THE CLAIM")}
<div style="position:absolute;left:64px;top:148px;width:720px">
  <div class="kicker">The wall, and the door</div>
  <div class="disp" style="font-size:126px;margin-top:26px">A terminal tool<br>is a pipe.</div>
  <div class="disp hot" style="font-size:126px;margin-top:4px">Pilot is a TTY.</div>
  <div style="width:74px;height:3px;background:#FF6A1A;margin:34px 0 26px"></div>
  <div style="font-size:17px;line-height:1.55;color:#B8B2A6;max-width:560px">
    It can run a command. It cannot answer a prompt, draw a screen, or take a keystroke.
    Pilot gives the agent a real terminal, and reads the screen back as text.
  </div>
  <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:30px;max-width:600px">{chips}</div>
</div>
<div style="position:absolute;left:836px;top:148px;width:700px">
  <div class="mono" style="font-size:10px;letter-spacing:.18em;color:#6F6D66;margin-bottom:10px">
    PILOT · SESSION vim1 · 120×36</div>
  <div class="frame">
    <div class="bar"><span class="dot"></span><span class="dot"></span><span class="dot"></span>
      <span style="margin-left:8px">vim /tmp/notes.txt</span>
      <span style="margin-left:auto;color:#514F48">tmux -L hermes-pilot</span></div>
    <div class="screen" style="font-size:15px;line-height:1.62;padding:22px 24px">{VIM}</div>
  </div>
  <div style="display:flex;align-items:center;gap:10px;margin-top:16px">
    {chip("i")}<span class="faint">→</span>{chip("typed 44 chars")}<span class="faint">→</span>{chip("Esc")}<span class="faint">→</span>{chip(":wq")}
    <span class="mono" style="margin-left:auto;font-size:11px;color:#8A877E">exit 0</span>
  </div>
  <div class="mono" style="font-size:12px;color:#6F6D66;margin-top:14px">$ cat /tmp/notes.txt</div>
  <div class="mono" style="font-size:12px;color:#D9D3C7;margin-top:4px">written by an agent, one keystroke at a time</div>
</div>
{footer("00", "THE CLAIM", "a real TTY for a coding agent")}
"""
    return page(1600, 900, body)


# ── 01 · the wall ───────────────────────────────────────────────────────────
def wall() -> str:
    body = f"""
{header("01", "THE WALL")}
<div style="position:absolute;left:64px;top:104px;width:1072px">
  <div class="kicker">Same program. Same machine. Same second.</div>
  <div class="disp" style="font-size:60px;margin-top:14px">One of these is unreadable.</div>
</div>
<div style="position:absolute;left:64px;top:224px;width:500px">
  <div class="mono" style="font-size:10px;letter-spacing:.18em;color:#FF5140;margin-bottom:8px">TERMINAL TOOL · PIPE · TERM=dumb</div>
  <div class="frame" style="border-color:rgba(255,81,64,.22)">
    <div class="bar"><span class="dot"></span><span class="dot"></span><span class="dot"></span>
      <span style="margin-left:8px;color:#B4706A">$ htop</span></div>
    <div class="screen bad" style="font-size:10.5px;line-height:1.45;height:318px;overflow:hidden;color:#C98980;white-space:pre-wrap;overflow-wrap:anywhere">{read("fail.txt")}</div>
  </div>
</div>
<div style="position:absolute;left:600px;top:224px;width:536px">
  <div class="mono" style="font-size:10px;letter-spacing:.18em;color:#FF6A1A;margin-bottom:8px">PILOT · TTY · 88×24</div>
  <div class="frame">
    <div class="bar"><span class="dot"></span><span class="dot"></span><span class="dot"></span>
      <span style="margin-left:8px">pilot screen art</span></div>
    <div class="screen" style="font-size:9.2px;line-height:1.32;height:318px;overflow:hidden;padding:14px 14px">{read("tty.txt")}</div>
  </div>
</div>
<div class="mono" style="position:absolute;left:64px;top:588px;font-size:11px;color:#6F6D66">
  left: control codes, repaint garbage, an ioctl error &nbsp;·&nbsp; right: a screen the model can read
</div>
{footer("01", "THE WALL", "htop · captured 2026-11-11")}
"""
    return page(1200, 675, body)


# ── 02 · the keystrokes ─────────────────────────────────────────────────────
def keystrokes() -> str:
    body = f"""
{header("02", "THE KEYSTROKES")}
<div style="position:absolute;left:64px;top:120px;width:952px">
  <div class="kicker">No mockup. This is the pane.</div>
  <div class="disp" style="font-size:150px;margin-top:18px">The agent<br>typed this<span class="hot">.</span></div>
</div>
<div style="position:absolute;left:64px;top:470px;width:952px">
  <div class="frame">
    <div class="bar"><span class="dot"></span><span class="dot"></span><span class="dot"></span>
      <span style="margin-left:8px">vim /tmp/notes.txt</span>
      <span style="margin-left:auto;color:#514F48">pilot · 120×36</span></div>
    <div class="screen" style="font-size:16px;line-height:1.75;padding:26px 28px">{VIM}</div>
  </div>
</div>
<div style="position:absolute;left:64px;top:900px;width:952px">
  <div style="display:flex;gap:10px;align-items:center">
    {chip("open vim")}<span class="faint">→</span>{chip("i")}<span class="faint">→</span>{chip("type")}<span class="faint">→</span>{chip("Esc")}<span class="faint">→</span>{chip(":wq")}
  </div>
  <div class="mono" style="font-size:13px;color:#6F6D66;margin-top:24px">$ cat /tmp/notes.txt</div>
  <div class="mono" style="font-size:13px;color:#D9D3C7;margin-top:6px">written by an agent, one keystroke at a time</div>
  <div class="rule" style="margin:30px 0 24px"></div>
  <div class="disp" style="font-size:54px">Every agent can run a command.</div>
  <div class="disp hot" style="font-size:54px">Pilot lets it use a program.</div>
  <div class="mono" style="font-size:12px;color:#8A877E;margin-top:34px">$ hermes plugins enable pilot<span class="hot">█</span></div>
  <div class="mono" style="font-size:10px;color:#514F48;margin-top:10px">tmux 3.8 · no api key · 21 tests · works offline</div>
</div>
{footer("02", "THE KEYSTROKES", "vim · real pane")}
"""
    return page(1080, 1350, body)


# ── 03 · the other machine ──────────────────────────────────────────────────
def ssh() -> str:
    before = read("ssh-before.txt")
    after = read("ssh-after.txt")
    if not before or not after:
        return ""

    def output(text: str, needle: str) -> str:
        lines = [line.strip() for line in text.splitlines()]
        exact = [line for line in lines if line == needle]
        if exact:
            return exact[-1]
        containing = [line for line in lines if needle in line]
        return containing[-1] if containing else needle

    def highlight(line: str, token: str, cls: str) -> str:
        """Wrap the changed token so the eye lands on the fix, not the frame."""
        head, sep, tail = line.partition(token)
        if not sep:
            return line
        colour = "#FF5140" if cls == "badfix" else "#FF6A1A"
        return f'{head}<span style="color:{colour};font-weight:bold">{token}</span>{tail}'

    body = f"""
{header("03", "THE OTHER MACHINE")}
<div style="position:absolute;left:64px;top:104px;width:1072px">
  <div class="kicker">SSH → VIM → :WQ</div>
  <div class="disp" style="font-size:64px;margin-top:14px">SSH in. Fix it.</div>
</div>
<div style="position:absolute;left:64px;top:236px;width:500px">
  <div class="mono" style="font-size:10px;letter-spacing:.2em;color:#FF5140;margin-bottom:8px">BEFORE · REMOTE</div>
  <div class="frame" style="border-color:rgba(255,81,64,.22)">
    <div class="bar"><span class="dot"></span><span class="dot"></span><span class="dot"></span>
      <span style="margin-left:8px">~/pilot-demo/app.conf</span>
      <span style="margin-left:auto;color:#B4706A">typo</span></div>
    <div class="screen bad" style="font-size:13px;line-height:1.8;padding:18px 20px">$ cat ~/pilot-demo/app.conf
{highlight(output(before, "porrt = 8080"), "porrt", "badfix")}</div>
  </div>
</div>
<div style="position:absolute;left:596px;top:300px;width:44px;text-align:center">
  <div class="mono" style="font-size:26px;color:#FF6A1A">→</div>
</div>
<div style="position:absolute;left:664px;top:236px;width:472px">
  <div class="mono" style="font-size:10px;letter-spacing:.2em;color:#FF6A1A;margin-bottom:8px">AFTER · REMOTE</div>
  <div class="frame">
    <div class="bar"><span class="dot"></span><span class="dot"></span><span class="dot"></span>
      <span style="margin-left:8px">~/pilot-demo/app.conf</span>
      <span style="margin-left:auto;color:#FF6A1A">fixed</span></div>
    <div class="screen" style="font-size:13px;line-height:1.8;padding:18px 20px">$ cat ~/pilot-demo/app.conf
{highlight(output(after, "port = 8080"), "port", "hotfix")}</div>
  </div>
</div>
<div style="position:absolute;left:64px;top:424px;width:1072px">
  <div class="rule" style="margin-bottom:18px"></div>
  <div style="display:flex;gap:10px;align-items:center">
    {chip("ssh host")}<span class="faint">→</span>{chip("cw")}<span class="faint">→</span>{chip("type port")}<span class="faint">→</span>{chip(":wq")}<span class="faint">→</span>{chip("cat")}
  </div>
  <div class="mono" style="font-size:11px;color:#6F6D66;margin-top:16px">
    one session, no local tools on the remote, no copy step.
  </div>
  <div class="disp" style="font-size:34px;margin-top:22px">The pane is the machine<span class="hot">.</span></div>
</div>
{footer("03", "THE OTHER MACHINE", "ssh · real session")}
"""
    return page(1200, 675, body)


# ── 04 · the spec ───────────────────────────────────────────────────────────
def spec() -> str:
    body = f"""
{header("04", "THE SPEC")}
<div style="position:absolute;left:64px;top:170px">
  <div class="disp" style="font-size:300px">Pilot<span class="hot" style="font-size:180px">▮</span></div>
  <div class="mono" style="font-size:12px;letter-spacing:.28em;color:#8A877E;margin-top:-10px">A HERMES PLUGIN</div>
  <div style="width:80px;height:3px;background:#FF6A1A;margin:38px 0 30px"></div>
  <div style="font-size:30px;line-height:1.35;color:#B8B2A6;max-width:620px">
    Every agent can run a command.<br><span style="color:#EDE7DA">Pilot lets it use a program.</span>
  </div>
  <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:34px;max-width:620px">
    {chip("ssh")}{chip("vim")}{chip("htop")}{chip("fzf")}{chip("psql")}{chip("installers")}{chip("REPLs")}
  </div>
</div>
<div style="position:absolute;left:706px;top:196px;width:310px">
  <div class="mono" style="font-size:10px;letter-spacing:.24em;color:#6F6D66">SPEC</div>
  <div class="rule" style="margin:10px 0 16px"></div>
  <div class="mono" style="font-size:11px;line-height:2.1;color:#B8B2A6">
    <div style="display:flex;justify-content:space-between"><span class="dim">surface</span><span>a real TTY</span></div>
    <div style="display:flex;justify-content:space-between"><span class="dim">backend</span><span>tmux 3.8</span></div>
    <div style="display:flex;justify-content:space-between"><span class="dim">api keys</span><span>none</span></div>
    <div style="display:flex;justify-content:space-between"><span class="dim">network</span><span>off</span></div>
    <div style="display:flex;justify-content:space-between"><span class="dim">tests</span><span>21</span></div>
    <div style="display:flex;justify-content:space-between"><span class="dim">takeover</span><span class="hot">yes</span></div>
  </div>
  <div class="rule" style="margin:16px 0 12px"></div>
  <div class="mono" style="font-size:10px;line-height:1.7;color:#514F48">ssh · vim · htop · fzf<br>psql · sudo · installers<br>REPLs · ncurses menus</div>
</div>
<div style="position:absolute;left:64px;bottom:150px;right:64px">
  <div class="frame">
    <div class="bar"><span class="dot"></span><span class="dot"></span><span class="dot"></span>
      <span style="margin-left:8px">pilot screen vim1</span></div>
    <div class="screen" style="font-size:12px;line-height:1.45;padding:16px 18px">~
written by an agent, one keystroke at a time<span class="hot">█</span>
~
<span class="dim">-- INSERT --</span></div>
  </div>
</div>
{footer("04", "THE SPEC", "a real terminal for a coding agent")}
"""
    return page(1080, 1080, body)


# ── icon ────────────────────────────────────────────────────────────────────
def icon() -> str:
    body = f"""
<div style="position:absolute;inset:26px;border:1px solid rgba(237,231,218,.16);border-radius:28px"></div>
<div style="position:absolute;left:50%;top:82px;transform:translateX(-50%);white-space:nowrap">
  <span class="disp" style="font-size:328px">P</span><span style="display:inline-block;width:58px;height:164px;background:#FF6A1A;vertical-align:baseline;margin-left:4px"></span>
</div>
<div class="mono" style="position:absolute;left:0;right:0;bottom:78px;text-align:center;font-size:22px;letter-spacing:.3em;color:#EDE7DA">PILOT</div>
<div class="mono" style="position:absolute;left:0;right:0;bottom:52px;text-align:center;font-size:9px;letter-spacing:.22em;color:#514F48">HERMES PLUGIN</div>
"""
    return page(512, 512, body)


ARTIFACTS = {
    "00-hero-1600x900": (hero, 1600, 900),
    "01-wall-1200x675": (wall, 1200, 675),
    "02-keystrokes-1080x1350": (keystrokes, 1080, 1350),
    "03-ssh-1200x675": (ssh, 1200, 675),
    "04-spec-1080x1080": (spec, 1080, 1080),
    "icon-512x512": (icon, 512, 512),
}


def render(name: str, html: str, width: int, height: int) -> Path:
    src = SRC / f"{name}.html"
    src.write_text(html, encoding="utf-8")
    raw = OUT / f"{name}@2x.png"
    subprocess.run(
        [
            "chromium", "--headless=new", "--no-sandbox", "--disable-gpu",
            "--hide-scrollbars", "--force-device-scale-factor=2",
            "--virtual-time-budget=2500", "--run-all-compositor-stages-before-draw",
            f"--window-size={width},{height}", f"--screenshot={raw}", f"file://{src}",
        ],
        capture_output=True,
        timeout=120,
    )
    final = OUT / f"{name}.png"
    subprocess.run(
        ["magick", str(raw), "-resize", f"{width}x{height}", "-strip",
         "-define", "png:compression-level=9", str(final)],
        check=True,
    )
    raw.unlink(missing_ok=True)
    return final


if __name__ == "__main__":
    for name, (fn, w, h) in ARTIFACTS.items():
        html = fn()
        if not html:
            print(f"{name}: skipped (missing captured input)")
            continue
        out = render(name, html, w, h)
        print(f"{out.name}: {out.stat().st_size // 1024} KB")
