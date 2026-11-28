import json
from typing import Optional
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, Response, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.gemini_service import parse_timetable, generate_setup_guide
from app.ics_service import build_ics, generate_qr_data_uri
from app.storage_service import save_venue, get_venue, get_ics, list_venues

app = FastAPI(title="SilentZone", version="1.1.0")
templates = Jinja2Templates(directory="app/templates")


def _seed_demo_venues():
    if list_venues():
        return
    demos = [
        {
            "venue_id": "masjid-al-noor-blr",
            "name": "Masjid Al-Noor Bengaluru",
            "category": "Place of Worship",
            "ssid": "MasjidSilentZone",
            "events": [
                {"title": "Fajr Jamaat", "start_time": "05:45", "end_time": "06:05", "days": ["MO", "TU", "WE", "TH", "FR", "SA", "SU"], "notes": "Daily"},
                {"title": "Dhuhr Jamaat", "start_time": "13:15", "end_time": "13:35", "days": ["MO", "TU", "WE", "TH", "SA", "SU"], "notes": "Daily"},
                {"title": "Jumuah Khutbah & Prayer", "start_time": "13:15", "end_time": "14:00", "days": ["FR"], "notes": "Fridays"},
                {"title": "Asr Jamaat", "start_time": "16:45", "end_time": "17:05", "days": ["MO", "TU", "WE", "TH", "FR", "SA", "SU"], "notes": "Daily"},
                {"title": "Maghrib Jamaat", "start_time": "18:05", "end_time": "18:25", "days": ["MO", "TU", "WE", "TH", "FR", "SA", "SU"], "notes": "Daily"},
                {"title": "Isha Jamaat", "start_time": "19:45", "end_time": "20:05", "days": ["MO", "TU", "WE", "TH", "FR", "SA", "SU"], "notes": "Daily"},
            ],
        },
        {
            "venue_id": "central-library-blr",
            "name": "Central Engineering Library",
            "category": "Library",
            "ssid": "LibraryQuietZone",
            "events": [
                {"title": "Morning Study Block", "start_time": "09:00", "end_time": "12:30", "days": ["MO", "TU", "WE", "TH", "FR", "SA"], "notes": "Reading Hall"},
                {"title": "Afternoon Focus Hours", "start_time": "14:00", "end_time": "17:30", "days": ["MO", "TU", "WE", "TH", "FR", "SA"], "notes": "Reading Hall"},
            ],
        },
    ]
    for d in demos:
        ics = build_ics(d["name"], d["ssid"], d["events"])
        save_venue(d, ics)


@app.on_event("startup")
async def startup_event():
    _seed_demo_venues()


def _external_base_url(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}".rstrip("/")


def _detect_device(ua: str) -> dict:
    u = (ua or "").lower()
    if "iphone" in u or "ipad" in u:
        return {
            "id": "ios",
            "label": "iPhone / iPad (iOS Focus & Shortcuts)",
            "trigger": "iOS Focus Automation + Silent Notification Trigger",
            "steps_hint": "Shortcuts -> Automation -> Wi-Fi Joins -> Turn Focus (Do Not Disturb) On",
        }
    if "samsung" in u or "sm-" in u:
        return {
            "id": "samsung",
            "label": "Samsung Galaxy (Modes & Routines)",
            "trigger": "Samsung Modes & Routines -> Auto-DND",
            "steps_hint": "Settings -> Modes & Routines -> If Wi-Fi + Calendar Active -> Do Not Disturb",
        }
    if "pixel" in u:
        return {
            "id": "pixel",
            "label": "Google Pixel (Android Rules)",
            "trigger": "Pixel System Rules -> Do Not Disturb",
            "steps_hint": "Settings -> System -> Rules -> Add Wi-Fi Network -> Turn on Do Not Disturb",
        }
    if "xiaomi" in u or "redmi" in u or "poco" in u or "oneplus" in u or "android" in u:
        return {
            "id": "android",
            "label": "Android (Modes / MacroDroid Silent Trigger)",
            "trigger": "Android Wi-Fi + Calendar Silent Mode Trigger",
            "steps_hint": "MacroDroid / Modes -> Trigger: Wi-Fi Connected + Calendar Busy -> Ringer Silent/DND",
        }
    return {
        "id": "desktop",
        "label": "Desktop Browser (Scan QR on Phone)",
        "trigger": "Auto-detects Samsung, Pixel, Android & iOS on scan",
        "steps_hint": "Scan the QR code with your phone camera to get OS-specific silent triggers",
    }


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    _seed_demo_venues()
    venues = list_venues()[:6]
    return templates.TemplateResponse(
        request=request, name="index.html", context={"venues": venues}
    )


