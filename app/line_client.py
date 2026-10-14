from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, PushMessageRequest, TextMessage,
    ShowLoadingAnimationRequest,
)
from .config import LINE_CHANNEL_ACCESS_TOKEN

_config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
MAX_LEN = 4900  # LINE จำกัดข้อความละ 5,000 ตัวอักษร


def _chunks(text: str):
    return [text[i:i + MAX_LEN] for i in range(0, len(text), MAX_LEN)][:5]


def reply(reply_token: str, text: str):
    with ApiClient(_config) as client:
        MessagingApi(client).reply_message(ReplyMessageRequest(
            reply_token=reply_token,
            messages=[TextMessage(text=t) for t in _chunks(text)],
        ))


def push(to: str, text: str):
    """Push นับโควตาข้อความของแพ็กเกจ OA — ใช้เท่าที่จำเป็น"""
    with ApiClient(_config) as client:
        MessagingApi(client).push_message(PushMessageRequest(
            to=to,
            messages=[TextMessage(text=t) for t in _chunks(text)],
        ))


def show_loading(user_id: str, seconds: int = 20):
    """แสดงจุดกำลังพิมพ์ (ใช้ได้เฉพาะแชทเดี่ยว)"""
    try:
        with ApiClient(_config) as client:
            MessagingApi(client).show_loading_animation(
                ShowLoadingAnimationRequest(chat_id=user_id, loading_seconds=seconds)
            )
    except Exception:
        pass
