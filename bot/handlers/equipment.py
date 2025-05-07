from telebot.async_telebot import AsyncTeleBot, types
from telebot.asyncio_handler_backends import State, StatesGroup

class EquipmentStates(StatesGroup):
    ACTION = State()
    EQ_ID = State()
    COURIER_ID = State()
    ISSUE_DESC = State()
    PHOTO = State()

async def start_equipment_flow(message: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("Выдать курьеру", "Принять на склад", "Нужен ремонт")
    await message.answer("Выберите действие с оборудованием:", reply_markup=kb)
    await EquipmentStates.ACTION.set()

# TODO: по состоянию ACTION обрабатывать выбор и переходить в EQ_ID/COURIER_ID/ISSUE_DESC

def register_equipment_handlers(bot: AsyncTeleBot):
    bot.register_message_handler(
        start_equipment_flow,
        func=lambda m: m.text == "Выдача оборудования"
    )
