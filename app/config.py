import os
from dotenv import load_dotenv

load_dotenv()

LINE_CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
CRON_SECRET = os.environ["CRON_SECRET"]
BOT_TRIGGER = os.getenv("BOT_TRIGGER", "เลขา")
# Google Calendar (ไม่บังคับ): ใส่ path ของไฟล์ key หรือเนื้อหา JSON อย่างใดอย่างหนึ่ง
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
TIMEZONE = "Asia/Bangkok"
