"""Gorsel/video uretimi.

Saglayicilar:
  replicate : AI ile ozgun klipler. Video modeli (Seedance 1 Pro varsayilan,
              prompt sadakati yuksek; Kling da desteklenir) senaryoya ozel
              hareketli sahneler uretir; resim modeli (Flux vb.) secilirse
              montajda Ken Burns efektiyle canlandirilir.
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

# video uretimi dakikalar surebilir, resim saniyeler
POLL_INTERVAL = 5
TIMEOUT_VIDEO = 15 * 60
TIMEOUT_IMAGE = 3 * 60

# Replicate 402/429 bazen GECICI oluyor (ayni istek saniyeler sonra kabul ediliyor)
# -> pes etmeden once bekleyip tekrar dene
RETRY_STATUSES = {402, 429, 500, 502, 503}
RETRY_DELAYS = (20, 45, 90)  # saniye


def _create_prediction(url: str, headers: dict, payload: dict) -> dict:
    """Prediction olustur; gecici hatalarda artan bekleme ile tekrar dene."""
    last_err = None
    for attempt, delay in enumerate((0,) + RETRY_DELAYS):
        if delay:
            log.info("Replicate gecici hata, %d sn bekleyip tekrar (%d. deneme)...",
                     delay, attempt + 1)
            time.sleep(delay)
        resp = requests.post(url, headers=headers, json={"input": payload}, timeout=180)
        if resp.status_code not in RETRY_STATUSES:
            resp.raise_for_status()
            return resp.json()
        last_err = f"{resp.status_code}: {resp.text[:200]}"
    raise requests.HTTPError(f"Replicate {last_err} (tum denemeler tukendi)")


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


def _poll(pred: dict, key: str, timeout: float) -> dict:
    """Prediction tamamlanana kadar bekle (Prefer:wait yetmezse)."""
    deadline = time.monotonic() + timeout
    while pred.get("status") not in ("succeeded", "failed", "canceled"):
        if time.monotonic() > deadline:
            raise TimeoutError(f"Replicate zaman asimi ({timeout:.0f} sn)")
        time.sleep(POLL_INTERVAL)
        pred = requests.get(pred["urls"]["get"],
                            headers={"Authorization": f"Bearer {key}"}, timeout=30).json()
    return pred


def _download(url: str, dest: Path) -> None:
    with requests.get(url, stream=True, timeout=300) as dl:
        dl.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in dl.iter_content(1 << 20):
                f.write(chunk)


def _video_payload(model: str, prompt: str, r_cfg: dict, aspect: str) -> dict:
    """Model ailesine gore dogru API parametrelerini kur (yanlis alan 422 doner)."""
    dur = int(r_cfg.get("clip_seconds", 10))
    if "seedance" in model:
        return {
            "prompt": prompt,
            "duration": 10 if dur >= 8 else 5,     # seedance sadece 5/10 sn destekler
            "resolution": r_cfg.get("resolution", "1080p"),
            "aspect_ratio": aspect,
            "camera_fixed": False,
        }
    # kling ve benzeri modeller icin varsayilan sema
    payload = {
        "prompt": prompt,
        "duration": max(3, min(15, dur)),
        "aspect_ratio": aspect,
        "mode": r_cfg.get("mode", "standard"),
        "generate_audio": bool(r_cfg.get("generate_audio", False)),
    }
    if r_cfg.get("negative_prompt"):
        payload["negative_prompt"] = r_cfg["negative_prompt"]
    return payload


def _replicate(script: dict, cfg: dict, workdir: Path) -> list[Path]:
    key = os.environ.get("REPLICATE_API_TOKEN")
    if not key:
        raise RuntimeError("REPLICATE_API_TOKEN tanimli degil (replicate.com -> API tokens). "
                           "Alternatif: config'te visuals.provider: pexels")

    r_cfg = cfg["visuals"]["replicate"]
    model = r_cfg.get("model", "bytedance/seedance-1-pro")
    is_video = r_cfg.get("type", "video" if "video" in model else "image") == "video"
    style = " ".join(str(r_cfg.get("style_suffix", "")).split())
    prompts = script.get("visual_prompts") or script.get("stock_keywords") or [script["title"]]
    aspect = "9:16" if cfg.get("format") == "vertical" else "16:9"

    out_dir = workdir / ("ai_clips" if is_video else "ai_images")
    out_dir.mkdir(exist_ok=True)
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
               "Prefer": "wait"}
    out: list[Path] = []

    for i, prompt in enumerate(prompts[: r_cfg.get("per_video", 3)]):
        # sahne icerigi one, stil sona: icerik prompt'a hakim kalsin
        full_prompt = f"{prompt}. Style: {style}" if style else prompt
        if is_video:
            payload = _video_payload(model, full_prompt, r_cfg, aspect)
        else:
            payload = {"prompt": full_prompt, "aspect_ratio": aspect,
                       "output_format": "jpg", "output_quality": 90}
            if r_cfg.get("negative_prompt"):
                payload["negative_prompt"] = r_cfg["negative_prompt"]

        try:
            log.info("AI %s %d/%d uretiliyor: %s...", "klip" if is_video else "gorsel",
                     i + 1, min(len(prompts), r_cfg.get("per_video", 3)), prompt[:60])
            pred = _create_prediction(REPLICATE_API.format(model=model), headers, payload)
            pred = _poll(pred, key, TIMEOUT_VIDEO if is_video else TIMEOUT_IMAGE)

            if pred.get("status") != "succeeded":
                log.warning("Uretim basarisiz (%s): %s", prompt[:40], pred.get("error"))
                continue

            output = pred["output"]
            url = output[0] if isinstance(output, list) else output
            dest = out_dir / f"scene_{i:02d}.{'mp4' if is_video else 'jpg'}"
            _download(url, dest)
            out.append(dest)
            log.info("AI %s %d hazir: %s", "klip" if is_video else "gorsel", i + 1, dest.name)
        except (requests.RequestException, TimeoutError) as e:
            log.warning("Replicate hatasi (%s): %s", prompt[:40], e)

    if not out:
        raise RuntimeError("Hicbir AI klip/gorsel uretilemedi. Token/kredi durumunu kontrol edin.")
    return out
