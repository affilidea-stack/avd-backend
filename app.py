import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from yt_dlp import YoutubeDL

app = FastAPI()

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/extract")
def extract(url: str = Query(..., description="URL della pagina video")):
    # Config YDL: niente download, solo info; niente playlist
    ydl_opts = {
        "quiet": True,
        "noplaylist": True,
        "skip_download": True,
        "nocheckcertificate": True,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        # Se il link punta a una playlist, prendo il primo item
        if "entries" in info and info["entries"]:
            info = info["entries"][0]

        title = info.get("title") or "video"
        formats = info.get("formats") or []

        variants = []
        for f in formats:
            # prendiamo solo URL diretti (no HLS/DASH manifest)
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

            variants.append({
                "url":   f["url"],
                "label": label
            })

        # fallback: alcuni video (es. certi YT) hanno solo “best”
        if not variants and info.get("url"):
            variants.append({"url": info["url"], "label": "Best"})

        return JSONResponse({"title": title, "variants": variants})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
