import os
import logging
from uuid import uuid4
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MANAGER_CHAT_ID = int(os.getenv("MANAGER_CHAT_ID"))

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

SERVICES = [
    "Баня до 4х Гостей",
    "Баня до 6 Гостей",
    "Купель-Фурако",
    "Чан",
    "Обряд тишины",
]

# {order_id: {user_id, service, status, user_name, username}}
orders: dict = {}

# {chat_id: {"order_id": str, "role": "manager" | "guest"}}
waiting_for_reply: dict = {}


def manager_keyboard(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm:{order_id}"),
            InlineKeyboardButton("❌ Отказать", callback_data=f"reject:{order_id}"),
        ],
        [InlineKeyboardButton("💬 Задать вопрос", callback_data=f"ask:{order_id}")],
    ])


def guest_keyboard(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Задать вопрос менеджеру", callback_data=f"guest_ask:{order_id}")]
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton(service, callback_data=f"order:{service}")]
        for service in SERVICES
    ]
    await update.message.reply_text(
        "🏕 Добро пожаловать в глэмпинг!\n\nВыберите услугу для заказа:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    service = query.data.split(":", 1)[1]
    user = query.from_user
    order_id = str(uuid4())[:8].upper()

    orders[order_id] = {
        "user_id": user.id,
        "service": service,
        "status": "pending",
        "user_name": user.full_name,
        "username": f"@{user.username}" if user.username else user.full_name,
    }

    await query.edit_message_text(
        f"✅ Заявка №{order_id} на «{service}» отправлена.\n"
        "Ожидайте подтверждения менеджера.",
        reply_markup=guest_keyboard(order_id),
    )

    order = orders[order_id]
    await context.bot.send_message(
        chat_id=MANAGER_CHAT_ID,
        text=(
            f"🔔 Новая заявка №{order_id}\n"
            f"Услуга: {service}\n"
            f"Гость: {order['user_name']} ({order['username']})"
        ),
        reply_markup=manager_keyboard(order_id),
    )


async def handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    order_id = query.data.split(":", 1)[1]
    order = orders.get(order_id)
    if not order:
        await query.answer("Заявка не найдена.", show_alert=True)
        return

    orders[order_id]["status"] = "confirmed"

    await query.edit_message_text(
        f"✅ Заявка №{order_id} — ПОДТВЕРЖДЕНА\n"
        f"Услуга: {order['service']}\n"
        f"Гость: {order['user_name']} ({order['username']})",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Задать вопрос", callback_data=f"ask:{order_id}")]
        ]),
    )

    await context.bot.send_message(
        chat_id=order["user_id"],
        text=f"✅ Ваш заказ «{order['service']}» подтверждён!\nЖдём вас в глэмпинге 🏕",
        reply_markup=guest_keyboard(order_id),
    )


async def handle_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    order_id = query.data.split(":", 1)[1]
    order = orders.get(order_id)
    if not order:
        await query.answer("Заявка не найдена.", show_alert=True)
        return

    orders[order_id]["status"] = "rejected"

    await query.edit_message_text(
        f"❌ Заявка №{order_id} — ОТКЛОНЕНА\n"
        f"Услуга: {order['service']}\n"
        f"Гость: {order['user_name']} ({order['username']})",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Задать вопрос", callback_data=f"ask:{order_id}")]
        ]),
    )

    await context.bot.send_message(
        chat_id=order["user_id"],
        text=f"❌ Заказ на «{order['service']}» отклонён.\nЕсли есть вопросы — напишите менеджеру.",
        reply_markup=guest_keyboard(order_id),
    )


async def handle_manager_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    order_id = query.data.split(":", 1)[1]
    if order_id not in orders:
        return

    waiting_for_reply[MANAGER_CHAT_ID] = {"order_id": order_id, "role": "manager"}

    await context.bot.send_message(
        chat_id=MANAGER_CHAT_ID,
        text=f"Введите вопрос для гостя по заявке №{order_id}:",
    )


async def handle_guest_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    order_id = query.data.split(":", 1)[1]
    order = orders.get(order_id)
    if not order:
        return

    waiting_for_reply[order["user_id"]] = {"order_id": order_id, "role": "guest"}

    await context.bot.send_message(
        chat_id=order["user_id"],
        text=f"Введите ваш вопрос менеджеру по заявке №{order_id}:",
    )


async def handle_guest_reply_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    order_id = query.data.split(":", 1)[1]
    order = orders.get(order_id)
    if not order:
        return

    waiting_for_reply[order["user_id"]] = {"order_id": order_id, "role": "guest"}

    await context.bot.send_message(
        chat_id=order["user_id"],
        text="Введите ваш ответ:",
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    text = update.message.text

    if user_id not in waiting_for_reply:
        if user_id == MANAGER_CHAT_ID:
            await update.message.reply_text("Управляйте заявками через кнопки.")
        else:
            await update.message.reply_text("Используйте /start для выбора услуги.")
        return

    info = waiting_for_reply.pop(user_id)
    order_id = info["order_id"]
    role = info["role"]
    order = orders.get(order_id)

    if not order:
        await update.message.reply_text("Заявка не найдена.")
        return

    if role == "manager":
        await context.bot.send_message(
            chat_id=order["user_id"],
            text=f"❓ Вопрос менеджера по заявке №{order_id}:\n\n{text}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 Ответить", callback_data=f"reply:{order_id}")]
            ]),
        )
        await update.message.reply_text("✉️ Вопрос отправлен гостю.")

    elif role == "guest":
        await context.bot.send_message(
            chat_id=MANAGER_CHAT_ID,
            text=(
                f"💬 Сообщение от гостя по заявке №{order_id}:\n\n{text}\n\n"
                f"({order['user_name']} {order['username']})"
            ),
            reply_markup=manager_keyboard(order_id),
        )
        await update.message.reply_text("✉️ Сообщение отправлено менеджеру.")


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_order, pattern=r"^order:"))
    app.add_handler(CallbackQueryHandler(handle_confirm, pattern=r"^confirm:"))
    app.add_handler(CallbackQueryHandler(handle_reject, pattern=r"^reject:"))
    app.add_handler(CallbackQueryHandler(handle_manager_ask, pattern=r"^ask:"))
    app.add_handler(CallbackQueryHandler(handle_guest_ask, pattern=r"^guest_ask:"))
    app.add_handler(CallbackQueryHandler(handle_guest_reply_button, pattern=r"^reply:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()
