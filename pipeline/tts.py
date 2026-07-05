"""Seslendirme.

Saglayicilar:
  elevenlabs : gercek insan sesine en yakin TTS (endustri standardi, Turkce destekli).
               Kelime zamanlamalarini API'den alir -> senkron altyazi.
  edge       : ucretsiz yedek (Microsoft neural). Kelime zamanlamasi WordBoundary'den.

Her iki yol da workdir/words.json uretir: [{"word","start","end"}] (saniye).
"""
import asyncio
import json
import logging
import os
from pathlib import Path

log = logging.getLogger("tts")


def synthesize(text: str, cfg: dict, workdir: Path) -> Path:
    provider = cfg["tts"].get("provider", "edge")
    if provider == "elevenlabs":
        return _elevenlabs(text, cfg, workdir)
    return _edge(text, cfg, workdir)


# --------------------------- ElevenLabs ---------------------------

def _elevenlabs(text: str, cfg: dict, workdir: Path) -> Path:
    import base64
    import requests

    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY tanimli degil (elevenlabs.io -> Profile -> API key). "
                           "Gecici cozum: config'te tts.provider: edge")

    e = cfg["tts"]["elevenlabs"]
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{e['voice_id']}/with-timestamps"
    r = requests.post(
        url,
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        json={
            "text": text,
            "model_id": e.get("model_id", "eleven_multilingual_v2"),
            "voice_settings": {
                "stability": e.get("stability", 0.35),
                "similarity_boost": e.get("similarity_boost", 0.75),
                "style": e.get("style", 0.45),
                "use_speaker_boost": bool(e.get("use_speaker_boost", True)),
            },
        },
        timeout=300,
    )
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs hatasi {r.status_code}: {r.text[:500]}")
    data = r.json()

    out = workdir / "narration.mp3"
    out.write_bytes(base64.b64decode(data["audio_base64"]))

    # karakter zamanlamalarini kelimelere donustur
    al = data["alignment"]
    chars, starts, ends = al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]
    words, cur, w_start = [], "", None
    for ch, s, en in zip(chars, starts, ends):
        if ch.strip():
            if w_start is None:
                w_start = s
            cur += ch
            w_end = en
        elif cur:
            words.append({"word": cur, "start": w_start, "end": w_end})
            cur, w_start = "", None
    if cur:
        words.append({"word": cur, "start": w_start, "end": w_end})

    (workdir / "words.json").write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
    log.info("ElevenLabs ses hazir: %s (%d kelime zamanlamasi)", out, len(words))
    return out


# --------------------------- edge-tts (yedek) ---------------------------

def _edge(text: str, cfg: dict, workdir: Path) -> Path:
    import edge_tts

    voice = cfg["tts"]["voice_tr"] if cfg["language"] == "tr" else cfg["tts"]["voice_en"]
    out = workdir / "narration.mp3"
    words = []

    async def _run():
        communicate = edge_tts.Communicate(text, voice, rate=cfg["tts"].get("rate", "+0%"))
        with open(out, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    start = chunk["offset"] / 1e7
                    words.append({"word": chunk["text"],
                                  "start": start,
                                  "end": start + chunk["duration"] / 1e7})

    log.info("edge-tts seslendirme (%s)...", voice)
    asyncio.run(_run())
    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError("TTS ciktisi bos. Internet baglantisini kontrol edin.")
    (workdir / "words.json").write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
    log.info("Ses hazir: %s (%d kelime)", out, len(words))
    return out
