import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
except:
    ADMIN_ID = None

CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@YourChannel")
VERIFICATION_SERVER_PORT = int(os.getenv("VERIFICATION_PORT", "8080"))
FINGERPRINT_WEB_URL = os.getenv("FINGERPRINT_WEB_URL", "https://khaledsaleman.github.io/ihalat/")
DATABASE_PATH = os.getenv("DATABASE_PATH", "bot_database.db")

if not BOT_TOKEN:
    print("❌ خطأ: لم يتم تعيين BOT_TOKEN في ملف .env")
    sys.exit(1)

if not ADMIN_ID:
    print("❌ خطأ: لم يتم تعيين ADMIN_ID في ملف .env")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
