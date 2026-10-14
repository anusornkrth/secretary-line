import json
from datetime import date, datetime
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
            "ใช้เมื่อผู้ใช้ส่งอีเมลมา หรือถามว่าใครมีประชุมอะไร ผลลัพธ์จัดรูปแบบพร้อมส่งให้ผู้ใช้แล้ว"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "อีเมลเจ้าของปฏิทิน"},
                "date": {"type": "string", "description": "วันที่ YYYY-MM-DD (ไม่ระบุ = วันนี้)"},
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


def meetings_text(email: str, day_str: str | None = None) -> str:
    today = datetime.now(ZoneInfo(TIMEZONE)).date()
    day = date.fromisoformat(day_str) if day_str else today
    label = "วันนี้" if day == today else f"วันที่ {day.isoformat()} "
    try:
        meetings = calendar_client.list_meetings(email, day)
    except calendar_client.CalendarError as e:
        return str(e)
    if not meetings:
        return f"คุณ {email}\n{label}ไม่มีประชุม"
    lines = [f"คุณ {email}", "มีประชุมดังนี้" if day == today else f"มีประชุม{label}ดังนี้"]
    for m in meetings:
        title = m["title"] if m["title"].startswith("ประชุม") else f"ประชุม {m['title']}"
        lines.append(f"{m['time']} {title}")
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
            return meetings_text(args["email"].strip(), args.get("date"))
        if name == "subscribe_daily_summary":
            db.subscribe(chat_id)
            return "สมัครสรุปรายวันเรียบร้อย"
        return f"ไม่รู้จัก tool: {name}"
    except Exception as e:
        return f"เกิดข้อผิดพลาด: {e}"
