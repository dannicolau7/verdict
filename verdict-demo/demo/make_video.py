"""Render a short square video (1080x1080, ~25 s) from a real `verdict diff` result.

    python demo/make_video.py --diff out/verdict-diff.json \
        --patch demo/subtle-skip-lookup.patch --out out/verdict-demo.mp4

Every number on screen comes from the verdict-diff.json you pass in; nothing is
made up. A skipped or incomplete run is refused. `--preview` stamps every frame
"PREVIEW" for checking the layout with test data. Needs Pillow and ffmpeg.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W = H = 1080
FPS = 30
PAD = 80
BG, FG, MUTED = (17, 19, 24), (236, 238, 242), (140, 146, 158)
RED, GREEN, AMBER, PANEL = (239, 99, 99), (99, 210, 140), (240, 180, 80), (28, 31, 38)

_SANS = ["/usr/share/fonts/opentype/inter/Inter-SemiBold.otf",
         "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
_MONO = ["/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Regular.ttf",
         "/System/Library/Fonts/Menlo.ttc",
         "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]


def _font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


SANS = {s: _font(_SANS, s) for s in (34, 44, 60, 76)}
MONO = {s: _font(_MONO, s) for s in (28, 32)}


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for w in words:
        trial = f"{line} {w}".strip()
        if draw.textlength(trial, font=font) <= width:
            line = trial
        else:
            lines.append(line)
            line = w
    return lines + [line] if line else lines


class Renderer:
    def __init__(self, out: Path, preview: bool) -> None:
        self.preview = preview
        self.proc = subprocess.Popen(
            ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264",
             "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart", str(out)],
            stdin=subprocess.PIPE,
        )

    def frame(self, img: Image.Image, seconds: float = 1 / FPS) -> None:
        if self.preview:
            d = ImageDraw.Draw(img)
            d.text((W - PAD, H - 50), "PREVIEW · not a real run", font=SANS[34], fill=AMBER,
                   anchor="rs")
        data = img.tobytes()
        for _ in range(max(1, round(seconds * FPS))):
            assert self.proc.stdin is not None
            self.proc.stdin.write(data)

    def close(self) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.close()
        if self.proc.wait() != 0:
            raise SystemExit("ffmpeg failed")


def canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG)
    return img, ImageDraw.Draw(img)


def text_block(d, lines, y, font, fill=FG, gap=1.25) -> int:
    for line in lines:
        d.text((PAD, y), line, font=font, fill=fill)
        y += int(font.size * gap)
    return y


# --- scenes -------------------------------------------------------------------


def scene_title(r: Renderer) -> None:
    img, d = canvas()
    lines = _wrap(d, "Did this prompt change make my agent worse?", SANS[76], W - 2 * PAD)
    text_block(d, lines, 330, SANS[76])
    d.text((PAD, 760), "A real eval run with Verdict", font=SANS[44], fill=MUTED)
    r.frame(img, 3.0)


def _items(lines: list[str]) -> list[str]:
    """Join a diff side's lines into bullet items ("- rule" starts a new one)."""
    items: list[str] = []
    for ln in lines:
        text = ln.strip()
        if not text:
            continue
        if text.startswith("- ") or not items:
            items.append(text.removeprefix("- "))
        else:
            items[-1] += " " + text
    return items


def _one_line(d, text: str, font, width: int) -> str:
    if d.textlength(text, font=font) <= width:
        return text
    while text and d.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def scene_patch(r: Renderer, patch: str) -> None:
    body = [ln for ln in patch.splitlines() if not ln.startswith(("---", "+++"))]
    removed = _items([ln[1:] for ln in body if ln.startswith("-")])
    added = _items([ln[1:] for ln in body if ln.startswith("+")])
    img, d = canvas()
    d.text((PAD, 120), "The change to the system prompt", font=SANS[44], fill=FG)
    y, width = 220, W - 2 * PAD - 40
    if added:
        for ln in _wrap(d, "+ " + " ".join(added), MONO[32], width)[:4]:
            d.text((PAD, y), ln, font=MONO[32], fill=GREEN)
            y += 48
        y += 30
    label = "1 rule deleted" if len(removed) == 1 else f"{len(removed)} rules deleted"
    d.text((PAD, y), label, font=SANS[34], fill=MUTED)
    y += 60
    for item in removed[:5]:
        d.text((PAD, y), _one_line(d, "- " + item, MONO[28], width), font=MONO[28], fill=RED)
        y += 44
    d.text((PAD, max(y + 70, 820)), "Easy to approve in code review.", font=SANS[44], fill=FG)
    r.frame(img, 5.0)


