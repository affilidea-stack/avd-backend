import re
from urllib.parse import urlparse
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from yt_dlp import YoutubeDL

app = FastAPI()

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

def ydl_extract(u: str, extra: dict | None = None):
    opts = {
        "quiet": True,
        "noplaylist": True,
        "skip_download": True,
        "nocheckcertificate": True,
    }
    if extra:
        opts.update(extra)
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(u, download=False)
    if isinstance(info, dict) and "entries" in info and info["entries"]:
        info = info["entries"][0]
    return info

def extract_vimeo_manual(page_url: str):
    # id numerico dalla URL
    m = re.search(r"vimeo\.com/(?:.*?/)?(\d+)", page_url)
    if not m:
        raise ValueError("Vimeo: ID non trovato")
    vid = m.group(1)

    cfg_url = f"https://player.vimeo.com/video/{vid}/config"
    headers = {
        "User-Agent": UA,
        "Accept": "application/json",
        "Referer": f"https://vimeo.com/{vid}",
        "Origin": "https://vimeo.com",
    }
    r = requests.get(cfg_url, headers=headers, timeout=15)
    if r.status_code != 200:
        raise ValueError(f"Vimeo config HTTP {r.status_code}")

    j = r.json()
    title = (j.get("video") or {}).get("title") or "video"
    prog = (
        ((j.get("request") or {}).get("files") or {}).get("progressive")
        or ((j.get("files") or {}).get("progressive"))
        or []
    )
    variants = []
    for f in prog:
        url = f.get("url")
        if not url:
            continue
        q = f.get("quality") or ""
        fps = f.get("fps")
        lbl = f"MP4 {q}"
        if fps:
            lbl += f" {fps}fps"
        variants.append({"url": url, "label": lbl})

    # ordina per qualità
    def to_int(s): 
        import re
        m = re.search(r"(\d{3,4})p", s or "")
        return int(m.group(1)) if m else 0
    variants.sort(key=lambda v: to_int(v["label"]), reverse=True)

    if not variants:
        raise ValueError("Nessuna variante progressive")
    return {"title": title, "variants": variants}

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/extract")
def extract(url: str = Query(..., description="URL della pagina video")):
    host = (urlparse(url).netloc or "").lower()
    try:
        # Vimeo: prima prova manuale, poi fallback a yt-dlp
        if "vimeo.com" in host:
            try:
                return JSONResponse(extract_vimeo_manual(url))
            except Exception:
                info = ydl_extract(url, {
                    "http_headers": {"Referer": "https://vimeo.com/"},
                    "extractor_args": {"vimeo": {"player_client": ["ios","android","html5"]}},
                })
        else:
            info = ydl_extract(url)

        title = info.get("title") or "video"
        formats = info.get("formats") or []
        variants = []
        for f in formats:
            u = f.get("url")
            if not u:
                continue
            proto = (f.get("protocol") or "").lower()
            ext = (f.get("ext") or "").lower()
            if proto not in ("http", "https"):
                continue
            if ext not in ("mp4", "webm", "m4v", "mov"):
                continue
            h = f.get("height") or 0
            fps = f.get("fps")
            label = f"{ext.upper()} {h}p" if h else ext.upper()
            if fps:
                label += f" {fps}fps"
            variants.append({"url": u, "label": label})

        if not variants and info.get("url"):
            variants.append({"url": info["url"], "label": "Best"})

        return JSONResponse({"title": title, "variants": variants})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
