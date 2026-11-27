import io
import base64
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from icalendar import Calendar, Event
import qrcode


def build_ics(venue_name: str, ssid: str, events: list, tz_name: str = "Asia/Kolkata") -> str:
    cal = Calendar()
    cal.add("prodid", "-//SilentZone Labs//SilentZone Schedule//EN")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", f"{venue_name} — SilentZone")
    cal.add("x-wr-timezone", tz_name)

    tz = ZoneInfo(tz_name)
    today = datetime.now(tz).date()

    for idx, ev in enumerate(events):
        try:
            sh, sm = map(int, ev["start_time"].split(":"))
            eh, em = map(int, ev["end_time"].split(":"))
        except Exception:
            continue

        dt_start = datetime(today.year, today.month, today.day, sh, sm, tzinfo=tz)
        dt_end = datetime(today.year, today.month, today.day, eh, em, tzinfo=tz)
        if dt_end <= dt_start:
            dt_end = dt_start + timedelta(minutes=20)

        ical_ev = Event()
        ical_ev.add("uid", f"silentzone-{idx}-{sh}{sm}@silentzone.app")
        ical_ev.add("summary", f"SilentZone: {ev.get('title', 'Quiet Window')}")
        ical_ev.add("dtstart", dt_start)
        ical_ev.add("dtend", dt_end)
        ical_ev.add("location", f"Wi-Fi SSID: {ssid}")
        ical_ev.add("description", ev.get("notes") or f"Auto-silence active inside {venue_name} ({ssid}).")

        days = ev.get("days") or ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
        ical_ev.add("rrule", {"freq": "weekly", "byday": days})
        cal.add_component(ical_ev)

    return cal.to_ical().decode("utf-8")


def generate_qr_data_uri(url: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#101D33", back_color="#FFFFFF")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"
