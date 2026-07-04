"""Gorsel uretimi.

Saglayicilar:
  replicate : AI ile ozgun sinematik gorseller (Flux modeli, 9:16). Stok gorunumu yok,
              her video icin senaryoya ozel uretilir. En profesyonel/ozgun sonuc.
  pexels    : lisansli profesyonel stok video (ucretsiz).
  local     : assets/ klasorundeki kendi dosyalarin.
"""
import logging
import os
import time
from pathlib import Path

import requests

log = logging.getLogger("visuals")

REPLICATE_API = "https://api.replicate.com/v1/models/{model}/predictions"


def generate(script: dict, cfg: dict, workdir: Path) -> list[Path]:
    provider = cfg["visuals"]["provider"]
    if provider == "replicate":
        return _replicate(script, cfg, workdir)
    if provider == "pexels":
        from pipeline import stock
        return stock.fetch_clips(script["stock_keywords"], cfg, workdir)
    # local
    assets = Path(__file__).parent.parent / cfg["video"]["assets_dir"]
    clips = sorted(p for p in assets.iterdir()
                   if p.suffix.lower() in {".mp4", ".mov", ".jpg", ".jpeg", ".png"}) if assets.exists() else []
    if not clips:
        raise RuntimeError(f"{assets} bos. Klip/gorsel ekleyin ya da provider degistirin.")
    return clips


def _replicate(script: dict, cfg: dict, workdir: Path) -> list[Path]:
    key = os.environ.get("REPLICATE_API_TOKEN")
    if not key:
        raise RuntimeError("REPLICATE_API_TOKEN tanimli degil (replicate.com -> API tokens). "
                           "Alternatif: config'te visuals.provider: pexels")

    r_cfg = cfg["visuals"]["replicate"]
    model = r_cfg.get("model", "minimax/video-01")
    style = r_cfg.get("style_suffix", "cinematic, dramatic lighting, high detail, no text")
    prompts = script.get("visual_prompts") or script.get("stock_keywords") or [script["title"]]

    img_dir = workdir / "ai_images"
    img_dir.mkdir(exist_ok=True)
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
               "Prefer": "wait"}
    out: list[Path] = []

    for i, prompt in enumerate(prompts[: r_cfg.get("per_video", 6)]):
        full_prompt = f"{prompt}, {style}"
        try:
            resp = requests.post(
                REPLICATE_API.format(model=model),
                headers=headers,
                json={"input": {"prompt": full_prompt, "aspect_ratio": "9:16",
                                "output_format": "jpg", "output_quality": 90}},
                timeout=180,
            )
            resp.raise_for_status()
            pred = resp.json()

            # Prefer:wait cogu zaman yeterli; degilse kisa sure polla
            for _ in range(30):
                if pred.get("status") in ("succeeded", "failed", "canceled"):
                    break
                time.sleep(2)
                pred = requests.get(pred["urls"]["get"],
                                    headers={"Authorization": f"Bearer {key}"}, timeout=30).json()

            if pred.get("status") != "succeeded":
                log.warning("Gorsel uretilemedi (%s): %s", prompt[:40], pred.get("error"))
                continue

            output = pred["output"]
            url = output[0] if isinstance(output, list) else output
            dest = img_dir / f"scene_{i:02d}.jpg"
            with requests.get(url, stream=True, timeout=120) as dl:
                dl.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in dl.iter_content(1 << 20):
                        f.write(chunk)
            out.append(dest)
            log.info("AI gorsel %d/%d hazir: %s", i + 1, len(prompts), prompt[:50])
        except requests.RequestException as e:
            log.warning("Replicate hatasi (%s): %s", prompt[:40], e)

    if not out:
        raise RuntimeError("Hicbir AI gorsel uretilemedi. Token/kredi durumunu kontrol edin.")
    return out
