import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from google import genai
from google.genai import types
from . import calendar_client, db
from .config import GEMINI_API_KEY, GEMINI_MODEL, TIMEZONE

# Gemini ตอบ 503 เป็นช่วง ๆ เมื่อคนใช้เยอะ → ให้ SDK ลองใหม่เอง
client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(
        attempts=4,
        http_status_codes=[500, 502, 503, 504],  # ไม่ลองซ้ำเมื่อ 429 (โควตาหมด ลองอีกก็ไม่ผ่าน)
    )),
)

_TOOL_DEFS = [
    {
        "name": "add_task",
        "description": "บันทึกงานใหม่ลงรายการ To-do ของห้องแชทนี้",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "ชื่องาน"},
                "owner": {"type": "string", "description": "ผู้รับผิดชอบ (ถ้ามี)"},
                "due_date": {"type": "string", "description": "กำหนดส่ง YYYY-MM-DD (ถ้ามี)"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "list_tasks",
        "description": "ดูรายการงานของห้องแชทนี้",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["todo", "done", "all"]},
            },
        },
    },
    {
        "name": "complete_task",
        "description": "ทำเครื่องหมายว่างานเสร็จแล้ว ด้วยหมายเลข id ของงาน",
        "parameters": {
            "type": "object",
            "properties": {"task_id": {"type": "integer"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "summarize_chat",
        "description": "สรุปบทสนทนาของห้องนี้ในวันนี้ (ประเด็นหลัก ข้อตกลง งานที่ต้องทำ)",
    },
    {
        "name": "list_meetings",
        "description": (
            "ดูรายการประชุมจาก Google Calendar ของอีเมลที่ระบุ "
            "ใช้เมื่อผู้ใช้ส่งอีเมลมา หรือถามว่าใครมีประชุมอะไร ดูได้ทั้งวันเดียวหรือเป็นช่วง (สูงสุด 62 วัน) "
            "ผลลัพธ์จัดรูปแบบพร้อมส่งให้ผู้ใช้แล้ว"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "อีเมลเจ้าของปฏิทิน"},
                "date": {"type": "string", "description": "วันที่ YYYY-MM-DD หรือวันแรกของช่วง (ไม่ระบุ = วันนี้)"},
                "end_date": {
                    "type": "string",
                    "description": "วันสุดท้ายของช่วง YYYY-MM-DD ใช้เมื่อถามหลายวัน เช่น ทั้งสัปดาห์ ทั้งเดือน (ไม่ระบุ = วันเดียว)",
                },
            },
            "required": ["email"],
        },
    },
    {
        "name": "subscribe_daily_summary",
        "description": "สมัครรับสรุปรายวันอัตโนมัติทุกเย็นสำหรับห้องนี้",
    },
]

TOOLS = [types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name=t["name"],
        description=t["description"],
        parameters_json_schema=t.get("parameters"),
    )
    for t in _TOOL_DEFS
])]


def summarize_today(chat_id: str) -> str:
    msgs = db.get_messages_today(chat_id)
    if not msgs:
        return "วันนี้ยังไม่มีข้อความในห้องนี้"
    transcript = "\n".join(
        f"[{m['created_at'][11:16]}] {m['user_id'][-4:] if m['user_id'] else '?'}: {m['text']}"
        for m in msgs
    )
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=f"สรุปแชทวันนี้:\n\n{transcript}",
        config=types.GenerateContentConfig(
            system_instruction=(
                "คุณคือเลขาที่สรุปการประชุม/แชทเป็นภาษาไทย กระชับ อ่านง่ายบนมือถือ "
                "รูปแบบ: 📌 ประเด็นหลัก / ✅ ข้อตกลง / 📝 งานที่ต้องทำ (ใคร-อะไร-เมื่อไร) / ❓ เรื่องค้าง"
            ),
        ),
    )
    return (resp.text or "").strip() or "ขออภัย สรุปแชทไม่สำเร็จ ลองใหม่อีกครั้งนะคะ"


THAI_DAYS = ["จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา."]
THAI_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
               "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
MAX_RANGE_DAYS = 62


def _thai_date(d: date) -> str:
    return f"{THAI_DAYS[d.weekday()]} {d.day} {THAI_MONTHS[d.month - 1]}"


def month_range(today: date | None = None) -> tuple[str, str]:
    """วันแรกและวันสุดท้ายของเดือนปัจจุบัน (YYYY-MM-DD)"""
    today = today or datetime.now(ZoneInfo(TIMEZONE)).date()
    first = today.replace(day=1)
    last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return first.isoformat(), last.isoformat()


def _meeting_line(m: dict) -> str:
    title = m["title"] if m["title"].startswith("ประชุม") else f"ประชุม {m['title']}"
    return f"{m['time']} {title}"


def meetings_text(email: str, day_str: str | None = None, end_str: str | None = None) -> str:
    today = datetime.now(ZoneInfo(TIMEZONE)).date()
    first = date.fromisoformat(day_str) if day_str else today
    last = date.fromisoformat(end_str) if end_str else first
    if last < first:
        first, last = last, first
    if (last - first).days >= MAX_RANGE_DAYS:
        return f"ขอดูได้ครั้งละไม่เกิน {MAX_RANGE_DAYS} วันนะคะ"
    try:
        meetings = calendar_client.list_meetings(email, first, last)
    except calendar_client.CalendarError as e:
        return str(e)

    # วันเดียว: รูปแบบเดิม
    if first == last:
        label = "วันนี้" if first == today else f"วันที่ {first.isoformat()} "
        if not meetings:
            return f"คุณ {email}\n{label}ไม่มีประชุม"
        lines = [f"คุณ {email}", "มีประชุมดังนี้" if first == today else f"มีประชุม{label}ดังนี้"]
        return "\n".join(lines + [_meeting_line(m) for m in meetings])

    # หลายวัน: จัดกลุ่มตามวัน แสดงเฉพาะวันที่มีประชุม
    span = f"{_thai_date(first)} – {_thai_date(last)} {last.year}"
    if not meetings:
        return f"คุณ {email}\nช่วง {span} ไม่มีประชุม"
    lines = [f"คุณ {email}", f"ตารางประชุม {span} ({len(meetings)} รายการ)"]
    current = None
    for m in meetings:
        if m["date"] != current:
            current = m["date"]
            lines.append(f"\n📅 {_thai_date(current)}" + (" (วันนี้)" if current == today else ""))
        lines.append(_meeting_line(m))
    return "\n".join(lines)


def execute_tool(name: str, args: dict, chat_id: str) -> str:
    try:
        if name == "add_task":
            t = db.add_task(chat_id, args["title"], args.get("owner"), args.get("due_date"))
            return json.dumps({"ok": True, "task": t}, ensure_ascii=False)
        if name == "list_tasks":
            return json.dumps(db.list_tasks(chat_id, args.get("status", "todo")), ensure_ascii=False)
        if name == "complete_task":
            return json.dumps(db.complete_task(chat_id, int(args["task_id"])), ensure_ascii=False)
        if name == "summarize_chat":
            return summarize_today(chat_id)
        if name == "list_meetings":
            return meetings_text(args["email"].strip(), args.get("date"), args.get("end_date"))
        if name == "subscribe_daily_summary":
            db.subscribe(chat_id)
            return "สมัครสรุปรายวันเรียบร้อย"
        return f"ไม่รู้จัก tool: {name}"
    except Exception as e:
        return f"เกิดข้อผิดพลาด: {e}"
