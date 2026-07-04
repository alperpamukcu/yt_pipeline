"""YouTube Data API v3 ile yukleme (OAuth2, kaldigi yerden devam edebilen upload + retry)."""
import logging
import time
from pathlib import Path

log = logging.getLogger("upload")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
BASE = Path(__file__).parent.parent

AI_DISCLOSURE_TR = "\n\n---\nBu videonun senaryo taslagi ve seslendirmesinde yapay zeka araclarindan yararlanilmis, icerik insan denetiminden gecirilmistir."


def _get_service(cfg: dict):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    y = cfg["youtube"]
    token_file = BASE / y["token_file"]
    secrets = BASE / y["client_secrets"]

    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not secrets.exists():
                raise RuntimeError(
                    f"{secrets} bulunamadi. Google Cloud Console'da YouTube Data API v3'u acin, "
                    "OAuth client (Desktop) olusturun ve JSON'u bu isimle kaydedin."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
            creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds)


def upload_video(item: dict, cfg: dict) -> str:
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    y = cfg["youtube"]
    yt = _get_service(cfg)

    description = item["description"]
    if y.get("ai_disclosure"):
        description += AI_DISCLOSURE_TR

    body = {
        "snippet": {
            "title": item["title"][:100],
            "description": description[:5000],
            "tags": item["tags"][:30],
            "categoryId": y["category_id"],
        },
        "status": {
            "privacyStatus": y["privacy"],
            "selfDeclaredMadeForKids": y["made_for_kids"],
        },
    }

    media = MediaFileUpload(item["video"], chunksize=8 * 1024 * 1024, resumable=True)
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)

    log.info("Yukleniyor: %s", item["title"])
    response = None
    retries = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                log.info("  %%%d", int(status.progress() * 100))
            retries = 0
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and retries < 5:
                retries += 1
                wait = 2 ** retries
                log.warning("Gecici hata (%s), %d sn sonra tekrar...", e.resp.status, wait)
                time.sleep(wait)
            else:
                raise

    video_id = response["id"]

    # thumbnail (kanalda thumbnail izni acik olmali - yeni kanallarda telefon dogrulamasi gerekir)
    try:
        yt.thumbnails().set(videoId=video_id, media_body=item["thumbnail"]).execute()
    except Exception as e:
        log.warning("Thumbnail yuklenemedi (video yuklendi): %s", e)

    return video_id
