import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext

from app.states import FilterSetup
from app.keyboards import get_multi_select_kb
from app.config import settings
from app.database import (
    clear_history,
    get_all_filters,
    get_user_status,
    init_db,
    set_user_status,
)

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
        if user and user.id not in settings.allowed_users:
            return
        return await handler(event, data)


def get_main_kb(is_active: bool = False) -> InlineKeyboardMarkup:
    """Generates the main menu keyboard. The button text changes depending on the status."""
    toggle_btn = InlineKeyboardButton(
        text="🔴 Зупинити" if is_active else "🟢 Запустити",
        callback_data="main_toggle",
    )
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
            [toggle_btn],
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
    is_active = await get_user_status(message.from_user.id)
    status_text = "🟢 Шукаю кожні 20 хв" if is_active else "🔴 Зупинено"

    await message.answer(
        f"Бажаю здоров'я, пане Сергію! Я бот для моніторингу OLX.\nСтатус: {status_text}\n\nОберіть дію нижче:",
        reply_markup=get_main_kb(is_active),
    )


@router.callback_query(F.data == "main_toggle")
async def process_toggle(callback: types.CallbackQuery):
    """Turns monitoring on or off."""
    user_id = callback.from_user.id
    current_status = await get_user_status(user_id)
    new_status = not current_status

    await set_user_status(user_id, new_status)
    status_text = "🟢 Шукаю кожні 20 хв" if new_status else "🔴 Зупинено"

    # Оновлюємо повідомлення з новими кнопками
    await callback.message.edit_text(
        f"Статус моніторингу змінено.\nПоточний статус: {status_text}",
        reply_markup=get_main_kb(new_status),
    )
    await callback.answer()


@router.callback_query(F.data == "main_current")
async def process_current_settings(callback: types.CallbackQuery):
    """Shows the current saved filters."""
    user_id = callback.from_user.id
    filters = await get_all_filters(user_id)

    if not filters:
        text = "Фільтри не задані. Зараз я не маю конкретних параметрів для пошуку."
    else:
        text = "Ваші поточні налаштування:\n\n"
        for category, data in filters.items():
            text += f"📁 Категорія: {category}\n"
            for key, value in data.items():
                # If it's a list (multi-select), join it with commas
                display_value = ", ".join(value) if isinstance(value, list) else value
                text += f"  - {key}: {display_value}\n"
            text += "\n"

    await callback.message.answer(text)
    await callback.answer()


@router.callback_query(F.data == "main_clear")
async def process_clear_history(callback: types.CallbackQuery):
    """Clears the history of sent ads."""
    await clear_history(callback.from_user.id)
    # show_alert=True displays a pop-up window in the center of the screen
    await callback.answer("Історію успішно очищено!", show_alert=True)


@router.callback_query(F.data == "main_setup")
async def process_setup(callback: types.CallbackQuery, state: FSMContext):
    """Starting filter setup. Step 1: Category selection."""
    # Stopping monitoring to avoid conflicts during setup
    await set_user_status(callback.from_user.id, False)

    # Keyboard for category selection
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💻 Ноутбук", callback_data="cat_laptop")],
            [InlineKeyboardButton(text="📱 Телефон", callback_data="cat_phone")],
            [InlineKeyboardButton(text="💊 Планшет", callback_data="cat_tablet")],
            [InlineKeyboardButton(text="❌ Скасувати", callback_data="setup_cancel")],
        ]
    )

    # Setting the state "category selection"
    await state.set_state(FilterSetup.category)

    await callback.message.edit_text(
        "Моніторинг тимчасово зупинено для налаштування.\n\n"
        "Оберіть категорію, для якої хочете налаштувати фільтр:",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data == "setup_cancel")
async def cancel_setup(callback: types.CallbackQuery, state: FSMContext):
    """Cancel the setting and return to the main menu."""
    await state.clear()

    is_active = await get_user_status(callback.from_user.id)
    status_text = "🟢 Шукаю кожні 20 хв" if is_active else "🔴 Зупинено"

    await callback.message.edit_text(
        f"Налаштування скасовано.\nСтатус: {status_text}\n\nОберіть дію нижче:",
        reply_markup=get_main_kb(is_active),
    )
    await callback.answer()


# Basic brand lists for various categories
BRANDS_LAPTOP = ["Apple", "Asus", "Acer", "HP", "Lenovo", "Dell", "MSI", "Huawei"]
BRANDS_MOBILE = [
    "Apple",
    "Samsung",
    "Xiaomi",
    "Motorola",
    "Google",
    "OnePlus",
    "Huawei",
    "Oppo",
    "Realme",
    "Vivo",
    "Honor",
    "Meizu",
]
BRANDS_TABLET = [
    "Apple",
    "Samsung",
    "Xiaomi",
    "Lenovo",
    "Acer",
    "ASUS",
    "Microsoft",
    "HONOR",
    "Realme",
    "Vivo",
    "Huawei",
    "Meizu",
]


@router.callback_query(FilterSetup.category, F.data.startswith("cat_"))
async def process_category(callback: types.CallbackQuery, state: FSMContext):
    """Saves the category and proceeds to brand selection."""
    category_map = {
        "cat_laptop": "Ноутбук",
        "cat_phone": "Телефон",
        "cat_tablet": "Планшет",
    }
    selected_category = category_map[callback.data]

    # Determines the list of brands depending on the category
    if selected_category == "Ноутбук":
        brands_list = BRANDS_LAPTOP
    elif selected_category == "Телефон":
        brands_list = BRANDS_MOBILE
    else:
        brands_list = BRANDS_TABLET

    # Saves data in FSM
    await state.update_data(
        category=selected_category,
        available_brands=brands_list,  # saves the list for the keyboard
        selected_brands=[],  # will save the selected ones here
    )

    # Switching the state to brand selection
    await state.set_state(FilterSetup.brand)

    kb = get_multi_select_kb(options=brands_list, selected=[], action_prefix="brand")

    await callback.message.edit_text(
        f"Категорія: {selected_category}\n\n"
        "Крок 1: Бренд\n"
        "Оберіть один або кілька брендів зі списку нижче. "
        "Також ви можете просто написати назву бренду в чат.",
        reply_markup=kb,
    )
    await callback.answer()


async def main():
    await init_db()
    router.message.middleware(AccessMiddleware())
    router.callback_query.middleware(AccessMiddleware())
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
