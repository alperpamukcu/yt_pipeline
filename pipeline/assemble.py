"""Video montaj: dikey (9:16) veya yatay; stok klipler + ses + kelime-kelime altyazi -> mp4."""
import logging
import random
import subprocess
from pathlib import Path

log = logging.getLogger("assemble")

IMAGE_EXT = {".jpg", ".jpeg", ".png"}


def _run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg hatasi:\n{r.stderr[-2000:]}")


def _duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip())


def _resolution(cfg: dict) -> tuple[int, int]:
    key = "resolution_vertical" if cfg.get("format") == "vertical" else "resolution_horizontal"
    w, h = cfg["video"][key].split("x")
    return int(w), int(h)


def _normalize_clip(src: Path, dest: Path, w: int, h: int, fps: int, seg_dur: float) -> None:
    """Her klibi ayni codec/cozunurluk/fps'e getir; goruntuyse Ken Burns zoom uygula."""
    if src.suffix.lower() in IMAGE_EXT:
        # hareket hissi icin yavas pan (zoompan cok yavas kaldigi icin animasyonlu crop)
        vf = (f"scale={int(w*1.2)}:-2,"
              f"crop={w}:{h}:x='(in_w-out_w)*t/{seg_dur:.2f}':y='(in_h-out_h)/2'")
        cmd = ["ffmpeg", "-y", "-loop", "1", "-t", f"{seg_dur:.2f}", "-r", str(fps), "-i", str(src),
               "-vf", vf, "-c:v", "libx264", "-preset", "fast", "-crf", "20",
               "-pix_fmt", "yuv420p", "-an", str(dest)]
    else:
        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps}"
        cmd = ["ffmpeg", "-y", "-i", str(src), "-t", f"{seg_dur:.2f}",
               "-vf", vf, "-c:v", "libx264", "-preset", "fast", "-crf", "20",
               "-pix_fmt", "yuv420p", "-an", str(dest)]
    _run(cmd)


def _subtitle_filter(workdir: Path, cfg: dict, h: int) -> str | None:
    ass = workdir / "captions.ass"
    if ass.exists():  # kelime kelime senkron karaoke altyazi
        p = str(ass.resolve()).replace('\\', '/').replace(':', '\\:')
        return f"ass='{p}'"
    srt = workdir / "narration.srt"
    if srt.exists():
        p = str(srt.resolve()).replace('\\', '/').replace(':', '\\:')
        return f"subtitles='{p}':force_style='FontSize=18,Outline=1,MarginV=40'"
    return None


def build_video(audio: Path, script: dict, cfg: dict, workdir: Path, clips: list[Path]) -> Path:
    v = cfg["video"]
    w, h = _resolution(cfg)
    fps = v["fps"]
    duration = _duration(audio)
    out = workdir / "video.mp4"

    log.info("Montaj: %dx%d, %.1f sn, %d klip", w, h, duration, len(clips))

    # her klibe esit sure ver, normalize et, concat ile birlestir
    random.shuffle(clips)
    n = max(min(len(clips), int(duration // 3) or 1), 1)
    seg = duration / n
    norm_dir = workdir / "norm"
    norm_dir.mkdir(exist_ok=True)
    norm_paths = []
    for i in range(n):
        src = clips[i % len(clips)]
        dest = norm_dir / f"seg_{i:02d}.mp4"
        _normalize_clip(src, dest, w, h, fps, seg)
        norm_paths.append(dest)

    concat = workdir / "concat.txt"
    concat.write_text("\n".join(f"file '{p.resolve()}'" for p in norm_paths), encoding="utf-8")

    vf = (_subtitle_filter(workdir, cfg, h) if v.get("subtitle") else None) or "null"

    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-i", str(audio)]
    music = v.get("bg_music", "")
    if music and Path(music).exists():
        cmd += ["-i", music,
                "-filter_complex",
                f"[0:v]{vf}[vout];[1:a]volume=1.0[voice];[2:a]volume={v['bg_music_volume']}[m];"
                f"[voice][m]amix=inputs=2:duration=first[a]",
                "-map", "[vout]", "-map", "[a]"]
    else:
        cmd += ["-filter_complex", f"[0:v]{vf}[vout]", "-map", "[vout]", "-map", "1:a"]

    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-shortest", "-t", f"{duration:.2f}",
            "-movflags", "+faststart", str(out)]
    _run(cmd)

    if not out.exists() or out.stat().st_size < 10_000:
        raise RuntimeError("Video ciktisi olusmadi ya da bozuk.")
    log.info("Video hazir: %s (%.1f MB)", out, out.stat().st_size / 1e6)
    return out