def scene_command(r: Renderer, result: dict) -> None:
    cmd = "$ verdict diff --base main"
    info = [f"  {result['n_cases']} cases × {result['runs']} runs per side",
            f"  base {result['base_sha'][:7]}  →  head {result['head_sha'][:7]}",
            "  judging both sides…"]
    for i in range(len(cmd) + 1):  # typing effect
        img, d = canvas()
        d.text((PAD, 200), "Before merge", font=SANS[60], fill=FG)
        d.text((PAD, 400), cmd[:i], font=MONO[32], fill=GREEN)
        r.frame(img, 0.045)
    for k in range(len(info) + 1):
        img, d = canvas()
        d.text((PAD, 200), "Before merge", font=SANS[60], fill=FG)
        d.text((PAD, 400), cmd, font=MONO[32], fill=GREEN)
        text_block(d, info[:k], 470, MONO[28], fill=MUTED, gap=1.6)
        r.frame(img, 0.7)
    r.frame(img, 0.8)


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def scene_result(r: Renderer, result: dict) -> None:
    s = result["suite"]
    failed = not result["gate"]["passed"]
    # Every case whose head pass count fell, worst first (not only the significant ones).
    regs = sorted((c for c in result["cases"] if c["delta"] < 0), key=lambda c: c["delta"])
    img, d = canvas()
    head = "Regression caught" if failed else "No regression"
    d.text((PAD, 110), head, font=SANS[76], fill=RED if failed else GREEN)
    d.text((PAD, 230), "Pass rate", font=SANS[34], fill=MUTED)
    d.text((PAD, 275), f"{_pct(s['base']['pass_rate'])}  →  {_pct(s['head']['pass_rate'])}",
           font=SANS[76], fill=FG)
    note = f"p = {s['p_value']:.3g}" if s["p_value"] >= 0.001 else "p < 0.001"
    d.text((PAD, 375), f"{s['delta'] * 100:+.0f} points · {note}", font=SANS[34], fill=MUTED)

    y = 470
    if regs:
        d.text((PAD, y), f"Cases that got worse ({len(regs)})", font=SANS[34], fill=MUTED)
        y += 60
        for c in regs[:4]:
            d.text((PAD, y), c["case_id"], font=MONO[28], fill=FG)
            d.text((W - PAD, y), f"{c['base']['passed']}/{c['base']['n']} → "
                   f"{c['head']['passed']}/{c['head']['n']}", font=MONO[28], fill=RED, anchor="ra")
            y += 50
    reason = next((c["head_failures"][0] for c in regs if c["head_failures"]), None)
    if reason:
        y += 20
        reason = reason.removeprefix("trajectory: ")
        for part in _wrap(d, f"Why: {reason}", SANS[34], W - 2 * PAD)[:3]:
            d.text((PAD, y), part, font=SANS[34], fill=AMBER)
            y += 46
    r.frame(img, 7.5)


def scene_end(r: Renderer) -> None:
    img, d = canvas()
    text_block(d, ["CI for prompts, skills", "and model changes."], 330, SANS[76])
    d.text((PAD, 640), "pip install verdict-eval", font=MONO[32], fill=GREEN)
    d.text((PAD, 700), "github.com/dannicolau7/verdict", font=MONO[32], fill=FG)
    r.frame(img, 4.0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--diff", required=True, type=Path)
    ap.add_argument("--patch", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--preview", action="store_true")
    args = ap.parse_args(argv)

    result = json.loads(args.diff.read_text(encoding="utf-8"))
    if result.get("status") != "completed" or not result.get("suite"):
        print("verdict-diff.json is not a completed run; refusing to render.", file=sys.stderr)
        return 1
    broken = [c for c in result["gate"]["checks"] if c["name"] == "run_errors" and c["breached"]]
    if broken:
        print("Too many runs failed or went unjudged; refusing to render:", file=sys.stderr)
        for c in broken:
            print("  " + c["detail"], file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    r = Renderer(args.out, args.preview)
    scene_title(r)
    scene_patch(r, args.patch.read_text(encoding="utf-8"))
    scene_command(r, result)
    scene_result(r, result)
    scene_end(r)
    r.close()
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
