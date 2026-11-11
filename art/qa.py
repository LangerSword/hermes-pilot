#!/usr/bin/env python3
"""Layout QA without eyes: chromium --dump-dom + an injected measurement script.

Reports viewport overflow, element boxes, font availability and text overflow.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "src"

MEASURE = """<script>
window.addEventListener('load', () => {
  const W = %d, H = %d, out = {
    vw: W, vh: H,
    sw: document.documentElement.scrollWidth,
    sh: document.documentElement.scrollHeight,
    fonts: {
      league: document.fonts.check("16px 'League Gothic'"),
      mono: document.fonts.check("16px 'JetBrains Mono Nerd Font Mono'"),
      sans: document.fonts.check("16px 'Google Sans Flex'")
    },
    boxes: {}, text: {}
  };
  for (const sel of ['.hdr', '.ftr', '.disp', '.frame', '.kicker']) {
    out.boxes[sel] = [...document.querySelectorAll(sel)].map(e => {
      const r = e.getBoundingClientRect();
      return [Math.round(r.x), Math.round(r.y), Math.round(r.right), Math.round(r.bottom)];
    });
  }
  out.text = [...document.querySelectorAll('.screen')].map(e => ({
    cw: e.clientWidth, sw: e.scrollWidth, ch: e.clientHeight, sh: e.scrollHeight
  }));
  out.overflow = [...document.querySelectorAll('body *')].filter(e => {
    const r = e.getBoundingClientRect();
    return r.right > W + 1 || r.bottom > H + 1 || r.left < -1 || r.top < -1;
  }).slice(0, 12).map(e => ({
    cls: String(e.className).slice(0, 40),
    r: Math.round(e.getBoundingClientRect().right),
    b: Math.round(e.getBoundingClientRect().bottom)
  }));
  document.title = 'QA::' + JSON.stringify(out);
});
</script>"""


def main() -> int:
    for html_path in sorted(SRC.glob("[0-9][0-9]-*.html")) + sorted(SRC.glob("icon-*.html")):
        m = re.search(r"-(\d+)x(\d+)\.html$", html_path.name)
        if not m:
            continue
        w, h = int(m.group(1)), int(m.group(2))
        html = html_path.read_text(encoding="utf-8")
        html = html.replace("</body>", MEASURE % (w, h) + "</body>")
        probe = SRC / f"qa-{html_path.name}"
        probe.write_text(html, encoding="utf-8")
        proc = subprocess.run(
            [
                "chromium", "--headless=new", "--no-sandbox", "--disable-gpu",
                "--hide-scrollbars", "--virtual-time-budget=3000", "--dump-dom",
                f"file://{probe}",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        match = re.search(r"<title>QA::(.*?)</title>", proc.stdout or "", re.S)
        print(f"\n### {html_path.name}")
        if not match:
            print("  no measurement (chromium failed):", (proc.stderr or "")[-300:])
            continue
        data = json.loads(match.group(1).replace("&quot;", '"'))
        print("  viewport:", data["vw"], "x", data["vh"],
              "| document:", data["sw"], "x", data["sh"])
        print("  fonts:", data["fonts"])
        for sel, boxes in data["boxes"].items():
            if boxes:
                print(f"  {sel}: {boxes}")
        print("  screens (client vs scroll):", data["text"])
        print("  overflow:", data["overflow"] or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
