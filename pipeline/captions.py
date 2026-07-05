"""Sesle senkron, kelime kelime takip eden altyazi (ASS karaoke).

words.json'daki zamanlamalardan ASS dosyasi uretir: 2-3 kelimelik gruplar
ekranda buyuk/kalin gorunur, konusulan kelime sari renkle 'yanar' (\\k karaoke).
"""
import json
import logging
from pathlib import Path

log = logging.getLogger("captions")

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{size},&H0000D7FF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,{outline},2,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ts(sec: float) -> str:
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def build(cfg: dict, workdir: Path, words_per_cue: int = 3) -> Path | None:
    words_file = workdir / "words.json"
    if not words_file.exists():
        log.warning("words.json yok, altyazi atlaniyor.")
        return None
    words = json.loads(words_file.read_text(encoding="utf-8"))
    if not words:
        return None

    vertical = cfg.get("format") == "vertical"
    w, h = (1080, 1920) if vertical else (1920, 1080)
    c = cfg["video"].get("captions", {})

    header = ASS_HEADER.format(
        w=w, h=h,
        font=c.get("font", "DejaVu Sans"),
        size=c.get("size", 96 if vertical else 64),
        outline=c.get("outline", 5),
        margin_v=int(h * c.get("position", 0.30)),  # alttan oran
    )

    lines = []
    for i in range(0, len(words), words_per_cue):
        group = words[i:i + words_per_cue]
        start, end = group[0]["start"], group[-1]["end"]
        parts = []
        for j, wd in enumerate(group):
            # karaoke suresi: kelimenin bitisinden bir sonrakinin baslangicina kadar
            nxt = group[j + 1]["start"] if j + 1 < len(group) else end
            k = max(int((nxt - wd["start"]) * 100), 1)
            parts.append(f"{{\\k{k}}}{wd['word'].upper()}")
        lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Cap,,0,0,0,,{' '.join(parts)}")

    out = workdir / "captions.ass"
    out.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    log.info("Senkron altyazi hazir: %s (%d cue)", out, len(lines))
    return out
