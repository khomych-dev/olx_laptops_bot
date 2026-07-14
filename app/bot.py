import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot, Dispatcher, Router, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings
from app.database import init_db

bot = Bot(token=settings.bot_token)
dp = Dispatcher()
router = Router()


class AccessMiddleware(BaseMiddleware):
    """Blocks access for all users whose ID is not listed in .env"""

    async def __call__(
        self,
        handler: Callable[[types.TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: types.TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        # If the list is empty or the user is not in it — ignore
        if user and user.id not in settings.allowed_users:
            return
        return await handler(event, data)


def get_main_kb() -> InlineKeyboardMarkup:
    """Generates the main menu keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚙️ Налаштувати фільтр", callback_data="main_setup"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📋 Поточні налаштування", callback_data="main_current"
                )
            ],
            [InlineKeyboardButton(text="🟢 Запустити", callback_data="main_toggle")],
            [
                InlineKeyboardButton(
                    text="🗑 Очистити історію", callback_data="main_clear"
                )
            ],
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    """Command Handler /start."""
    await message.answer(
        "Бажаю Здоров'я, пане Сергію! Я бот для моніторингу OLX.\n"
        "Статус: 🔴 Зупинено\n\n"
        "Оберіть дію нижче:",
        reply_markup=get_main_kb(),
    )


async def main():
    # Initialize database on startup
    await init_db()

    # Register access control for messages and button clicks
    router.message.middleware(AccessMiddleware())
    router.callback_query.middleware(AccessMiddleware())

    dp.include_router(router)

    # Skip old updates and start polling
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
