# bot/handlers/support.py
import logging
from datetime import datetime
from typing import List, Dict

from telebot.async_telebot import AsyncTeleBot, types
from sqlalchemy import select

from db.database import AsyncSessionLocal
from db.models import (
    Request,
    RequestStatus,
    Message,
    User,
)

logger = logging.getLogger(__name__)

WAIT_QUESTION: Dict[int, int] = {}   # admin_id   -> request_id
WAIT_ANSWER:   Dict[int, int] = {}   # courier_id -> request_id
REQ_PER_PAGE = 10


async def show_support_dashboard(bot: AsyncTeleBot, message: types.Message):
    await _send_request_page(bot, message.chat.id, None, page=0, edit=False)


def register_support_handlers(bot: AsyncTeleBot, admin_ids: List[int]):

    # ───── Dashboard ─────
    @bot.callback_query_handler(lambda c: c.data.startswith("req_pg:"))
    async def _paginate(call: types.CallbackQuery):
        page = int(call.data.split(":", 1)[1])
        await bot.answer_callback_query(call.id)
        await _send_request_page(bot, call.message.chat.id, call.message.id, page, edit=True)

    @bot.callback_query_handler(lambda c: c.data == "req_dash_close")
    async def _dash_close(call: types.CallbackQuery):
        await bot.answer_callback_query(call.id)
        await bot.edit_message_reply_markup(call.message.chat.id, call.message.id, reply_markup=None)

    @bot.callback_query_handler(lambda c: c.data.startswith("req_card:"))
    async def _card(call: types.CallbackQuery):
        req_id = int(call.data.split(":", 1)[1])
        async with AsyncSessionLocal() as sess:
            req = await sess.get(Request, req_id)
        if not req:
            return await bot.answer_callback_query(call.id, "Не найдена")

        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("💬 Вопрос курьеру", callback_data=f"req_ask:{req_id}"))

        txt = (
            f"*Заявка #{req.id}*\n"
            f"Категория: {req.category}\n"
            f"Приоритет: {req.priority}\n"
            f"Статус: {req.status.value}"
        )
        await bot.answer_callback_query(call.id)
        await bot.send_message(call.from_user.id, txt, parse_mode="Markdown", reply_markup=kb)

    # ───── Вопрос саппорта ─────
    @bot.callback_query_handler(lambda c: c.data.startswith("req_ask:"))
    async def ask_click(call: types.CallbackQuery):
        req_id = int(call.data.split(":", 1)[1])
        if call.from_user.id not in admin_ids:
            return await bot.answer_callback_query(call.id, "⛔ Недостаточно прав")

        WAIT_QUESTION[call.from_user.id] = req_id
        await bot.answer_callback_query(call.id)
        await bot.send_message(call.from_user.id, "Введите вопрос курьеру:")

    @bot.message_handler(func=lambda m: m.from_user.id in WAIT_QUESTION)
    async def receive_question(msg: types.Message):
        req_id = WAIT_QUESTION.pop(msg.from_user.id)
        text = msg.text.strip()

        async with AsyncSessionLocal() as sess:
            req = await sess.get(Request, req_id)
            if not req:
                return await bot.reply_to(msg, "⚠️ Заявка не найдена")

            sess.add(Message(
                request_id=req_id,
                from_user=msg.from_user.id,
                to_user=req.user_id,
                text=text,
                created_at=datetime.utcnow(),
            ))
            req.status = RequestStatus.NEED_INFO
            await sess.commit()

        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("💬 Ответить", callback_data=f"req_ans:{req_id}"))
        await bot.send_message(
            req.user_id,
            f"❓ *Вопрос по вашей заявке #{req.id}*\n\n{text}",
            parse_mode="Markdown",
            reply_markup=kb,
        )
        await bot.reply_to(msg, "Вопрос отправлен ✅")

    # ───── Ответ курьера ─────
    @bot.callback_query_handler(lambda c: c.data.startswith("req_ans:"))
    async def answer_click(call: types.CallbackQuery):
        req_id = int(call.data.split(":", 1)[1])
        WAIT_ANSWER[call.from_user.id] = req_id
        await bot.answer_callback_query(call.id)
        await bot.send_message(call.from_user.id, "Введите ответ саппорту:")

    @bot.message_handler(func=lambda m: m.from_user.id in WAIT_ANSWER)
    async def receive_answer(msg: types.Message):
        req_id = WAIT_ANSWER.pop(msg.from_user.id)
        text = msg.text.strip()

        async with AsyncSessionLocal() as sess:
            req = await sess.get(Request, req_id)
            if not req:
                return await bot.reply_to(msg, "⚠️ Заявка не найдена")

            for adm in admin_ids:
                sess.add(Message(
                    request_id=req_id,
                    from_user=msg.from_user.id,
                    to_user=adm,
                    text=text,
                    created_at=datetime.utcnow(),
                ))
            req.status = RequestStatus.IN_PROGRESS
            await sess.commit()

        for adm in admin_ids:
            await bot.send_message(
                adm,
                f"💬 *Ответ по заявке #{req_id}*\n\n{text}",
                parse_mode="Markdown",
            )
        await bot.reply_to(msg, "Ответ отправлен ✅")


# ───── helpers ─────
async def _send_request_page(bot: AsyncTeleBot, chat_id: int, msg_id: int | None, page: int, edit=False):
    async with AsyncSessionLocal() as sess:
        items = (
            await sess.execute(
                select(Request)
                .where(Request.status.in_([RequestStatus.OPEN,
                                           RequestStatus.NEED_INFO,
                                           RequestStatus.IN_PROGRESS]))
                .order_by(Request.created_at.desc())
            )
        ).scalars().all()

    total = max(1, (len(items) + REQ_PER_PAGE - 1) // REQ_PER_PAGE)
    page = max(0, min(page, total - 1))
    start, end = page * REQ_PER_PAGE, (page + 1) * REQ_PER_PAGE

    kb = types.InlineKeyboardMarkup()
    for r in items[start:end]:
        cat = r.category if len(r.category) <= 18 else r.category[:15] + "…"
        kb.add(types.InlineKeyboardButton(f"#{r.id} • {cat} • {r.status.value}",
                                          callback_data=f"req_card:{r.id}"))

    nav = []
    if page > 0:
        nav.append(types.InlineKeyboardButton("◀️", callback_data=f"req_pg:{page-1}"))
    if page + 1 < total:
        nav.append(types.InlineKeyboardButton("▶️", callback_data=f"req_pg:{page+1}"))
    if nav:
        kb.row(*nav)
    kb.add(types.InlineKeyboardButton("❌ Закрыть", callback_data="req_dash_close"))

    header = f"*Заявки (стр. {page+1}/{total})*"
    text = header if items else header + "\n\n_Нет открытых заявок_"

    if edit and msg_id:
        await bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb, parse_mode="Markdown")
    else:
        await bot.send_message(chat_id, text, reply_markup=kb, parse_mode="Markdown")
