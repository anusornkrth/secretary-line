import json
from datetime import date, datetime, time, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account
from .config import GOOGLE_SERVICE_ACCOUNT_FILE, GOOGLE_SERVICE_ACCOUNT_JSON, TIMEZONE

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
TZ = ZoneInfo(TIMEZONE)

_session = None
_sa_email = None


class CalendarError(Exception):
    """ข้อความใน exception นี้เขียนไว้ให้ส่งต่อถึงผู้ใช้ได้เลย"""


def _get_session() -> AuthorizedSession:
    global _session, _sa_email
    if _session is None:
        if GOOGLE_SERVICE_ACCOUNT_JSON:
            creds = service_account.Credentials.from_service_account_info(
                json.loads(GOOGLE_SERVICE_ACCOUNT_JSON), scopes=SCOPES)
        elif GOOGLE_SERVICE_ACCOUNT_FILE:
            creds = service_account.Credentials.from_service_account_file(
                GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        else:
            raise CalendarError(
                "ยังไม่ได้ตั้งค่า Google Calendar "
                "(ต้องใส่ GOOGLE_SERVICE_ACCOUNT_FILE ใน .env)")
        _sa_email = creds.service_account_email
        _session = AuthorizedSession(creds)
    return _session


def list_meetings(email: str, day: date) -> list[dict]:
    """คืนรายการนัดของปฏิทิน email ในวันที่ day เรียงตามเวลา: [{"time": "9.00", "title": ...}]"""
    session = _get_session()
    start = datetime.combine(day, time.min, tzinfo=TZ)
    resp = session.get(
        f"https://www.googleapis.com/calendar/v3/calendars/{quote(email, safe='')}/events",
        params={
            "timeMin": start.isoformat(),
            "timeMax": (start + timedelta(days=1)).isoformat(),
            "singleEvents": "true",   # แตกนัดที่เกิดซ้ำออกเป็นรายครั้ง
            "orderBy": "startTime",
            "timeZone": TIMEZONE,
            "maxResults": 50,
        },
        timeout=15,
    )
    if resp.status_code in (403, 404):
        raise CalendarError(
            f"เลขายังเข้าปฏิทินของ {email} ไม่ได้ "
            f"เจ้าของปฏิทินต้องแชร์ปฏิทินให้ {_sa_email} ก่อน")
    resp.raise_for_status()

    meetings = []
    for ev in resp.json().get("items", []):
        if ev.get("status") == "cancelled":
            continue
        start_at = ev["start"].get("dateTime")
        if start_at:
            t = datetime.fromisoformat(start_at).astimezone(TZ)
            when = f"{t.hour}.{t.minute:02d}"
        else:
            when = "ทั้งวัน"
        meetings.append({"time": when, "title": ev.get("summary") or "(ไม่มีชื่อ)"})
    return meetings
