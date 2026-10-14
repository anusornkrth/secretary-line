import re

from fastapi import FastAPI, Request, Header, HTTPException, BackgroundTasks
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent, JoinEvent

from . import db, line_client
from .agent import run_agent
from .tools import meetings_text, summarize_today
from .config import LINE_CHANNEL_SECRET, CRON_SECRET, BOT_TRIGGER

app = FastAPI()
parser = WebhookParser(LINE_CHANNEL_SECRET)
EMAIL_ONLY = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/callback")
async def callback(request: Request, background: BackgroundTasks,
                   x_line_signature: str = Header(None)):
    body = (await request.body()).decode("utf-8")
    try:
        events = parser.parse(body, x_line_signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in events:
        background.add_task(handle_event, event)
    return "OK"  # ตอบ LINE ทันที ป้องกัน timeout/retry


def handle_event(event):
    src = event.source
    chat_id = getattr(src, "group_id", None) or getattr(src, "room_id", None) or src.user_id
    is_group = src.type in ("group", "room")

    if isinstance(event, JoinEvent):
        line_client.reply(event.reply_token,
            f"สวัสดีค่ะ เลขาพร้อมช่วยงาน 🙏\nพิมพ์ \"{BOT_TRIGGER} ...\" เพื่อเรียกใช้ "
            f"เช่น \"{BOT_TRIGGER} สรุปวันนี้\"\n"
            "ℹ️ เลขาจะบันทึกข้อความในกลุ่มเพื่อใช้สรุปงาน")
        return

    if not (isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent)):
        return

    text = event.message.text.strip()

    # 1) บันทึกข้อความทุกข้อความ (ใช้สรุปแชท)
    try:
        db.save_message(chat_id, getattr(src, "user_id", None), text)
    except Exception as e:
        print("save_message error:", e)

    # 2) ในกลุ่ม: ตอบเฉพาะเมื่อถูกเรียก
    if is_group:
        if not text.startswith(BOT_TRIGGER):
            return
        text = text[len(BOT_TRIGGER):].strip() or "สวัสดี"
    else:
        line_client.show_loading(src.user_id)

    # 3) ให้ Agent คิด แล้วตอบกลับ
    try:
        if EMAIL_ONLY.fullmatch(text):
            # ส่งมาแค่อีเมล → ตอบรายการประชุมวันนี้ตรง ๆ ไม่ต้องผ่าน AI (เร็วกว่าและไม่กินโควตา)
            answer = meetings_text(text)
        else:
            answer = run_agent(chat_id, text)
    except Exception as e:
        if "RESOURCE_EXHAUSTED" in str(e):
            answer = "ขออภัย วันนี้โควตา AI หมดแล้ว ลองใหม่ภายหลังนะคะ (ส่งอีเมลเพื่อดูรายการประชุมยังใช้ได้)"
        else:
            answer = "ขออภัย ระบบขัดข้องชั่วคราว ลองใหม่อีกครั้งนะคะ"
        print("agent error:", e)

    try:
        line_client.reply(event.reply_token, answer)
    except Exception:
        # reply token หมดอายุ (เช่น AI คิดนาน) → ใช้ push แทน
        line_client.push(chat_id, answer)


@app.post("/cron/daily-summary")
def daily_summary(x_cron_secret: str = Header(None)):
    if x_cron_secret != CRON_SECRET:
        raise HTTPException(status_code=401)
    sent = 0
    for chat_id in db.all_subscriptions():
        summary = summarize_today(chat_id)
        if not summary.startswith("วันนี้ยังไม่มีข้อความ"):
            line_client.push(chat_id, "🗓️ สรุปประจำวัน\n\n" + summary)
            sent += 1
    return {"sent": sent}
