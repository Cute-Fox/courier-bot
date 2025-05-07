from telebot.async_telebot import AsyncTeleBot, types

def top_menu() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("Оставить заявку", "Выдача оборудования")
    kb.row("Просмотр оборудования")
    return kb

def register_basic_handlers(bot: AsyncTeleBot):

    @bot.message_handler(commands=["start", "help"])
    async def _start(msg: types.Message):
        await bot.send_message(
            msg.chat.id,
            "Привет! Выберите действие:",
            reply_markup=top_menu()
        )

    # ❌ УДАЛЕНО: отдельный хендлер для «Оставить заявку»
    # Его уже создаёт register_request_handlers

    @bot.message_handler(func=lambda m: m.text == "Выдача оборудования")
    async def _equip(msg: types.Message):
        from bot.handlers.equipment import start_equipment_flow
        await start_equipment_flow(bot, msg)

    @bot.message_handler(func=lambda m: m.text == "Просмотр оборудования")
    async def _equip_list(msg: types.Message):
        from bot.handlers.couriers import show_equipment_status
        await show_equipment_status(bot, msg)
