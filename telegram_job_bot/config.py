import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
NVIDIA_API_KEY = os.environ["NVIDIA_API_KEY"]

ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "")

DATABASE_PATH = os.getenv("DATABASE_PATH", "bot_data.db")

NVIDIA_MODEL = "moonshotai/kimi-k3"