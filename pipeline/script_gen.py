"""Senaryo uretimi: Claude API ile kisa dikey video senaryosu + platform metinleri."""
import json
import logging
import os
from pathlib import Path

log = logging.getLogger("script")

PROMPT_TEMPLATE = """TikTok / Instagram Reels / YouTube Shorts icin ayni konudan {n_videos} adet BAGIMSIZ dikey kisa video senaryosu yaz.

Konu: {topic}
Dil: {language}
Video basina hedef sure: yaklasik {seconds} saniye (saniyede ~2.6 kelime varsay)
Stil: {style}

Kurallar:
- Her video konunun FARKLI bir yonunu/acisini islemeli, icerik tekrar etmemeli.
- Her video tek basina izlenebilir olmali; diger videolara referans verme.
- visual_prompts cok onemli: her prompt, o videonun anlatiminda GECEN somut bir
  sahneyi/nesneyi/olayi gostermeli ve konunun ana ogesini ACIKCA icermeli
  (or. konu Mariana Cukuru ise her promptta okyanus/derinlik ogesi olmali).
  Ozne + eylem + ortam + kamera hareketi tarif et. STIL veya estetik kelimesi
  EKLEME (stil ayrica ekleniyor). Onceki sahneye referans verme.

SADECE su JSON formatinda cevap ver, baska hicbir sey yazma:
{{
  "videos": [
    {{
      "title": "60 karakteri gecmeyen baslik",
      "narration": "Seslendirilecek tam metin. Sahne yonergesi YOK.",
      "description": "YouTube Shorts aciklamasi, 1-2 paragraf",
      "tags": ["etiket1", "etiket2"],
      "caption": "TikTok/Instagram gonderi metni: 1-2 kisa cumle + 5-8 hashtag",
      "stock_keywords": ["stok arama icin 4-6 INGILIZCE anahtar kelime"],
      "visual_prompts": ["{n_scenes} adet INGILIZCE sahne tarifi, yukaridaki kurallara uygun"]
    }}
  ]
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


def generate(topic: str, cfg: dict, out_dir: Path) -> list[dict]:
    """Konudan videos_per_topic adet bagimsiz kisa senaryo uret."""
    s = cfg["script"]

    if s["provider"] == "manual":
        raise SystemExit(f"Manuel mod: {out_dir / 'script.json'} dosyasini kendiniz olusturun.")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY ortam degiskeni tanimli degil.")

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    r_cfg = cfg.get("visuals", {}).get("replicate", {})
    prompt = PROMPT_TEMPLATE.format(
        topic=topic,
        language="Turkce" if cfg["language"] == "tr" else "English",
        seconds=s["target_seconds"],
        style=s["style"],
        n_videos=s.get("videos_per_topic", 1),
        n_scenes=r_cfg.get("per_video", 3),
    )
    log.info("Senaryolar uretiliyor (%s, %d video)...", s["model"], s.get("videos_per_topic", 1))
    resp = client.messages.create(
        model=s["model"], max_tokens=s["max_tokens"],
        messages=[{"role": "user", "content": prompt}],
    )
    raw = "".join(b.text for b in resp.content if b.type == "text")
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        scripts = json.loads(raw)["videos"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        (out_dir / "script_raw.txt").write_text(raw, encoding="utf-8")
        raise RuntimeError(f"Model beklenen JSON'u dondurmedi, ham cikti script_raw.txt'de: {e}")

    for i, script in enumerate(scripts, 1):
        for key in ("title", "narration", "description", "tags", "caption"):
            if key not in script:
                raise RuntimeError(f"Video {i} senaryosunda eksik alan: {key}")

    log.info("Senaryolar hazir: %s", ", ".join(f"{len(v['narration'].split())} kelime" for v in scripts))
    log.info(">> Yayindan once her script.json'a kendi yorumunuzu ekleyin.")
    return scripts
