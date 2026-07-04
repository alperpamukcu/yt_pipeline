"""Profesyonel stok görüntü: Pexels API'den lisanslı dikey video klipler.

Pexels lisansı ticari kullanıma ve sosyal medyada yayina izin verir (atif zorunlu degil).
Ucretsiz API anahtari: https://www.pexels.com/api/
"""
import logging
import os
from pathlib import Path

import requests

log = logging.getLogger("stock")

API = "https://api.pexels.com/videos/search"


def fetch_clips(keywords: list[str], cfg: dict, workdir: Path) -> list[Path]:
    s = cfg["stock"]
    if s["provider"] == "local":
        assets = Path(__file__).parent.parent / cfg["video"]["assets_dir"]
        clips = sorted(p for p in assets.iterdir() if p.suffix.lower() in {".mp4", ".mov", ".jpg", ".png"})
        if not clips:
            raise RuntimeError(f"{assets} klasoru bos. Lisansli klip/gorsel ekleyin.")
        return clips

    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        raise RuntimeError("PEXELS_API_KEY tanimli degil (ucretsiz: pexels.com/api). "
                           "Alternatif: config'te stock.provider: local")

    clip_dir = workdir / "clips"
    clip_dir.mkdir(exist_ok=True)
    headers = {"Authorization": key}
    want = s["per_topic"]
    out: list[Path] = []

    for kw in keywords:
        if len(out) >= want:
            break
        try:
            r = requests.get(API, headers=headers,
                             params={"query": kw, "orientation": s["orientation"],
                                     "size": "medium", "per_page": 3},
                             timeout=30)
            r.raise_for_status()
        except requests.RequestException as e:
            log.warning("Pexels aramasi basarisiz (%s): %s", kw, e)
            continue

        for video in r.json().get("videos", []):
            if len(out) >= want:
                break
            # dikey ve yeterli cozunurlukte en uygun dosyayi sec
            files = [f for f in video["video_files"]
                     if f.get("height", 0) >= 1280 and f.get("height", 0) > f.get("width", 0)]
            if not files:
                continue
            best = min(files, key=lambda f: f["height"])  # gereksiz 4K indirme
            dest = clip_dir / f"pexels_{video['id']}.mp4"
            if dest.exists():
                out.append(dest)
                continue
            try:
                log.info("Klip indiriliyor: %s (%s)", video["id"], kw)
                with requests.get(best["link"], stream=True, timeout=120) as dl:
                    dl.raise_for_status()
                    with open(dest, "wb") as f:
                        for chunk in dl.iter_content(1 << 20):
                            f.write(chunk)
                out.append(dest)
            except requests.RequestException as e:
                log.warning("Indirme hatasi: %s", e)
                dest.unlink(missing_ok=True)

    if not out:
        raise RuntimeError("Hicbir stok klip indirilemedi. Anahtar kelimeleri/API anahtarini kontrol edin.")
    log.info("%d profesyonel dikey klip hazir.", len(out))
    return out
