import os
import logging
import asyncio

from dotenv import load_dotenv
from telebot.async_telebot import AsyncTeleBot

# DB init
from db.database import init_db

# Handlers
from bot.handlers.basic import register_basic_handlers
from bot.handlers.requests import register_request_handlers
from bot.handlers.equipment  import register_equipment_handlers
from bot.handlers.couriers import register_courier_handlers
from bot.handlers.support import register_support_handlers

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in .env")

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
ADMIN_IDS = [767221819] 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


bot = AsyncTeleBot(BOT_TOKEN)

async def main():
    await init_db()
    logger.info("✅ Database initialized")

    register_basic_handlers(bot)
    register_request_handlers(bot, ADMIN_ID)
    register_equipment_handlers(bot, ADMIN_ID)
    register_courier_handlers(bot)
    register_support_handlers(bot, ADMIN_IDS)
    logger.info("🔌 Handlers registered")

    await bot.infinity_polling()

if __name__ == "__main__":
    asyncio.run(main())
