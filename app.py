from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
import yt_dlp
import os
import base64
import tempfile
from urllib.parse import urlparse

app = FastAPI(title="AVD Backend", version="1.0.0")

# ---- CORS per app mobile/web ----
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # restringi se vuoi
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Cookie YouTube opzionali (YT_COOKIES_B64) ----
_COOKIE_PATH: Optional[str] = None
_b64 = os.getenv("YT_COOKIES_B64")
if _b64:
    try:
        raw = base64.b64decode(_b64)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        tmp.write(raw)
        tmp.flush()
        tmp.close()
        _COOKIE_PATH = tmp.name
        print(f"[init] YouTube cookies caricati in {_COOKIE_PATH}")
    except Exception as e:
        print(f"[init] Errore nel decode dei cookie: {e}")
        _COOKIE_PATH = None


def _is_youtube(u: str) -> bool:
    try:
        host = urlparse(u).netloc.lower()
    except Exception:
        return False
    return any(h in host for h in ("youtube.com", "youtu.be", "m.youtube.com"))


def make_ydl(use_cookies: bool = False) -> yt_dlp.YoutubeDL:
    """Costruisce un'istanza YoutubeDL con:
       - client YouTube 'android' (meno blocchi)
       - cookie lato server opzionali
       - niente download, solo metadata
    """
    ydl_opts: Dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noprogress": True,
        "extract_flat": False,
        "noplaylist": True,

        # Bypass pagine consenso/geo se possibile
        "geo_bypass": True,
        "geo_bypass_country": "US",

        # Forza client YouTube 'android' per ridurre sfide anti-bot
        "extractor_args": {
            "youtube": {"player_client": ["android"]},
        },

        # Header conservativi
        "http_headers": {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "en-US,en;q=0.9",
        },

        # Non scaricare stream segmentati lato server
        "format": "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio/best",
    }

    # Aggiungi cookie solo quando richiesto e disponibili
    if use_cookies and _COOKIE_PATH:
        ydl_opts["cookiefile"] = _COOKIE_PATH

    return yt_dlp.YoutubeDL(ydl_opts)


def pick_variants(info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Estrae varianti progressive con URL diretto (mp4/webm)."""
    variants: List[Dict[str, Any]] = []
    fmts = info.get("formats") or []
    for f in fmts:
        url = f.get("url")
        if not url:
            continue

        # Escludi HLS/DASH segmentati
        if f.get("protocol") in ("m3u8_native", "m3u8", "http_dash_segments", "dash"):
            continue

        ext = (f.get("ext") or "").lower()
        if ext not in ("mp4", "webm"):
            continue

        height = int(f.get("height") or 0)
        abr = int(f.get("abr") or 0)
        vcodec = (f.get("vcodec") or "").lower()

        if height > 0:
            label = f"{ext.upper()} {height}p"
        elif abr > 0:
            label = f"{ext.upper()} {abr}kbps"
        else:
            label = ext.upper()

        variants.append({
            "url": url,
            "label": label,
            "height": height,
            "vcodec": vcodec,
        })

    # Ordina: risoluzione desc, MP4 prima di WEBM
    variants.sort(
        key=lambda x: (
            x.get("height", 0),
            1 if x["url"].lower().endswith(".webm") else 0
        ),
        reverse=True
    )

    # Dedup per URL
    seen = set()
    out: List[Dict[str, Any]] = []
    for v in variants:
        if v["url"] in seen:
            continue
        seen.add(v["url"])
        out.append(v)
    return out


@app.get("/")
def root():
    return {"ok": True, "service": "avd-backend", "version": "1.0.0"}


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/extract")
def extract(url: str = Query(..., description="URL della pagina video")):
    """Estrae varianti dirette (progressive) da un URL video.
       Strategia:
       1) Tentativo senza cookie (client Android).
       2) Se YouTube chiede cookie/antibot e i cookie lato server sono presenti,
          retry automatico con cookie.
    """
    def _do_extract(use_cookies: bool = False) -> Dict[str, Any]:
        with make_ydl(use_cookies=use_cookies) as ydl:
            info = ydl.extract_info(url, download=False)
            if info.get("_type") == "playlist" and info.get("entries"):
                info = info["entries"][0]
            return info

    # 1) Primo tentativo senza cookie
    try:
        info = _do_extract(use_cookies=False)
    except yt_dlp.utils.DownloadError as e:
        msg = str(e)
        needs_cookie = _is_youtube(url) and any(
            s in msg.lower()
            for s in (
                "sign in to confirm you’re not a bot",
                "sign in to confirm you're not a bot",
                "consent", "cookies", "account", "please sign in"
            )
        )
        if needs_cookie and _COOKIE_PATH:
            # 2) Retry con cookie lato server
            try:
                info = _do_extract(use_cookies=True)
            except yt_dlp.utils.DownloadError as e2:
                raise HTTPException(
                    status_code=502,
                    detail=f"yt-dlp error (with cookies): {str(e2).splitlines()[-1]}"
                )
        else:
            raise HTTPException(
                status_code=502,
                detail=f"yt-dlp error: {str(e).splitlines()[-1]}"
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    title = info.get("title") or "video"
    variants = pick_variants(info)

    if not variants:
        # Nessuna variante diretta (solo HLS/DASH, geo/age, ecc.)
        raise HTTPException(
            status_code=424,
            detail="Nessuna variante diretta trovata (spesso il video è solo HLS/DASH o è bloccato da restrizioni/consenso)."
        )

    return JSONResponse({"title": title, "variants": variants})