@app.get("/admin", response_class=HTMLResponse)
async def admin_portal(request: Request):
    _seed_demo_venues()
    venues = list_venues()
    return templates.TemplateResponse(
        request=request, name="admin.html", context={"venues": venues}
    )


@app.post("/api/parse-timetable")
async def api_parse_timetable(
    raw_text: Optional[str] = Form(default=""),
    file: Optional[UploadFile] = File(default=None),
):
    image_bytes = None
    mime_type = None
    if file and file.filename:
        image_bytes = await file.read()
        if len(image_bytes) > 0:
            mime_type = file.content_type or "image/jpeg"
        else:
            image_bytes = None

    if not image_bytes and not (raw_text and raw_text.strip()):
        raise HTTPException(status_code=400, detail="Upload a timetable image or enter text.")

    try:
        result = parse_timetable(image_bytes=image_bytes, mime_type=mime_type, raw_text=raw_text)
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post("/api/venues")
async def api_create_venue(
    name: str = Form(...),
    category: str = Form(...),
    ssid: str = Form(...),
    events_json: str = Form(...),
):
    try:
        events = json.loads(events_json)
        if not isinstance(events, list) or len(events) == 0:
            raise ValueError("At least one quiet window is required.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid schedule JSON: {e}")

    ics_content = build_ics(venue_name=name, ssid=ssid, events=events)
    saved = save_venue(
        {"name": name.strip(), "category": category.strip(), "ssid": ssid.strip(), "events": events},
        ics_content,
    )
    return RedirectResponse(url=f"/v/{saved['venue_id']}", status_code=303)


@app.get("/v/{venue_id}", response_class=HTMLResponse)
async def venue_page(request: Request, venue_id: str):
    _seed_demo_venues()
    venue = get_venue(venue_id)
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    base_url = _external_base_url(request)
    venue_url = f"{base_url}/v/{venue_id}"
    ics_url = f"{base_url}/v/{venue_id}/calendar.ics"
    webcal_url = ics_url.replace("https://", "webcal://").replace("http://", "webcal://")
    qr_uri = generate_qr_data_uri(venue_url)
    device_info = _detect_device(request.headers.get("user-agent", ""))
    return templates.TemplateResponse(
        request=request,
        name="venue.html",
        context={
            "venue": venue,
            "venue_url": venue_url,
            "ics_url": ics_url,
            "webcal_url": webcal_url,
            "qr_uri": qr_uri,
            "device_info": device_info,
        },
    )


@app.get("/v/{venue_id}/poster", response_class=HTMLResponse)
async def venue_poster(request: Request, venue_id: str):
    _seed_demo_venues()
    venue = get_venue(venue_id)
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    base_url = _external_base_url(request)
    venue_url = f"{base_url}/v/{venue_id}"
    qr_uri = generate_qr_data_uri(venue_url)
    return templates.TemplateResponse(
        request=request,
        name="poster.html",
        context={"venue": venue, "venue_url": venue_url, "qr_uri": qr_uri},
    )


@app.get("/v/{venue_id}/calendar.ics")
async def venue_ics(venue_id: str):
    _seed_demo_venues()
    ics_content = get_ics(venue_id)
    if not ics_content:
        raise HTTPException(status_code=404, detail="Calendar feed not found")
    return Response(
        content=ics_content,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{venue_id}.ics"',
            "Cache-Control": "no-cache",
        },
    )


@app.post("/api/setup-guide")
async def api_setup_guide(
    device_os: str = Form(...),
    language: str = Form(...),
    venue_name: str = Form(...),
    ssid: str = Form(...),
):
    try:
        guide = generate_setup_guide(device_os, language, venue_name, ssid)
        return JSONResponse(guide)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/health")
async def health():
    import os
    return {"status": "ok", "service": "SilentZone", "gemini_configured": bool(os.getenv("GEMINI_API_KEY", "").strip())}


@app.get("/robots.txt")
async def robots():
    return Response("User-agent: *
Allow: /
Sitemap: https://silentzone.onrender.com/sitemap.xml
", media_type="text/plain")


@app.get("/sitemap.xml")
async def sitemap():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://silentzone.onrender.com/</loc></url>
  <url><loc>https://silentzone.onrender.com/admin</loc></url>
  <url><loc>https://silentzone.onrender.com/v/masjid-al-noor-blr</loc></url>
  <url><loc>https://silentzone.onrender.com/v/central-library-blr</loc></url>
</urlset>"""
    return Response(xml, media_type="application/xml")


@app.get("/manifest.json")
async def manifest():
    return JSONResponse({
        "name": "SilentZone Labs",
        "short_name": "SilentZone",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0C0D0F",
        "theme_color": "#C46D3B",
    })
