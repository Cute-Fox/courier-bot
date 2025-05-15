# bot/handlers/basic.py
from telebot.async_telebot import AsyncTeleBot, types
from bot.config import ADMIN_IDS      # список TG-ID саппорта

def top_menu(user_id: int) -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("Оставить заявку", "Выдача оборудования")
    kb.row("Просмотр оборудования")
    if user_id in ADMIN_IDS:          # кнопка только для саппорта
        kb.row("Координация с поддержкой")
    return kb


def register_basic_handlers(bot: AsyncTeleBot):

    @bot.message_handler(commands=["start", "help"])
    async def _start(msg: types.Message):
        await bot.send_message(
            msg.chat.id,
            "Привет! Выберите действие:",
            reply_markup=top_menu(msg.from_user.id)
        )

    @bot.message_handler(func=lambda m: m.text == "Просмотр оборудования")
    async def _equip_list(msg: types.Message):
        from bot.handlers.couriers import show_equipment_status
        await show_equipment_status(bot, msg)

    @bot.message_handler(func=lambda m: m.text == "Координация с поддержкой")
    async def _support_menu(msg: types.Message):
        from bot.handlers.support import show_support_dashboard
        await show_support_dashboard(bot, msg)
