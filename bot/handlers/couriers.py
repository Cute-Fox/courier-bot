from telebot.async_telebot import AsyncTeleBot, types
from telebot.asyncio_handler_backends import State, StatesGroup

class CourierStates(StatesGroup):
    ID = State()
    TRANSPORT_TYPE = State()
    TRANSPORT_PHOTO = State()

async def start_courier_registration(message: types.Message):
    await message.answer("Введите ID курьера:")
    await CourierStates.ID.set()

async def show_equipment_status(message: types.Message):
    # TODO: выбрать из БД все equipment и вывести статус
    await message.answer("Статус оборудования:\nID123 — у курьера\nID456 — на складе\n...")

def register_courier_handlers(bot: AsyncTeleBot):
    bot.register_message_handler(
        start_courier_registration,
        func=lambda m: m.text == "Регистрация курьера"
    )
    bot.register_message_handler(
        show_equipment_status,
        func=lambda m: m.text == "Просмотр оборудования"
    )
