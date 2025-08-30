from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import List, Dict, Any
import yt_dlp

app = FastAPI()

def make_ydl():
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noprogress": True,
        "extract_flat": False,

        # Evita “video unavailable” / pagine di consenso
        "geo_bypass": True,
        "geo_bypass_country": "US",
        "extractor_args": {
            # usa il client 'android' che funziona bene senza cookie
            "youtube": {"player_client": ["android"]}
        },

        # headers conservativi
        "http_headers": {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "en-US,en;q=0.9",
        },

        # niente download di stream separati (DASH) lato server
        "format": "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio/best",
    }
    return yt_dlp.YoutubeDL(ydl_opts)

def pick_variants(info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Estrae varianti progressive con URL diretto (mp4/webm)."""
    variants = []
    fmts = info.get("formats") or []
    for f in fmts:
        # URL diretto e non frammentato
        if not f.get("url"):
            continue
        if f.get("protocol") in ("m3u8_native", "m3u8", "http_dash_segments", "dash"):
            continue
        ext = (f.get("ext") or "").lower()
        if ext not in ("mp4", "webm"):
            continue
        height = int(f.get("height") or 0)
        abr = int(f.get("abr") or 0)
        vcodec = (f.get("vcodec") or "").lower()
        # etichetta carina
        if height > 0:
            label = f"{ext.upper()} {height}p"
        elif abr > 0:
            label = f"{ext.upper()} {abr}kbps"
        else:
            label = ext.upper()
        variants.append({
            "url": f["url"],
            "label": label,
            "height": height,
            "vcodec": vcodec,
        })

    # ordina per risoluzione discendente, poi MP4 prima di WEBM
    variants.sort(key=lambda x: (x.get("height", 0), 1 if x["url"].lower().endswith(".webm") else 0), reverse=True)
    # dedup per URL
    seen = set(); out = []
    for v in variants:
        if v["url"] in seen: continue
        seen.add(v["url"]); out.append(v)
    return out

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/extract")
def extract(url: str = Query(..., description="URL della pagina video")):
    try:
        with make_ydl() as ydl:
            info = ydl.extract_info(url, download=False)
            # playlist? prendi il primo entry
            if info.get("_type") == "playlist" and info.get("entries"):
                info = info["entries"][0]
            title = info.get("title") or "video"
            variants = pick_variants(info)

        if not variants:
            raise HTTPException(status_code=424, detail="Nessuna variante diretta trovata (spesso il video è solo HLS/DASH o geo/age bloccato).")

        # JSON compatibile con l’app
        return JSONResponse({"title": title, "variants": variants})

    except yt_dlp.utils.DownloadError as e:
        # messaggio più chiaro
        raise HTTPException(status_code=502, detail=f"yt-dlp error: {str(e).splitlines()[-1]}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
