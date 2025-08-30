from fastapi import FastAPI, HTTPException, Query
import yt_dlp

app = FastAPI()

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/extract")
def extract(url: str = Query(..., min_length=6)):
    ydl_opts = {
        "quiet": True,
        "noplaylist": True,
        "skip_download": True,
        "extract_flat": False,
        "geo_bypass": True,
        "nocheckcertificate": True,
        "http_headers": {"User-Agent": "Mozilla/5.0"},
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    title = info.get("title") or "video"
    formats = info.get("formats") or []

    variants = []
    seen = set()
    for f in formats:
        # scarta audio-only o video-only
        if (f.get("vcodec") in (None, "none")) or (f.get("acodec") in (None, "none")):
            continue
        # scarta manifest (m3u8/dash) perché non è un file diretto
        proto = (f.get("protocol") or "")
        if "m3u8" in proto or "dash" in proto:
            continue

        u = f.get("url")
        if not u or u in seen:
            continue
        seen.add(u)

        ext = (f.get("ext") or "mp4").upper()
        h = f.get("height") or 0
        label = f"{ext} {h}p" if h else ext
        variants.append({"url": u, "label": label})

    return {"title": title, "variants": variants}
