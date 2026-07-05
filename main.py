#!/usr/bin/env python3
"""
Dikey Video Otomasyon Pipeline (TikTok / Reels / Shorts)
Akis: konu -> senaryo -> TTS -> stok klipler -> montaj -> kapak -> POST KIT -> [insan onayi] -> YouTube

Kullanim:
    python main.py --auto           # TEK TIK: topics.txt'teki TUM konulari isle
    python main.py                  # sadece siradaki konuyu isle
    python main.py --review         # onay bekleyenleri listele
    python main.py --approve <id>   # YouTube Shorts olarak yukle (TikTok/IG paylasimi post_kit'ten manuel)
"""
import argparse
import json
import logging
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path

import yaml

from pipeline import script_gen, tts, assemble, thumbnail, upload, visuals, captions

BASE = Path(__file__).parent
OUTPUT = BASE / "output"
STATE_FILE = OUTPUT / "state.json"

OUTPUT.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(),
              logging.FileHandler(OUTPUT / "pipeline.log", encoding="utf-8")],
)
log = logging.getLogger("main")


def load_config() -> dict:
    with open(BASE / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"done_topics": [], "pending_review": [], "uploaded": []}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def pending_topics(cfg: dict, state: dict) -> list[str]:
    topics_file = BASE / cfg["topics_file"]
    if not topics_file.exists():
        log.error("Konu dosyasi yok: %s", topics_file)
        return []
    return [ln.strip() for ln in topics_file.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
            and ln.strip() not in state["done_topics"]]


def make_post_kit(workdir: Path, video: Path, cover: Path, script: dict) -> Path:
    """TikTok/Instagram'a hazir paket: video + kapak + gonderi metni."""
    kit = workdir / "post_kit"
    kit.mkdir(exist_ok=True)
    shutil.copy(video, kit / "video_9x16.mp4")
    shutil.copy(cover, kit / "cover.jpg")
    (kit / "caption.txt").write_text(script["caption"], encoding="utf-8")
    (kit / "youtube_meta.txt").write_text(
        f"BASLIK: {script['title']}\n\nACIKLAMA:\n{script['description']}\n\n"
        f"ETIKETLER: {', '.join(script['tags'])}", encoding="utf-8")
    return kit


def process_part(video_id: str, topic: str, script: dict, cfg: dict, state: dict) -> None:
    """Tek bir kisa videoyu uret (senaryo hazir)."""
    workdir = OUTPUT / video_id
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "script.json").write_text(
        json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")

    audio = tts.synthesize(script["narration"], cfg, workdir)
    captions.build(cfg, workdir)                       # sesle senkron kelime altyazisi
    clips = visuals.generate(script, cfg, workdir)     # AI gorsel / stok / local
    video = assemble.build_video(audio, script, cfg, workdir, clips)
    cover = thumbnail.create(script["title"], cfg, workdir)
    kit = make_post_kit(workdir, video, cover, script)

    state["pending_review"].append({
        "id": video_id, "topic": topic, "title": script["title"],
        "description": script["description"], "tags": script["tags"],
        "video": str(video), "thumbnail": str(cover), "post_kit": str(kit),
    })
    save_state(state)
    log.info("HAZIR -> %s", kit)
    log.info("YouTube Shorts: izleyip onaylayin -> python main.py --approve %s", video_id)


def process_topic(topic: str, cfg: dict, state: dict) -> None:
    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_dir = OUTPUT / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    log.info("=== Konu: %s | %s ===", topic, batch_dir)

    scripts = script_gen.generate(topic, cfg, batch_dir)   # konu basina N kisa senaryo
    ok = 0
    for i, script in enumerate(scripts, 1):
        video_id = f"{batch_id}_{i:02d}" if len(scripts) > 1 else batch_id
        log.info("--- Video %d/%d: %s ---", i, len(scripts), script["title"])
        try:
            process_part(video_id, topic, script, cfg, state)
            ok += 1
        except Exception:
            log.error("Video %d atlandi:\n%s", i, traceback.format_exc())
    if ok == 0:
        raise RuntimeError("Konudan hicbir video uretilemedi.")

    state["done_topics"].append(topic)
    save_state(state)
    log.info("Konu tamamlandi: %d/%d video hazir.", ok, len(scripts))
    log.info("TikTok/Instagram: her post_kit icindeki video + caption.txt ile paylasin.")


def run(cfg: dict, auto: bool) -> None:
    state = load_state()
    topics = pending_topics(cfg, state)
    if not topics:
        log.info("Islenecek yeni konu yok. topics.txt'e konu ekleyin.")
        return
    batch = topics if auto else topics[:1]
    ok, fail = 0, 0
    for topic in batch:
        try:
            process_topic(topic, cfg, state)
            ok += 1
        except Exception:
            fail += 1
            log.error("Konu atlandi (%s):\n%s", topic, traceback.format_exc())
            if not auto:
                sys.exit(1)
    log.info("Bitti: %d basarili, %d hatali.", ok, fail)


def list_pending() -> None:
    state = load_state()
    if not state["pending_review"]:
        print("Onay bekleyen video yok.")
        return
    for v in state["pending_review"]:
        print(f"[{v['id']}] {v['title']}\n    post_kit: {v['post_kit']}")


def approve(video_id: str, cfg: dict) -> None:
    state = load_state()
    match = [v for v in state["pending_review"] if v["id"] == video_id]
    if not match:
        log.error("Bu id ile onay bekleyen video yok: %s", video_id)
        sys.exit(1)
    v = match[0]
    yt_id = upload.upload_video(v, cfg)
    v["youtube_id"] = yt_id
    state["uploaded"].append(v)
    state["pending_review"] = [p for p in state["pending_review"] if p["id"] != video_id]
    save_state(state)
    log.info("Yuklendi: https://youtu.be/%s", yt_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Dikey video otomasyon pipeline")
    parser.add_argument("--auto", action="store_true", help="Tum bekleyen konulari tek seferde isle")
    parser.add_argument("--topic", metavar="KONU", help="Verilen konudan direkt video uret")
    parser.add_argument("--suggest", metavar="NIS", help="Nis icin ilgi cekici konu onerileri uret")
    parser.add_argument("-n", type=int, default=10, help="--suggest ile kac konu (varsayilan 10)")
    parser.add_argument("--review", action="store_true", help="Onay bekleyenleri listele")
    parser.add_argument("--approve", metavar="ID", help="YouTube'a yukle")
    args = parser.parse_args()

    cfg = load_config()
    if args.suggest:
        topics = script_gen.suggest_topics(args.suggest, args.n, cfg)
        print("\nOnerilen konular:\n" + "\n".join(f"  {i+1}. {t}" for i, t in enumerate(topics)))
        ans = input("\ntopics.txt'e eklensin mi? [e/h] ").strip().lower()
        if ans == "e":
            with open(BASE / cfg["topics_file"], "a", encoding="utf-8") as f:
                f.write("\n" + "\n".join(topics) + "\n")
            print("Eklendi. Baslatmak icin: python main.py --auto")
    elif args.topic:
        state = load_state()
        process_topic(args.topic, cfg, state)
    elif args.review:
        list_pending()
    elif args.approve:
        approve(args.approve, cfg)
    else:
        run(cfg, auto=args.auto)


if __name__ == "__main__":
    main()
