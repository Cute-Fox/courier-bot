# bot/handlers/requests.py

import asyncio
from telebot.async_telebot import AsyncTeleBot, types
from uuid import uuid4
from db.database import AsyncSessionLocal
from db.models import Request
from datetime import datetime

# Temporary in-memory storage for drafts
# Key: draft_id, Value: dict with user_id, category, title, description, priority, subcategory, photos, step
DRAFTS: dict[str, dict] = {}


def register_request_handlers(bot: AsyncTeleBot, admin_id: int):
    @bot.message_handler(func=lambda m: m.text == "Оставить заявку")
    async def start_request_flow(message: types.Message):
        # Step 1: choose category
        kb = types.InlineKeyboardMarkup(row_width=2)
        for cat in (
            "Тех. обслуживание", "Видеонаблюдение",
            "Пожарная сигнализация", "Карты доступа",
            "Охранная сигнализация"
        ):
            kb.add(types.InlineKeyboardButton(cat, callback_data=f"req_cat:{cat}"))
        await bot.send_message(
            message.chat.id,
            "Выберите категорию заявки:",
            reply_markup=kb
        )

    @bot.callback_query_handler(lambda c: c.data.startswith("req_cat:"))
    async def handle_category(call: types.CallbackQuery):
        _, category = call.data.split(":", 1)
        did = str(uuid4())
        # init draft and set next step to 'title'
        DRAFTS[did] = {
            "user_id": call.from_user.id,
            "category": category,
            "photos": [],
            "step": "title"
        }
        await bot.answer_callback_query(call.id)
        await bot.edit_message_text(
            f"Категория: {category}\nВведите заголовок заявки:",
            call.message.chat.id,
            call.message.id
        )

    @bot.message_handler(func=lambda m: any(
        d.get("user_id") == m.from_user.id and d.get("step") == "title"
        for d in DRAFTS.values()
    ))
    async def process_title(message: types.Message):
        # find active draft for this user awaiting title
        did, draft = next(
            (did, d) for did, d in DRAFTS.items()
            if d.get("user_id") == message.from_user.id and d.get("step") == "title"
        )
        # save title and clear step
        draft["title"] = message.text.strip()
        draft["step"] = None

        # Step 2: choose priority
        kb = types.InlineKeyboardMarkup(row_width=3)
        for pr in ("низкий", "средний", "блокирует работу"):
            kb.add(types.InlineKeyboardButton(pr, callback_data=f"req_prio:{did}:{pr}"))
        await bot.send_message(
            message.chat.id,
            "Выберите приоритет:",
            reply_markup=kb
        )

    @bot.callback_query_handler(lambda c: c.data.startswith("req_prio:"))
    async def handle_priority(call: types.CallbackQuery):
        _, did, prio = call.data.split(":", 2)
        draft = DRAFTS.get(did)
        if not draft:
            return await bot.answer_callback_query(call.id, "Проект не найден.")
        # save priority and set next step 'description'
        draft["priority"] = prio
        draft["step"] = "description"

        await bot.answer_callback_query(call.id)
        await bot.edit_message_text(
            f"Приоритет: {prio}\nОпишите проблему подробнее:",
            call.message.chat.id,
            call.message.id
        )

    @bot.message_handler(func=lambda m: any(
        d.get("user_id") == m.from_user.id and d.get("step") == "description"
        for d in DRAFTS.values()
    ))
    async def process_description(message: types.Message):
        did, draft = next(
            (did, d) for did, d in DRAFTS.items()
            if d.get("user_id") == message.from_user.id and d.get("step") == "description"
        )
        draft["description"] = message.text.strip()
        draft["step"] = None

        # Step 3: choose subcategory
        kb = types.InlineKeyboardMarkup(row_width=2)
        for sub in ("Электрика", "Кондиционеры", "Оборудование", "Другое"):
            kb.add(types.InlineKeyboardButton(sub, callback_data=f"req_sub:{did}:{sub}"))
        await bot.send_message(
            message.chat.id,
            "Уточните проблематику:",
            reply_markup=kb
        )

    @bot.callback_query_handler(lambda c: c.data.startswith("req_sub:"))
    async def handle_subcategory(call: types.CallbackQuery):
        _, did, sub = call.data.split(":", 2)
        draft = DRAFTS.get(did)
        if not draft:
            return await bot.answer_callback_query(call.id, "Проект не найден.")
        draft["subcategory"] = sub
        draft["step"] = None

        await bot.answer_callback_query(call.id)
        # Step 4: ask for photo or skip
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("Пропустить", callback_data=f"req_skip:{did}"))
        await bot.edit_message_text(
            f"Уточнение: {sub}\nПрикрепите фото или нажмите «Пропустить»",
            call.message.chat.id,
            call.message.id,
            reply_markup=kb
        )

    @bot.callback_query_handler(lambda c: c.data.startswith((
        "req_skip:", "req_confirm:", "req_cancel:"
    )))
    async def handle_finalize(call: types.CallbackQuery):
        action, did = call.data.split(":", 1)
        draft = DRAFTS.get(did)
        await bot.answer_callback_query(call.id)

        if action == "req_cancel":
            DRAFTS.pop(did, None)
            return await bot.edit_message_text(
                "❌ Заявка отменена.",
                call.message.chat.id,
                call.message.id
            )
        # on skip or confirm, save and clear draft
        if not draft:
            return
        # persist to DB
        async with AsyncSessionLocal() as sess:
            req_obj = Request(
                user_id=draft["user_id"],
                category=draft["category"],
                subcategory=draft.get("subcategory"),
                title=draft.get("title"),
                description=draft.get("description"),
                priority=draft.get("priority"),
                photos=draft.get("photos"),
                created_at=datetime.utcnow()
            )
            sess.add(req_obj)
            await sess.commit()
        DRAFTS.pop(did, None)

        await bot.edit_message_text(
            "✅ Заявка создана!",
            call.message.chat.id,
            call.message.id
        )
        if admin_id:
            await bot.send_message(
                admin_id,
                f"Новая заявка #{req_obj.id}\nКатегория: {req_obj.category}\n"
                f"Заголовок: {req_obj.title}\nПриоритет: {req_obj.priority}"
            )

# После импорта в main.py вызвать: register_request_handlers(bot, ADMIN_ID)
