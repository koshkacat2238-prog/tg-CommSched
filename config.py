import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
DATABASE_URL = os.getenv("DATABASE_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "")

ADMIN_ROLES = ("admin", "owner")
TEACHER_ROLES = ("teacher", "admin", "owner")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")
if OWNER_ID == 0:
    raise RuntimeError("OWNER_ID is not set")