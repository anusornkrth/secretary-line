from datetime import datetime
from zoneinfo import ZoneInfo
from google.genai import types
from . import db
from .tools import client, TOOLS, execute_tool
from .config import GEMINI_MODEL, TIMEZONE

SYSTEM_PROMPT = """คุณคือ "เลขา" ผู้ช่วยส่วนตัวใน LINE
- ตอบเป็นภาษาไทย สุภาพ กระชับ เหมาะกับการอ่านบนมือถือ (ไม่ใช้ตาราง markdown)
- ถ้าผู้ใช้สั่งงานเกี่ยวกับ To-do หรือสรุปแชท ให้ใช้ tools ที่มี
- เรียก list_meetings เฉพาะเมื่อข้อความล่าสุดของผู้ใช้ถามเรื่องประชุมหรือปฏิทินของอีเมลใดอีเมลหนึ่ง
- ถามหลายวันให้ส่ง date และ end_date เช่น "ทั้งเดือน/เดือนนี้" = วันที่ 1 ถึงวันสุดท้ายของเดือน, "สัปดาห์นี้" = จันทร์ถึงอาทิตย์ของสัปดาห์นี้
- แปลงวันที่แบบภาษาพูด (พรุ่งนี้, ศุกร์หน้า) เป็น YYYY-MM-DD โดยอิงวันที่ปัจจุบัน
- ตอบเฉพาะข้อความล่าสุดของผู้ใช้ ไม่ต้องทวนคำตอบเก่าในประวัติแชทซ้ำ
- ถ้าไม่แน่ใจข้อมูล ให้ถามกลับ อย่าเดา
วันที่และเวลาปัจจุบัน: {now}"""


def _text(role: str, text: str) -> types.Content:
    # ในฐานข้อมูลเก็บ role เป็น 'assistant' แต่ Gemini ใช้ 'model'
    return types.Content(role="model" if role == "assistant" else "user",
                         parts=[types.Part(text=text)])


def run_agent(chat_id: str, user_text: str) -> str:
    now = datetime.now(ZoneInfo(TIMEZONE)).strftime("%A %Y-%m-%d %H:%M")
    contents = [_text(h["role"], h["content"]) for h in db.get_history(chat_id)]
    contents.append(_text("user", user_text))
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT.format(now=now),
        tools=TOOLS,
        # เรียก tool เองใน loop ด้านล่าง เพราะต้องส่ง chat_id เข้าไปด้วย
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    for _ in range(5):  # กัน loop ไม่รู้จบ
        resp = client.models.generate_content(
            model=GEMINI_MODEL, contents=contents, config=config,
        )

        calls = resp.function_calls
        if not calls:
            answer = (resp.text or "").strip() or "รับทราบค่ะ"
            db.save_turn(chat_id, user_text, answer)
            return answer

        if all(fc.name == "list_meetings" for fc in calls):
            # ผลของ list_meetings จัดรูปแบบไว้แล้ว → ส่งให้ผู้ใช้ตรง ๆ ไม่ให้ AI เรียบเรียงใหม่
            answer = "\n\n".join(
                execute_tool(fc.name, dict(fc.args or {}), chat_id) for fc in calls)
            db.save_turn(chat_id, user_text, answer)
            return answer

        # Gemini ขอเรียก tool → ทำงานแล้วส่งผลกลับ
        contents.append(resp.candidates[0].content)
        contents.append(types.Content(role="user", parts=[
            types.Part.from_function_response(
                name=fc.name,
                response={"result": execute_tool(fc.name, dict(fc.args or {}), chat_id)},
            )
            for fc in calls
        ]))

    return "ขออภัย งานนี้ซับซ้อนเกินไป ลองแบ่งเป็นคำสั่งย่อยอีกครั้งนะคะ"
