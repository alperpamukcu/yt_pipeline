"""Kapak gorseli: dikeyde 1080x1920 (TikTok/Reels kapak), yatayda 1280x720."""
import logging
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger("thumbnail")


def _load_font(path: str, size: int):
    if path and Path(path).exists():
        return ImageFont.truetype(path, size)
    for candidate in (
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default(size)


def create(title: str, cfg: dict, workdir: Path) -> Path:
    t = cfg["thumbnail"]
    vertical = cfg.get("format") == "vertical"
    W, H = (1080, 1920) if vertical else (1280, 720)
    img = Image.new("RGB", (W, H), t["bg_color"])
    draw = ImageDraw.Draw(img)

    bar = 18 if vertical else 14
    draw.rectangle([0, H - bar, W, H], fill=t["text_color"])
    draw.rectangle([0, 0, bar, H], fill=t["text_color"])

    wrap = 12 if vertical else 18
    lines = textwrap.wrap(title.upper(), width=wrap)[:5]
    size = (150 if len(lines) <= 3 else 118) if vertical else (110 if len(lines) <= 2 else 88)
    font = _load_font(t.get("font", ""), size)

    # en uzun satir kenar boslugu birakarak sigana kadar fontu kucult
    max_w = W - 2 * bar - 40
    while size > 40:
        widths = [draw.textbbox((0, 0), ln, font=font)[2] for ln in lines]
        if max(widths) <= max_w:
            break
        size = int(size * 0.92)
        font = _load_font(t.get("font", ""), size)

    line_h = size + 20
    y = (H - line_h * len(lines)) // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (W - (bbox[2] - bbox[0])) // 2
        draw.text((x + 5, y + 5), line, font=font, fill="#000000")
        draw.text((x, y), line, font=font, fill=t["text_color"])
        y += line_h

    out = workdir / ("cover.jpg" if vertical else "thumbnail.jpg")
    img.save(out, quality=92)
    log.info("Kapak hazir: %s", out)
    return out
