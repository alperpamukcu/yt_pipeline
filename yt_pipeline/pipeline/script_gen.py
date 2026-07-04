"""Senaryo uretimi: Claude API ile kisa dikey video senaryosu + platform metinleri."""
import json
import logging
import os
from pathlib import Path

log = logging.getLogger("script")

PROMPT_TEMPLATE = """TikTok / Instagram Reels / YouTube Shorts icin dikey kisa video senaryosu yaz.

Konu: {topic}
Dil: {language}
Hedef sure: yaklasik {seconds} saniye (saniyede ~2.6 kelime varsay)
Stil: {style}

SADECE su JSON formatinda cevap ver, baska hicbir sey yazma:
{{
  "title": "60 karakteri gecmeyen baslik",
  "narration": "Seslendirilecek tam metin. Sahne yonergesi YOK.",
  "description": "YouTube Shorts aciklamasi, 1-2 paragraf",
  "tags": ["etiket1", "etiket2"],
  "caption": "TikTok/Instagram gonderi metni: 1-2 kisa cumle + 5-8 hashtag",
  "stock_keywords": ["stok arama icin 4-6 INGILIZCE anahtar kelime"],
  "visual_prompts": ["AI gorsel uretimi icin 6 INGILIZCE sinematik sahne tarifi, her biri videonun bir bolumune karsilik gelir, ornek: 'close-up of hands typing on a glowing laptop in a dark room'"]
}}"""

SUGGEST_PROMPT = """Su nis icin TikTok/Reels/Shorts'ta yuksek etkilesim alacak {n} video konusu oner.
Nis: {niche}
Dil: {language}

Kurallar:
- Her konu merak bosluğu yaratmali (izleyici "bunu bilmem lazim" demeli)
- Somut, spesifik, iddiali - jenerik "X hakkinda 5 sey" formatindan kacin
- Guncel ilgiyle baglantili olsun

SADECE su JSON formatinda cevap ver:
{{"topics": ["konu 1", "konu 2", ...]}}"""


def suggest_topics(niche: str, n: int, cfg: dict) -> list[str]:
    """Claude ile ilgi cekici konu fikirleri uret."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY tanimli degil.")
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=cfg["script"]["model"], max_tokens=1500,
        messages=[{"role": "user", "content": SUGGEST_PROMPT.format(
            niche=niche, n=n,
            language="Turkce" if cfg["language"] == "tr" else "English")}],
    )
    raw = "".join(b.text for b in resp.content if b.type == "text")
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(raw)["topics"]


def generate(topic: str, cfg: dict, workdir: Path) -> dict:
    s = cfg["script"]
    script_file = workdir / "script.json"

    if s["provider"] == "manual":
        raise SystemExit(f"Manuel mod: {script_file} dosyasini kendiniz olusturun.")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY ortam degiskeni tanimli degil.")

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    prompt = PROMPT_TEMPLATE.format(
        topic=topic,
        language="Turkce" if cfg["language"] == "tr" else "English",
        seconds=s["target_seconds"],
        style=s["style"],
    )
    log.info("Senaryo uretiliyor (%s)...", s["model"])
    resp = client.messages.create(
        model=s["model"], max_tokens=s["max_tokens"],
        messages=[{"role": "user", "content": prompt}],
    )
    raw = "".join(b.text for b in resp.content if b.type == "text")
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        script = json.loads(raw)
    except json.JSONDecodeError as e:
        (workdir / "script_raw.txt").write_text(raw, encoding="utf-8")
        raise RuntimeError(f"Model JSON dondurmedi, ham cikti script_raw.txt'de: {e}")

    for key in ("title", "narration", "description", "tags", "caption"):
        if key not in script:
            raise RuntimeError(f"Senaryoda eksik alan: {key}")

    script_file.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Senaryo hazir: %d kelime", len(script["narration"].split()))
    log.info(">> Yayindan once script.json'a kendi yorumunuzu ekleyin.")
    return script
