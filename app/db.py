from datetime import datetime, time
from zoneinfo import ZoneInfo
from supabase import create_client
from .config import SUPABASE_URL, SUPABASE_KEY, TIMEZONE

sb = create_client(SUPABASE_URL, SUPABASE_KEY)
TZ = ZoneInfo(TIMEZONE)


# ---------- messages ----------
def save_message(chat_id: str, user_id: str | None, text: str):
    sb.table("messages").insert(
        {"chat_id": chat_id, "user_id": user_id, "text": text}
    ).execute()


def get_messages_today(chat_id: str) -> list[dict]:
    start = datetime.combine(datetime.now(TZ).date(), time.min, tzinfo=TZ)
    res = (sb.table("messages").select("user_id,text,created_at")
           .eq("chat_id", chat_id)
           .gte("created_at", start.isoformat())
           .order("created_at").limit(1000).execute())
    return res.data


# ---------- conversation memory ----------
def get_history(chat_id: str, limit: int = 10) -> list[dict]:
    res = (sb.table("conversations").select("role,content")
           .eq("chat_id", chat_id)
           .order("created_at", desc=True).limit(limit).execute())
    history = list(reversed(res.data))
    # Claude ต้องเริ่มด้วย role 'user'
    while history and history[0]["role"] != "user":
        history.pop(0)
    return [{"role": h["role"], "content": h["content"]} for h in history]


def save_turn(chat_id: str, user_text: str, bot_text: str):
    sb.table("conversations").insert([
        {"chat_id": chat_id, "role": "user", "content": user_text},
        {"chat_id": chat_id, "role": "assistant", "content": bot_text},
    ]).execute()


# ---------- tasks ----------
def add_task(chat_id, title, owner=None, due_date=None):
    return sb.table("tasks").insert({
        "chat_id": chat_id, "title": title,
        "owner": owner, "due_date": due_date,
    }).execute().data[0]


def list_tasks(chat_id, status="todo"):
    q = sb.table("tasks").select("id,title,owner,due_date,status").eq("chat_id", chat_id)
    if status != "all":
        q = q.eq("status", status)
    return q.order("due_date", nullsfirst=False).execute().data


def complete_task(chat_id, task_id: int):
    return (sb.table("tasks").update({"status": "done"})
            .eq("chat_id", chat_id).eq("id", task_id).execute().data)


# ---------- subscriptions ----------
def subscribe(chat_id):
    sb.table("subscriptions").upsert({"chat_id": chat_id}).execute()


def all_subscriptions() -> list[str]:
    return [r["chat_id"] for r in sb.table("subscriptions").select("chat_id").execute().data]
