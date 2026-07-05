# yt_pipeline

Dikey kisa video (TikTok / Reels / Shorts) otomasyon pipeline'i.
Akis: konu -> Claude ile N kisa senaryo -> ElevenLabs TTS -> AI video klipleri (Replicate)
-> ffmpeg montaj + senkron altyazi -> kapak -> post kit -> [insan onayi] -> YouTube upload.

## Komutlar

```
python main.py --auto            # topics.txt'teki tum konulari isle
python main.py                   # sadece siradaki konuyu isle
python main.py --topic "KONU"    # tek konudan direkt uret
python main.py --suggest "NIS"   # konu onerileri uret (-n ile adet)
python main.py --review          # onay bekleyenleri listele
python main.py --approve <id>    # YouTube Shorts olarak yukle
```

Test/derleme adimi yok; hizli kontrol: `python -m py_compile main.py pipeline/*.py`

## Gerekli ortam degiskenleri / araclar

- `ANTHROPIC_API_KEY` — senaryo uretimi (pipeline/script_gen.py)
- `ELEVENLABS_API_KEY` — seslendirme (pipeline/tts.py; yedek: edge-tts, ucretsiz)
- `REPLICATE_API_TOKEN` — AI video/gorsel (pipeline/visuals.py; yedek: pexels icin `PEXELS_API_KEY`)
- `ffmpeg` + `ffprobe` PATH'te olmali (montaj ve sure olcumu)
- YouTube upload: `client_secret.json` (OAuth), ilk calistirmada `token.json` uretilir

## Mimari

- `main.py` — orkestrasyon + durum (`output/state.json`). Bir konu = N bagimsiz kisa video
  (`script.videos_per_topic`). Her video `output/<batch>_<nn>/` altinda uretilir;
  bir video hata verse digerleri devam eder.
- `pipeline/script_gen.py` — Claude tek cagrida `{"videos":[...]}` dondurur (konu basina N senaryo).
  `visual_prompts` kurali: her prompt anlatimdaki somut bir sahneyi gostermeli ve konunun ana
  ogesini icermeli; stil kelimesi ICERMEZ (stil visuals.py'de sona eklenir).
- `pipeline/tts.py` — ElevenLabs `with-timestamps` endpoint'i; ses + `words.json`
  (kelime zamanlamalari) uretir. `eleven_multilingual_v2` zorunlu cunku senkron altyazi
  karakter zamanlamalarina dayanir (eleven_v3 timestamps desteklemiyor).
- `pipeline/captions.py` — `words.json` -> `captions.ass` (kelime kelime karaoke altyazi).
- `pipeline/visuals.py` — Replicate ile klip uretimi. Model ailesine gore payload kurulur
  (`_video_payload`): seedance (duration 5/10, resolution) vs kling (mode, generate_audio,
  negative_prompt). Yeni model eklerken buraya sema dali ekle — yanlis alan 422 doner.
- `pipeline/assemble.py` — ffmpeg: klipleri normalize et, ses suresine esit bol, altyazi bind et.
  Windows'ta altyazi yolu sorunlari nedeniyle ffmpeg workdir icinde goreli adla calistirilir.
- `pipeline/thumbnail.py`, `pipeline/upload.py` — kapak ve YouTube upload.

## Onemli kararlar / tuzaklar

- **Video sayisi/suresi**: kisa (~30 sn) ve konu basina 3 video tercih edildi — tek uzun
  videodan daha iyi performans. Ayar: `config.yaml -> script.target_seconds / videos_per_topic`.
  Toplam klip suresi ~= video suresi olacak sekilde `visuals.replicate.per_video x clip_seconds`
  ayarla (3 x 10 sn = 30 sn).
- **Konudan kopan gorseller**: iki nedeni vardi — (1) agir stil metni (Wes Anderson) sahne
  icerigini eziyordu, (2) stil hem senaryo prompt'una hem visuals.py'ye ekleniyordu (cift).
  Cozum: stil SADECE visuals.py'de prompt sonuna eklenir, `style_suffix` kisa/notr tutulur,
  senaryo prompt'u her sahnede konunun ana ogesini zorunlu kilar. Stili tekrar agirlastirma.
- **Ses**: eski voice_id (Antoni) Ingilizce bir sesti, Turkce'de robotik cikiyordu. En iyi
  sonuc icin ElevenLabs Voice Library'den anadili Turkce bir ses secilip ID config'e yazilmali.
  Dogallik ayarlari: stability dusuk (0.35), style yuksek (0.45), speaker_boost acik.
- `output/state.json` islenen konulari tutar; bir konuyu yeniden islemek icin
  `done_topics`'ten silin.
- Kod tabani ASCII/Turkce-karaktersiz yorum kullanir (or. "uretim", "sure") — mevcut stile uy.
