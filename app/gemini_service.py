import os
import json
import time
from typing import List, Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from google.genai.errors import ServerError, APIError

load_dotenv()

PRIMARY_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
FALLBACK_MODELS = [PRIMARY_MODEL, "gemini-3.5-flash-lite"]


class QuietEvent(BaseModel):
    title: str = Field(description="Name of prayer, lecture, or quiet window")
    start_time: str = Field(description="24-hour start time in HH:MM format, e.g., 13:15")
    end_time: str = Field(description="24-hour end time in HH:MM format, e.g., 13:45")
    days: List[str] = Field(
        description="Two-letter iCal weekday codes: MO, TU, WE, TH, FR, SA, SU"
    )
    notes: str = Field(description="Brief note or empty string")


class ScheduleResponse(BaseModel):
    venue_suggestion: str = Field(description="Detected venue name or empty string")
    events: List[QuietEvent]


class SetupGuideResponse(BaseModel):
    device_label: str
    headline: str
    steps: List[str]
    emergency_tip: str


def _get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set in environment.")
    return genai.Client(api_key=api_key)


def _generate_with_retry(contents, schema, temperature=0.1) -> dict:
    client = _get_client()
    last_err = None
    for model_name in FALLBACK_MODELS:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=schema,
                        temperature=temperature,
                    ),
                )
                return json.loads(response.text)
            except ServerError as e:
                last_err = e
                time.sleep(1.5 * (attempt + 1))
            except APIError as e:
                last_err = e
                break  # model not found -> try next fallback
    raise RuntimeError(f"Gemini temporarily unavailable: {last_err}")


def parse_timetable(
    image_bytes: Optional[bytes] = None,
    mime_type: Optional[str] = None,
    raw_text: Optional[str] = None,
) -> dict:
    prompt = (
        "You are SilentZone's schedule extraction engine. Extract every quiet-hour, prayer, "
        "class, or clinic window from the provided timetable into strict JSON. "
        "Convert all times to 24-hour HH:MM format. If only a start time is shown (like a prayer Jamaat time), "
        "set end_time to 20 minutes after start_time. Use two-letter weekday codes (MO, TU, WE, TH, FR, SA, SU) "
        "and include all 7 days if it repeats daily."
    )
    contents = [prompt]
    if raw_text and raw_text.strip():
        contents.append(f"Timetable text:\n{raw_text.strip()}")
    if image_bytes and mime_type:
        contents.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))

    return _generate_with_retry(contents, ScheduleResponse, temperature=0.1)


def generate_setup_guide(
    device_os: str, language: str, venue_name: str, ssid: str
) -> dict:
    prompt = (
        f"Generate a clear, beginner-friendly 3-step phone automation guide in {language} "
        f"for a visitor using {device_os} at '{venue_name}'. "
        f"Goal: automatically enable Do Not Disturb ONLY when connected to Wi-Fi '{ssid}' "
        f"and an event from the subscribed '{venue_name} SilentZone' calendar is active, "
        f"and restore normal ringer on exit. "
        f"Also provide a 1-sentence emergency_tip in {language} explaining how to allow Repeat Callers or Starred Contacts."
    )
    return _generate_with_retry(prompt, SetupGuideResponse, temperature=0.2)
