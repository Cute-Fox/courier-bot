# bot/handlers/couriers.py
from telebot.async_telebot import AsyncTeleBot, types
from sqlalchemy import select

from db.database import AsyncSessionLocal
from db.models import Equipment, EquipmentStatus

PER_PAGE = 10
ICON = {
    EquipmentStatus.IN_STOCK:     "🟢",
    EquipmentStatus.WITH_COURIER: "🚴",
    EquipmentStatus.NEED_REPAIR:  "🛠️",
}

def _keyboard(page: int, total_pages: int):
    kb = types.InlineKeyboardMarkup()
    if page > 0:
        kb.add(types.InlineKeyboardButton("◀️", callback_data=f"eq_page:{page-1}"))
    if page + 1 < total_pages:
        kb.add(types.InlineKeyboardButton("▶️", callback_data=f"eq_page:{page+1}"))
    kb.add(types.InlineKeyboardButton("❌ Закрыть", callback_data="eq_close"))
    return kb

async def _render_page(bot: AsyncTeleBot, chat_id: int, msg_id: int | None, page: int, edit: bool):
    async with AsyncSessionLocal() as sess:
        eq_list = (await sess.execute(select(Equipment))).scalars().all()

    total_pages = max(1, (len(eq_list) + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    start, end = page * PER_PAGE, (page + 1) * PER_PAGE

    lines = []
    for eq in eq_list[start:end]:
        icon = ICON[eq.status]
        if eq.status == EquipmentStatus.WITH_COURIER and eq.assigned_to:
            status = f"У курьера #{eq.assigned_to}"
        elif eq.status == EquipmentStatus.NEED_REPAIR:
            status = "Нужен ремонт"
        else:
            status = "На складе"
        lines.append(f"{icon} *{eq.eq_id}* — {status}")

    text = "*Оборудование* " \
           f"(стр. {page+1}/{total_pages})\n\n" + ("\n".join(lines) or "_список пуст_")
    kb = _keyboard(page, total_pages)

    if edit:
        await bot.edit_message_text(text, chat_id, msg_id,
                                    reply_markup=kb, parse_mode="Markdown")
    else:
        await bot.send_message(chat_id, text,
                               reply_markup=kb, parse_mode="Markdown")

# ───────────────────── публичные обработчики ─────────────────────
async def show_equipment_status(bot: AsyncTeleBot, message: types.Message):
    """Вызывается из basic.py по кнопке «Просмотр оборудования»."""
    await _render_page(bot, message.chat.id, None, page=0, edit=False)

def register_courier_handlers(bot: AsyncTeleBot):
    @bot.callback_query_handler(lambda c: c.data.startswith("eq_page:"))
    async def _paginate(call: types.CallbackQuery):
        page = int(call.data.split(":", 1)[1])
        await _render_page(bot, call.message.chat.id, call.message.id, page, edit=True)
        await bot.answer_callback_query(call.id)

    @bot.callback_query_handler(lambda c: c.data == "eq_close")
    async def _close(call: types.CallbackQuery):
        await bot.edit_message_reply_markup(call.message.chat.id, call.message.id, reply_markup=None)
        await bot.answer_callback_query(call.id)
