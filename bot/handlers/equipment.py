# bot/handlers/equipment.py

import logging
from datetime import datetime
from uuid import uuid4

from telebot.async_telebot import AsyncTeleBot, types
from sqlalchemy import select

from db.database import AsyncSessionLocal
from db.models import Equipment, Request, RequestStatus, EquipmentStatus, User

logger = logging.getLogger(__name__)

# Временное хранилище черновиков для оборудования
EQUIP_DRAFTS: dict[str, dict] = {}
# Структура: { draft_id: { user_id, step, action, eq, eq_id, issue_desc } }

ACTIONS = ["Выдать курьеру", "Принять на склад", "Нужен ремонт"]


def register_equipment_handlers(bot: AsyncTeleBot, admin_id: int):
    # ─────────── админская команда для добавления оборудования ───────────
    @bot.message_handler(commands=["add_equipment"])
    async def add_equipment_cmd(msg: types.Message):
        if msg.from_user.id != admin_id:
            return await bot.reply_to(msg, "⛔ Только администратор.")
        parts = msg.text.split(maxsplit=2)
        if len(parts) < 2:
            return await bot.reply_to(
                msg,
                "Использование: /add_equipment <ID> [Тип]\n"
                "Пример: /add_equipment 0001 bike"
            )
        _, eq_id, eq_type = parts[0], parts[1], (parts[2] if len(parts) == 3 else "unknown")
        async with AsyncSessionLocal() as sess:
            # проверяем по полю eq_id (не по PK)
            exists = await sess.execute(
                select(Equipment).where(Equipment.eq_id == eq_id)
            )
            if exists.scalar_one_or_none():
                return await bot.reply_to(msg, "⚠️ Оборудование с таким ID уже есть.")
            # создаём запись
            sess.add(Equipment(
                eq_id=eq_id,
                type=eq_type,
                status=EquipmentStatus.IN_STOCK,
                assigned_to=None
            ))
            await sess.commit()
        await bot.reply_to(msg, f"✅ Оборудование добавлено: {eq_id} ({eq_type})")

    # ─────────── стартовый экран для операций с оборудованием ───────────
    @bot.message_handler(func=lambda m: m.text == "Выдача оборудования")
    async def start_equipment(msg: types.Message):
        kb = types.InlineKeyboardMarkup()
        for action in ACTIONS:
            kb.add(types.InlineKeyboardButton(action, callback_data=f"eq_act:{action}"))
        kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="eq_cancel"))
        await bot.send_message(msg.chat.id, "Выберите действие с оборудованием:", reply_markup=kb)

    # ─────────── пользователь выбрал действие ───────────
    @bot.callback_query_handler(lambda c: c.data.startswith("eq_act:"))
    async def act_chosen(call: types.CallbackQuery):
        action = call.data.split(":", 1)[1]
        did = str(uuid4())
        EQUIP_DRAFTS[did] = {
            "user_id": call.from_user.id,
            "step": "eq_id",
            "action": action
        }
        await bot.answer_callback_query(call.id)
        await bot.edit_message_text(
            f"*Действие:* {action}\nВведите ID оборудования:",
            call.message.chat.id,
            call.message.id,
            parse_mode="Markdown"
        )

    # ─────────── отмена операции ───────────
    @bot.callback_query_handler(lambda c: c.data == "eq_cancel")
    async def cancel_eq(call: types.CallbackQuery):
        # удаляем все черновики пользователя
        to_remove = [did for did, d in EQUIP_DRAFTS.items() if d["user_id"] == call.from_user.id]
        for did in to_remove:
            EQUIP_DRAFTS.pop(did, None)
        await bot.answer_callback_query(call.id, "Операция отменена")
        await bot.edit_message_reply_markup(call.message.chat.id, call.message.id, reply_markup=None)

    # ─────────── ввод ID оборудования ───────────
    @bot.message_handler(func=lambda m: _draft_step(m.from_user.id) == "eq_id")
    async def got_eq_id(msg: types.Message):
        did, draft = _find_draft(msg.from_user.id)
        eq_id = msg.text.strip()
        async with AsyncSessionLocal() as sess:
            eq = (await sess.execute(
                select(Equipment).where(Equipment.eq_id == eq_id)
            )).scalar_one_or_none()
        if not eq:
            return await bot.reply_to(msg, "❌ Оборудование не найдено, попробуйте другой ID.")
        draft.update({"eq": eq, "eq_id": eq_id})

        action = draft["action"]
        if action == "Выдать курьеру":
            draft["step"] = "courier_id"
            await bot.reply_to(msg, "Введите ID курьера:")
        elif action == "Принять на склад":
            await _update_status(eq, EquipmentStatus.IN_STOCK, None)
            EQUIP_DRAFTS.pop(did, None)
            await bot.reply_to(msg, "✅ Оборудование принято на склад")
        else:  # "Нужен ремонт"
            draft["step"] = "issue_desc"
            await bot.reply_to(msg, "Опишите проблему для ремонта:")

    # ─────────── ввод ID курьера для выдачи ───────────
    @bot.message_handler(func=lambda m: _draft_step(m.from_user.id) == "courier_id")
    async def got_courier_id(msg: types.Message):
        did, draft = _find_draft(msg.from_user.id)
        try:
            courier_id = int(msg.text.strip())
        except ValueError:
            return await bot.reply_to(msg, "ID курьера должен быть числом.")

        # обеспечиваем наличие пользователя
        async with AsyncSessionLocal() as sess:
            if not await sess.get(User, courier_id):
                sess.add(User(id=courier_id, name=""))
                await sess.flush()

        await _update_status(draft["eq"], EquipmentStatus.WITH_COURIER, courier_id)
        EQUIP_DRAFTS.pop(did, None)
        await bot.reply_to(msg, "✅ Оборудование выдано курьеру")

    # ─────────── ввод описания поломки ───────────
    @bot.message_handler(func=lambda m: _draft_step(m.from_user.id) == "issue_desc")
    async def got_issue_desc(msg: types.Message):
        did, draft = _find_draft(msg.from_user.id)
        draft["issue_desc"] = msg.text.strip()
        draft["step"] = "photo"
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("Пропустить фото", callback_data=f"eq_skip:{did}"))
        await bot.reply_to(msg, "Прикрепите фото или нажмите «Пропустить фото»:", reply_markup=kb)

    # ─────────── приём фото ───────────
    @bot.message_handler(content_types=["photo"], func=lambda m: _draft_step(m.from_user.id) == "photo")
    async def got_photo(msg: types.Message):
        did, draft = _find_draft(msg.from_user.id)
        photo_id = msg.photo[-1].file_id
        await _save_repair_request(draft, photo_id)
        EQUIP_DRAFTS.pop(did, None)
        await bot.reply_to(msg, "✅ Заявка на ремонт зарегистрирована")

    # ─────────── пропуск фото ───────────
    @bot.callback_query_handler(lambda c: c.data.startswith("eq_skip:"))
    async def skip_photo(call: types.CallbackQuery):
        did = call.data.split(":", 1)[1]
        draft = EQUIP_DRAFTS.pop(did, None)
        if draft:
            await _save_repair_request(draft, photo_id=None)
        await bot.answer_callback_query(call.id, "✅ Заявка на ремонт зарегистрирована")
        await bot.edit_message_reply_markup(call.message.chat.id, call.message.id, reply_markup=None)


    # ─────────────────────────── вспомогательные функции ───────────────────────────
    def _find_draft(user_id: int):
        for did, d in EQUIP_DRAFTS.items():
            if d["user_id"] == user_id:
                return did, d
        raise ValueError("draft not found")

    def _draft_step(user_id: int):
        try:
            return _find_draft(user_id)[1]["step"]
        except ValueError:
            return None

    async def _update_status(eq: Equipment, status: EquipmentStatus, courier_id: int | None):
        async with AsyncSessionLocal() as sess:
            if courier_id is not None and not await sess.get(User, courier_id):
                sess.add(User(id=courier_id, name=""))
                await sess.flush()

            eq.status      = status
            eq.assigned_to = courier_id
            sess.add(eq)
            await sess.commit()

    async def _save_repair_request(draft: dict, photo_id: str | None):
        async with AsyncSessionLocal() as sess:
            user_id = draft["user_id"]
            if not await sess.get(User, user_id):
                sess.add(User(id=user_id, name=""))
                await sess.flush()
            sess.add(Request(
                user_id=user_id,
                category="Ремонт оборудования",
                subcategory=draft["eq_id"],
                title=f"Ремонт {draft['eq_id']}",
                description=draft["issue_desc"],
                priority="средний",
                photos=[photo_id] if photo_id else [],
                status=RequestStatus.OPEN,
                created_at=datetime.utcnow()
            ))
            await sess.commit()

    PER_PAGE = 10
    STATUS_ICON = {
        EquipmentStatus.IN_STOCK:      "🟢",
        EquipmentStatus.WITH_COURIER:  "🚴",
        EquipmentStatus.NEED_REPAIR:   "🛠️",
    }

    def _build_equipment_keyboard(page: int, total_pages: int):
        kb = types.InlineKeyboardMarkup()
        nav = []
        if page > 0:
            nav.append(types.InlineKeyboardButton("◀️", callback_data=f"eq_list:{page-1}"))
        if page + 1 < total_pages:
            nav.append(types.InlineKeyboardButton("▶️", callback_data=f"eq_list:{page+1}"))
        if nav:
            kb.row(*nav)
        kb.add(types.InlineKeyboardButton("❌ Закрыть", callback_data="eq_close"))
        return kb

    @bot.message_handler(func=lambda m: m.text == "Просмотр ТС на складе")
    async def show_equipment(msg: types.Message):
        await _send_equipment_page(msg.chat.id, msg.message_id, 0)

    @bot.callback_query_handler(lambda c: c.data.startswith("eq_list:"))
    async def paginate_equipment(call: types.CallbackQuery):
        page = int(call.data.split(":", 1)[1])
        await bot.answer_callback_query(call.id)
        await _send_equipment_page(call.message.chat.id, call.message.id, page, edit=True)

    @bot.callback_query_handler(lambda c: c.data == "eq_close")
    async def close_equipment_view(call: types.CallbackQuery):
        await bot.answer_callback_query(call.id)
        await bot.edit_message_reply_markup(call.message.chat.id, call.message.id, reply_markup=None)

    async def _send_equipment_page(chat_id: int, message_id: int, page: int, edit: bool = False):
        async with AsyncSessionLocal() as sess:
            items = (await sess.execute(select(Equipment))).scalars().all()

        total_pages = max(1, (len(items) + PER_PAGE - 1) // PER_PAGE)
        page = max(0, min(page, total_pages - 1))
        start, end = page * PER_PAGE, (page + 1) * PER_PAGE

        lines = []
        for eq in items[start:end]:
            icon = STATUS_ICON[eq.status]
            if eq.status == EquipmentStatus.WITH_COURIER and eq.assigned_to:
                status_txt = f"У курьера #{eq.assigned_to}"
            elif eq.status == EquipmentStatus.NEED_REPAIR:
                status_txt = "Нужен ремонт"
            else:
                status_txt = "На складе"
            lines.append(f"{icon} *{eq.eq_id}* — {status_txt}")

        text = "\n".join(lines) or "Список пуст."
        text = f"*Оборудование (стр. {page+1}/{total_pages})*\n\n{text}"

        kb = _build_equipment_keyboard(page, total_pages)

        if edit:
            await bot.edit_message_text(
                text, chat_id, message_id, reply_markup=kb, parse_mode="Markdown"
            )
        else:
            await bot.send_message(chat_id, text, reply_markup=kb, parse_mode="Markdown")