# app.py
import os, re, urllib.parse
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List
import yt_dlp

app = FastAPI()

ALLOWED = set(
    (os.getenv("ALLOWED_DOMAINS") or
     "youtube.com,youtu.be,vimeo.com,dailymotion.com,dai.ly,"
     "instagram.com,facebook.com,fb.watch,tiktok.com,twitter.com,x.com"
    ).split(",")
)

class Variant(BaseModel):
    url: str
    label: str

class ExtractResponse(BaseModel):
    title: str
    variants: List[Variant]

def hostname_ok(url: str) -> bool:
    try:
        host = urllib.parse.urlparse(url).hostname or ""
        host = host.lower()
        return any(host == d or host.endswith("." + d) for d in ALLOWED)
    except:
        return False

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/extract", response_model=ExtractResponse)
def extract(url: str = Query(...)):
    if not hostname_ok(url):
        raise HTTPException(400, "Domain not allowed")
    ydl_opts = {
        "quiet": True,
        "noplaylist": True,
        "skip_download": True,
        "extract_flat": False,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        raise HTTPException(502, f"Extractor error: {e}")

    title = info.get("title") or "video"
    variants = []

    # preferisci formati progressivi MP4 con altezza nota
    fmts = info.get("formats") or []
    for f in fmts:
        vurl = f.get("url")
        if not vurl: continue
        ext = (f.get("ext") or "").lower()
        height = int(f.get("height") or 0)
        # web-compat: usa MP4 progressivo quando possibile
        if ext == "mp4" and height > 0 and not f.get("fragment_base_url"):
            label = f"MP4 {height}p"
            variants.append({"url": vurl, "label": label})

    # fallback: qualche formato valido anche se non MP4
    if not variants:
        for f in fmts:
            vurl = f.get("url")
            if not vurl: continue
            height = int(f.get("height") or 0)
            label = f"{(f.get('ext') or '').upper()} {height}p" if height else (f.get("format_note") or "Video")
            variants.append({"url": vurl, "label": label})
            if len(variants) >= 5: break

    if not variants:
        raise HTTPException(404, "No downloadable variants")

    # dedup per URL e ordina per altezza desc
    seen, dedup = set(), []
    for v in variants:
        if v["url"] in seen: continue
        seen.add(v["url"]); dedup.append(v)
    def h(label): 
        m = re.search(r"(\d{3,4})p", label or "")
        return int(m.group(1)) if m else 0
    dedup.sort(key=lambda v: h(v["label"]), reverse=True)

    return JSONResponse({"title": title, "variants": dedup})
