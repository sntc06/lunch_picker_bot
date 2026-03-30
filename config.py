import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
DATA_FILE: str = os.getenv("DATA_FILE", "data/restaurants.json")

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set. "
        "Please set it in your environment or in a .env file."
    )
