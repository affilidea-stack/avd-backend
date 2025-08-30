import os
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from yt_dlp import YoutubeDL

app = FastAPI()

def ydl_extract(u: str, extra_opts: dict | None = None):
    opts = {
        "quiet": True,
        "noplaylist": True,
        "skip_download": True,
        "nocheckcertificate": True,
    }
    if extra_opts:
        opts.update(extra_opts)
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(u, download=False)
    # Se è playlist prendo il primo item
    if isinstance(info, dict) and "entries" in info and info["entries"]:
        info = info["entries"][0]
    return info

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/extract")
def extract(url: str = Query(..., description="URL della pagina video")):
    try:
        info = None
        host = (urlparse(url).netloc or "").lower()

        # 1) tentativo standard
        try:
            info = ydl_extract(url)
        except Exception as e1:
            # 2) fallback specifico per vimeo
            if "vimeo.com" in host:
                info = ydl_extract(url, {
                    "http_headers": {"Referer": "https://vimeo.com/"},
                    "extractor_args": {"vimeo": {"player_client": ["ios","android","html5"]}},
                })
            else:
                raise e1

        title = info.get("title") or "video"
        formats = info.get("formats") or []

        variants = []
        for f in formats:
            # Solo URL diretti (niente HLS/DASH manifest)
            if not f.get("url"):
                continue
            proto = (f.get("protocol") or "").lower()
            ext   = (f.get("ext") or "").lower()
            if proto not in ("http", "https"):
                continue
            if ext not in ("mp4", "webm", "m4v", "mov"):
                continue

            height = f.get("height") or 0
            fps    = f.get("fps")
            label  = f"{ext.upper()} {height}p" if height else ext.upper()
            if fps:
                label += f" {fps}fps"

            variants.append({"url": f["url"], "label": label})

        if not variants and info.get("url"):
            variants.append({"url": info["url"], "label": "Best"})

        return JSONResponse({"title": title, "variants": variants})
    except Exception as e:
        # Rendi l’errore visibile per debug
        raise HTTPException(status_code=400, detail=str(e))
