import logging
from uuid import uuid4
from datetime import datetime

from telebot.async_telebot import AsyncTeleBot, types
from db.database import AsyncSessionLocal
from db.models import Request, User

logger = logging.getLogger(__name__)

DRAFTS: dict[str, dict] = {}

PRIO_LABELS = ["низкий", "средний", "блокирует работу"]
SUBCATEGORIES = ["Электрика", "Кондиционеры", "Оборудование", "Другое"]


def register_request_handlers(bot: AsyncTeleBot, admin_id: int):
    @bot.message_handler(func=lambda m: m.text == "Оставить заявку")
    async def start_request_flow(message: types.Message):
        kb = types.InlineKeyboardMarkup(row_width=2)
        for cat in (
            "Тех. обслуживание", "Видеонаблюдение",
            "Пожарная сигнализация", "Карты доступа",
            "Контроль доступа и домофония",
            "Дератизация / Дезинсекция", "Охранная сигнализация"
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
        DRAFTS[did] = {
            "user_id": call.from_user.id,
            "category": category,
            "photos": [],
            "step": "title"
        }
        logger.info(f"[handle_category] CREATED draft {did}: {DRAFTS[did]}")
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
        did, draft = next(
            (did, d) for did, d in DRAFTS.items()
            if d["user_id"] == message.from_user.id and d["step"] == "title"
        )
        draft["title"] = message.text.strip()
        draft["step"] = "priority"
        kb = types.InlineKeyboardMarkup(row_width=3)
        for idx, label in enumerate(PRIO_LABELS):
            kb.add(types.InlineKeyboardButton(label, callback_data=f"req_prio:{did}:{idx}"))
        await bot.send_message(
            message.chat.id,
            "Выберите приоритет:",
            reply_markup=kb
        )

    @bot.callback_query_handler(lambda c: c.data.startswith("req_prio:"))
    async def handle_priority(call: types.CallbackQuery):
        _, did, idx_str = call.data.split(":", 2)
        draft = DRAFTS.get(did)
        if not draft:
            return await bot.answer_callback_query(call.id, "Драфт не найден.")
        prio_idx = int(idx_str)
        draft["priority"] = PRIO_LABELS[prio_idx]
        draft["step"] = "description"
        await bot.answer_callback_query(call.id)
        await bot.edit_message_text(
            f"Приоритет: {PRIO_LABELS[prio_idx]}\nОпишите проблему подробнее:",
            call.message.chat.id,
            call.message.id
        )

    @bot.message_handler(func=lambda m: any(
        d["user_id"] == m.from_user.id and d.get("step") == "description"
        for d in DRAFTS.values()
    ))
    async def process_description(message: types.Message):
        did, draft = next(
            (did, d) for did, d in DRAFTS.items()
            if d["user_id"] == message.from_user.id and d.get("step") == "description"
        )
        draft["description"] = message.text.strip()
        draft["step"] = "subcategory"
        kb = types.InlineKeyboardMarkup(row_width=2)
        for idx, sub in enumerate(SUBCATEGORIES):
            kb.add(types.InlineKeyboardButton(sub, callback_data=f"req_sub:{did}:{idx}"))
        await bot.send_message(
            message.chat.id,
            "Уточните проблематику:",
            reply_markup=kb
        )

    @bot.callback_query_handler(lambda c: c.data.startswith("req_sub:"))
    async def handle_subcategory(call: types.CallbackQuery):
        _, did, idx_str = call.data.split(":", 2)
        draft = DRAFTS.get(did)
        if not draft:
            return await bot.answer_callback_query(call.id, "Драфт не найден.")
        sub = SUBCATEGORIES[int(idx_str)]
        draft["subcategory"] = sub
        draft["step"] = "photo"
        await bot.answer_callback_query(call.id)
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("➕ Ещё фото", callback_data=f"req_photo_add:{did}"))
        kb.add(types.InlineKeyboardButton("Пропустить", callback_data=f"req_skip:{did}"))
        await bot.edit_message_text(
            f"Подкатегория: {sub}\nПрикрепите фото или выберите действие:",
            call.message.chat.id,
            call.message.id,
            reply_markup=kb
        )

    @bot.callback_query_handler(lambda c: c.data.startswith("req_photo_add:"))
    async def handle_add_photo(call: types.CallbackQuery):
        _, did = call.data.split(":", 1)
        draft = DRAFTS.get(did)
        if not draft:
            return await bot.answer_callback_query(call.id, "Драфт не найден.")
        draft["step"] = "photo"
        await bot.answer_callback_query(call.id)
        await bot.send_message(call.message.chat.id, "Отправьте фото:")

    @bot.message_handler(content_types=["photo"], func=lambda m: any(
        d["user_id"] == m.from_user.id and d.get("step") == "photo"
        for d in DRAFTS.values()
    ))
    async def process_photo(message: types.Message):
        did, draft = next(
            (did, d) for did, d in DRAFTS.items()
            if d["user_id"] == message.from_user.id and d.get("step") == "photo"
        )
        photos = draft.get("photos", [])
        photos.append(message.photo[-1].file_id)
        draft["photos"] = photos
        draft["step"] = "finalize"
        kb = types.InlineKeyboardMarkup()
        kb.row(
            types.InlineKeyboardButton("➕ Ещё фото", callback_data=f"req_photo_add:{did}"),
            types.InlineKeyboardButton("▶️ Далее", callback_data=f"req_confirm:{did}"),
            types.InlineKeyboardButton("Пропустить", callback_data=f"req_skip:{did}")
        )
        await bot.send_message(
            message.chat.id,
            "Фото добавлено. Выберите действие:",
            reply_markup=kb
        )

    @bot.callback_query_handler(lambda c: c.data.startswith(("req_skip:", "req_confirm:", "req_cancel:")))
    async def handle_finalize(call: types.CallbackQuery):
        action, did = call.data.split(":", 1)
        draft = DRAFTS.get(did)
        await bot.answer_callback_query(call.id)
        if action == "req_cancel":
            DRAFTS.pop(did, None)
            await bot.edit_message_text("❌ Заявка отменена.", call.message.chat.id, call.message.id)
            return
        if not draft:
            return

        async with AsyncSessionLocal() as sess:
            user = await sess.get(User, draft["user_id"])
            if not user:
                user = User(
                    id=draft["user_id"],
                    name=call.from_user.username or call.from_user.first_name or ""
                )
                sess.add(user)
                await sess.flush()

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
        await bot.edit_message_text("✅ Заявка создана!", call.message.chat.id, call.message.id)
        if admin_id:
            await bot.send_message(
                admin_id,
                f"Новая заявка #{req_obj.id}\n"
                f"Категория: {req_obj.category}\n"
                f"Заголовок: {req_obj.title}\n"
                f"Приоритет: {req_obj.priority}"
            )