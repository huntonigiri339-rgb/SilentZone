import json
from typing import Optional
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, Response, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.gemini_service import parse_timetable, generate_setup_guide
from app.ics_service import build_ics, generate_qr_data_uri
from app.storage_service import save_venue, get_venue, get_ics, list_venues

app = FastAPI(title="SilentZone", version="1.0.0")
templates = Jinja2Templates(directory="app/templates")


def _detect_device(ua: str) -> str:
    u = (ua or "").lower()
    if "iphone" in u or "ipad" in u:
        return "iPhone (iOS Focus & Shortcuts)"
    if "samsung" in u or "sm-" in u:
        return "Samsung Galaxy (Modes & Routines)"
    if "pixel" in u:
        return "Google Pixel (Android Rules)"
    if "xiaomi" in u or "redmi" in u or "poco" in u:
        return "Xiaomi / Redmi (Android + MacroDroid)"
    if "android" in u:
        return "Android (Modes & Routines / MacroDroid)"
    return "Android or iPhone"


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    venues = list_venues()[:6]
    return templates.TemplateResponse(
        request=request, name="index.html", context={"venues": venues}
    )


@app.get("/admin", response_class=HTMLResponse)
async def admin_portal(request: Request):
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
        mime_type = file.content_type or "image/jpeg"

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
    venue = get_venue(venue_id)
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    base_url = str(request.base_url).rstrip("/")
    venue_url = f"{base_url}/v/{venue_id}"
    ics_url = f"{base_url}/v/{venue_id}/calendar.ics"
    qr_uri = generate_qr_data_uri(venue_url)
    detected_device = _detect_device(request.headers.get("user-agent", ""))
    return templates.TemplateResponse(
        request=request,
        name="venue.html",
        context={
            "venue": venue,
            "venue_url": venue_url,
            "ics_url": ics_url,
            "qr_uri": qr_uri,
            "detected_device": detected_device,
        },
    )


@app.get("/v/{venue_id}/poster", response_class=HTMLResponse)
async def venue_poster(request: Request, venue_id: str):
    venue = get_venue(venue_id)
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    base_url = str(request.base_url).rstrip("/")
    venue_url = f"{base_url}/v/{venue_id}"
    qr_uri = generate_qr_data_uri(venue_url)
    return templates.TemplateResponse(
        request=request,
        name="poster.html",
        context={"venue": venue, "venue_url": venue_url, "qr_uri": qr_uri},
    )


@app.get("/v/{venue_id}/calendar.ics")
async def venue_ics(venue_id: str):
    ics_content = get_ics(venue_id)
    if not ics_content:
        raise HTTPException(status_code=404, detail="Calendar feed not found")
    return Response(
        content=ics_content,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'inline; filename="{venue_id}.ics"'},
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
    return {"status": "ok", "service": "SilentZone"}
