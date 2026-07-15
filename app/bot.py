import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext

from app.states import FilterSetup
from app.keyboards import get_multi_select_kb, get_skip_kb
from app.config import settings
from app.database import (
    clear_history,
    get_all_filters,
    get_user_status,
    init_db,
    set_user_status,
    save_filter,
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


@router.callback_query(FilterSetup.brand, F.data.startswith("brand_"))
async def process_brand_selection(callback: types.CallbackQuery, state: FSMContext):
    """Processing clicks on the brand selection keyboard."""
    action = callback.data.split("_")[1]
    data = await state.get_data()

    # If "Skip" or "Next" was pressed -> proceed to Model selection
    if action in ("skip", "next"):
        if action == "skip":
            await state.update_data(selected_brands=[])

        await state.set_state(FilterSetup.model)

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⏭ Пропустити", callback_data="model_skip")]
            ]
        )
        await callback.message.edit_text(
            "Крок 2: Модель\n\n"
            "Напишіть у чат назву моделі (наприклад: 'ProBook', 'S24 Ultra' або 'Air').\n"
            "Якщо модель не важлива, натисніть [Пропустити].",
            reply_markup=kb,
        )
        await callback.answer()
        return

    # If a specific brand was clicked (set/remove the checkbox)
    idx = int(action)
    available_brands = data.get("available_brands", [])
    selected_brands = data.get("selected_brands", [])

    selected_brand = available_brands[idx]
    if selected_brand in selected_brands:
        selected_brands.remove(selected_brand)
    else:
        selected_brands.append(selected_brand)

    await state.update_data(selected_brands=selected_brands)

    kb = get_multi_select_kb(
        options=available_brands, selected=selected_brands, action_prefix="brand"
    )
    # Updating the keyboard under the message
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


@router.message(FilterSetup.brand)
async def process_brand_text(message: types.Message, state: FSMContext):
    """Processing brand input text (if the user typed it manually)."""
    data = await state.get_data()
    selected_brands = data.get("selected_brands", [])
    available_brands = data.get("available_brands", [])

    new_brand = message.text.strip()

    # Adding a new brand to the lists if it's not there yet
    if new_brand not in available_brands:
        available_brands.append(new_brand)
        await state.update_data(available_brands=available_brands)

    if new_brand not in selected_brands:
        selected_brands.append(new_brand)
        await state.update_data(selected_brands=selected_brands)

    kb = get_multi_select_kb(
        options=available_brands, selected=selected_brands, action_prefix="brand"
    )

    await message.answer(
        f"Бренд '{new_brand}' додано! Оберіть ще зі списку або натисніть [Далі]:",
        reply_markup=kb,
    )


@router.callback_query(FilterSetup.model, F.data == "model_skip")
async def skip_model(callback: types.CallbackQuery, state: FSMContext):
    """Processing the skipping of the model input."""
    await state.update_data(model=None)
    await state.set_state(FilterSetup.price_from)

    await callback.message.edit_text(
        "Крок 3: Мінімальна ціна (від)\n\n"
        "Введіть мінімальну ціну в гривнях (тільки цифри) або натисніть [Пропустити].",
        reply_markup=get_skip_kb("price_from_skip"),
    )
    await callback.answer()


@router.message(FilterSetup.model)
async def process_model_text(message: types.Message, state: FSMContext):
    """Processing text input of the model."""
    model_name = message.text.strip()
    await state.update_data(model=model_name)
    await state.set_state(FilterSetup.price_from)

    await message.answer(
        f"✅ Модель '{model_name}' збережено.\n\n"
        "Крок 3: Мінімальна ціна (від)\n\n"
        "Введіть мінімальну ціну в гривнях (тільки цифри) або натисніть [Пропустити].",
        reply_markup=get_skip_kb("price_from_skip"),
    )


# Base lists for diagonals
DIAG_LAPTOP = ['До 13"', '13"-14"', '15"-15.6"', '16" і більше']
DIAG_MOBILE = ['До 5"', '5"-6"', '6"-6.5"', '6.5" і більше']
DIAG_TABLET = ['До 8"', '8"-10"', '10"-12"', '12" і більше']


@router.callback_query(FilterSetup.price_from, F.data == "price_from_skip")
async def skip_price_from(callback: types.CallbackQuery, state: FSMContext):
    """Processing the skipping of the minimum price input."""
    await state.update_data(price_from=None)
    await state.set_state(FilterSetup.price_to)
    await callback.message.edit_text(
        "Крок 4: Максимальна ціна (до)\n\n"
        "Введіть максимальну ціну в гривнях (тільки цифри) або натисніть [Пропустити].",
        reply_markup=get_skip_kb("price_to_skip"),
    )
    await callback.answer()


@router.message(FilterSetup.price_from)
async def process_price_from_text(message: types.Message, state: FSMContext):
    """Processing text input of the minimum price."""
    price_text = message.text.strip()

    if not price_text.isdigit():
        await message.answer(
            "Помилка: ціна має складатися тільки з цифр (без пробілів чи літер).\n"
            "Будь ласка, введіть число (наприклад: 15000) або натисніть [Пропустити].",
            reply_markup=get_skip_kb("price_from_skip"),
        )
        return

    await state.update_data(price_from=int(price_text))
    await state.set_state(FilterSetup.price_to)
    await message.answer(
        f"✅ Мінімальна ціна: {price_text} грн.\n\n"
        "Крок 4: Максимальна ціна (до)\n\n"
        "Введіть максимальну ціну в гривнях (тільки цифри) або натисніть [Пропустити].",
        reply_markup=get_skip_kb("price_to_skip"),
    )


async def transition_to_diagonal(message_or_callback, state: FSMContext):
    """Helper function to transition to diagonal selection (to avoid code duplication)."""
    data = await state.get_data()
    category = data.get("category")

    if category == "Ноутбук":
        diag_list = DIAG_LAPTOP
    elif category == "Телефон":
        diag_list = DIAG_MOBILE
    else:
        diag_list = DIAG_TABLET

    await state.update_data(available_diagonals=diag_list, selected_diagonals=[])
    await state.set_state(FilterSetup.diagonal)

    kb = get_multi_select_kb(options=diag_list, selected=[], action_prefix="diag")

    text = "Крок 5: Діагональ екрана\n\nОберіть один або кілька варіантів:"

    if isinstance(message_or_callback, types.CallbackQuery):
        await message_or_callback.message.edit_text(text, reply_markup=kb)
    else:
        await message_or_callback.answer(text, reply_markup=kb)


@router.callback_query(FilterSetup.price_to, F.data == "price_to_skip")
async def skip_price_to(callback: types.CallbackQuery, state: FSMContext):
    """Processing the skipping of the maximum price input."""
    await state.update_data(price_to=None)
    await transition_to_diagonal(callback, state)
    await callback.answer()


@router.message(FilterSetup.price_to)
async def process_price_to_text(message: types.Message, state: FSMContext):
    """Processing text input of the maximum price."""
    price_text = message.text.strip()

    if not price_text.isdigit():
        await message.answer(
            "Помилка: ціна має складатися тільки з цифр.\n"
            "Будь ласка, введіть число (наприклад: 25000) або натисніть [Пропустити].",
            reply_markup=get_skip_kb("price_to_skip"),
        )
        return

    await state.update_data(price_to=int(price_text))
    await transition_to_diagonal(message, state)


# Base lists for specific filters
CPU_LIST = [
    "Intel Core i3",
    "Intel Core i5",
    "Intel Core i7/i9",
    "AMD Ryzen 3",
    "AMD Ryzen 5",
    "AMD Ryzen 7/9",
    "Apple M-серія",
]
STORAGE_LIST = ["до 32 ГБ", "64 ГБ", "128 ГБ", "256 ГБ", "512 ГБ", "1 ТБ і більше"]


@router.callback_query(FilterSetup.diagonal, F.data.startswith("diag_"))
async def process_diagonal_selection(callback: types.CallbackQuery, state: FSMContext):
    """Handling keystrokes for selecting a diagonal and branching the path."""
    action = callback.data.split("_")[1]
    data = await state.get_data()

    # If you clicked “Skip” or “Next” -> proceed to the next step
    if action in ("skip", "next"):
        if action == "skip":
            await state.update_data(selected_diagonals=[])

        category = data.get("category")

        if category == "Ноутбук":
            # Path for laptops: Processor
            await state.update_data(available_cpus=CPU_LIST, selected_cpus=[])
            await state.set_state(FilterSetup.cpu)
            kb = get_multi_select_kb(options=CPU_LIST, selected=[], action_prefix="cpu")
            text = "Крок 6: Процесор\n\nОберіть один або кілька варіантів:"
        else:
            # Path for phones/tablets: Built-in memory
            await state.update_data(
                available_storages=STORAGE_LIST, selected_storages=[]
            )
            await state.set_state(FilterSetup.storage)
            kb = get_multi_select_kb(
                options=STORAGE_LIST, selected=[], action_prefix="storage"
            )
            text = "Крок 6: Вбудована пам'ять (Storage)\n\nОберіть один або кілька варіантів:"

        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()
        return

    # Processing the selection/cancellation of a checkbox
    idx = int(action)
    available_diagonals = data.get("available_diagonals", [])
    selected_diagonals = data.get("selected_diagonals", [])

    selected_diag = available_diagonals[idx]
    if selected_diag in selected_diagonals:
        selected_diagonals.remove(selected_diag)
    else:
        selected_diagonals.append(selected_diag)

    await state.update_data(selected_diagonals=selected_diagonals)

    kb = get_multi_select_kb(
        options=available_diagonals, selected=selected_diagonals, action_prefix="diag"
    )
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


OS_LIST = ["Android", "iOS", "HarmonyOS", "Windows"]
RAM_LIST = ["до 4 ГБ", "6 ГБ", "8 ГБ", "12 ГБ", "16 ГБ", "32+ ГБ"]


async def transition_to_ram(callback: types.CallbackQuery, state: FSMContext):
    """A joint transition to selecting the main program after the branches."""
    await state.update_data(available_rams=RAM_LIST, selected_rams=[])
    await state.set_state(FilterSetup.ram)

    kb = get_multi_select_kb(options=RAM_LIST, selected=[], action_prefix="ram")
    await callback.message.edit_text(
        "Фільтр: Оперативна пам'ять (ОЗП)\n\nОберіть один або кілька варіантів:",
        reply_markup=kb,
    )
    await callback.answer()


# --- PROCESSOR PERFORMANCE (Laptops) ---
@router.callback_query(FilterSetup.cpu, F.data.startswith("cpu_"))
async def process_cpu_selection(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split("_")[1]
    data = await state.get_data()

    if action in ("skip", "next"):
        if action == "skip":
            await state.update_data(selected_cpus=[])
        await transition_to_ram(callback, state)
        return

    idx = int(action)
    available_cpus = data.get("available_cpus", [])
    selected_cpus = data.get("selected_cpus", [])

    selected = available_cpus[idx]
    if selected in selected_cpus:
        selected_cpus.remove(selected)
    else:
        selected_cpus.append(selected)

    await state.update_data(selected_cpus=selected_cpus)
    kb = get_multi_select_kb(
        options=available_cpus, selected=selected_cpus, action_prefix="cpu"
    )
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


# --- PROCESSING BUILT-IN MEMORY (Phones/Tablets) ---
@router.callback_query(FilterSetup.storage, F.data.startswith("storage_"))
async def process_storage_selection(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split("_")[1]
    data = await state.get_data()

    if action in ("skip", "next"):
        if action == "skip":
            await state.update_data(selected_storages=[])

        # After built-in memory, we go to the Operating System
        await state.update_data(available_os=OS_LIST, selected_os=[])
        await state.set_state(FilterSetup.os_type)
        kb = get_multi_select_kb(options=OS_LIST, selected=[], action_prefix="os")

        await callback.message.edit_text(
            "Фільтр: Операційна система\n\nОберіть один або кілька варіантів:",
            reply_markup=kb,
        )
        await callback.answer()
        return

    idx = int(action)
    available = data.get("available_storages", [])
    selected = data.get("selected_storages", [])

    item = available[idx]
    if item in selected:
        selected.remove(item)
    else:
        selected.append(item)

    await state.update_data(selected_storages=selected)
    kb = get_multi_select_kb(
        options=available, selected=selected, action_prefix="storage"
    )
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


# --- PROCESSING OPERATING SYSTEM (Phones/Tablets) ---
@router.callback_query(FilterSetup.os_type, F.data.startswith("os_"))
async def process_os_selection(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split("_")[1]
    data = await state.get_data()

    if action in ("skip", "next"):
        if action == "skip":
            await state.update_data(selected_os=[])
        # We bring the path back to RAM
        await transition_to_ram(callback, state)
        return

    idx = int(action)
    available = data.get("available_os", [])
    selected = data.get("selected_os", [])

    item = available[idx]
    if item in selected:
        selected.remove(item)
    else:
        selected.append(item)

    await state.update_data(selected_os=selected)
    kb = get_multi_select_kb(options=available, selected=selected, action_prefix="os")
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


CONDITION_LIST = ["Новий", "Вживаний", "На запчастини"]


# --- PROCESSING RAM ---
@router.callback_query(FilterSetup.ram, F.data.startswith("ram_"))
async def process_ram_selection(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split("_")[1]
    data = await state.get_data()

    if action in ("skip", "next"):
        if action == "skip":
            await state.update_data(selected_rams=[])

        await state.update_data(
            available_conditions=CONDITION_LIST, selected_conditions=[]
        )
        await state.set_state(FilterSetup.condition)
        kb = get_multi_select_kb(
            options=CONDITION_LIST, selected=[], action_prefix="cond"
        )

        await callback.message.edit_text(
            "Фільтр: Стан\n\nОберіть один або кілька варіантів:", reply_markup=kb
        )
        await callback.answer()
        return

    idx = int(action)
    available = data.get("available_rams", [])
    selected = data.get("selected_rams", [])

    item = available[idx]
    if item in selected:
        selected.remove(item)
    else:
        selected.append(item)

    await state.update_data(selected_rams=selected)
    kb = get_multi_select_kb(options=available, selected=selected, action_prefix="ram")
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


# --- PROCESSING CONDITION ---
@router.callback_query(FilterSetup.condition, F.data.startswith("cond_"))
async def process_condition_selection(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split("_")[1]
    data = await state.get_data()

    if action in ("skip", "next"):
        if action == "skip":
            await state.update_data(selected_conditions=[])

        await state.set_state(FilterSetup.keywords)
        await callback.message.edit_text(
            "Останній крок: Ключові слова\n\n"
            "Введіть слово, яке обов'язково має бути в назві чи описі "
            "(наприклад: ігровий, гарантія). Якщо це не важливо, натисніть [Пропустити].",
            reply_markup=get_skip_kb("kw_skip"),
        )
        await callback.answer()
        return

    idx = int(action)
    available = data.get("available_conditions", [])
    selected = data.get("selected_conditions", [])

    item = available[idx]
    if item in selected:
        selected.remove(item)
    else:
        selected.append(item)

    await state.update_data(selected_conditions=selected)
    kb = get_multi_select_kb(options=available, selected=selected, action_prefix="cond")
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


# --- CONCLUSION: KEYWORDS AND SAVING ---
async def finish_setup(
    message_or_callback, state: FSMContext, keywords: str | None = None
):
    """Collects all data, clears empty fields, and saves to the database."""
    data = await state.get_data()
    category = data.get("category")
    user_id = message_or_callback.from_user.id

    # Form the final filter dictionary
    filter_data = {}
    if data.get("selected_brands"):
        filter_data["Бренд"] = data["selected_brands"]
    if data.get("model"):
        filter_data["Модель"] = data["model"]
    if data.get("price_from"):
        filter_data["Ціна від"] = data["price_from"]
    if data.get("price_to"):
        filter_data["Ціна до"] = data["price_to"]
    if data.get("selected_diagonals"):
        filter_data["Діагональ"] = data["selected_diagonals"]

    if data.get("selected_cpus"):
        filter_data["Процесор"] = data["selected_cpus"]
    if data.get("selected_storages"):
        filter_data["Пам'ять (вбудована)"] = data["selected_storages"]
    if data.get("selected_os"):
        filter_data["ОС"] = data["selected_os"]

    if data.get("selected_rams"):
        filter_data["ОЗП"] = data["selected_rams"]
    if data.get("selected_conditions"):
        filter_data["Стан"] = data["selected_conditions"]
    if keywords:
        filter_data["Ключові слова"] = keywords

    # Saving to database and clearing state
    await save_filter(user_id, category, filter_data)
    await state.clear()

    is_active = await get_user_status(user_id)
    text = f"✅ Фільтр для категорії '{category}' успішно збережено!\n\nОберіть дію:"

    if isinstance(message_or_callback, types.CallbackQuery):
        await message_or_callback.message.edit_text(
            text, reply_markup=get_main_kb(is_active)
        )
    else:
        await message_or_callback.answer(text, reply_markup=get_main_kb(is_active))


@router.callback_query(FilterSetup.keywords, F.data == "kw_skip")
async def skip_keywords(callback: types.CallbackQuery, state: FSMContext):
    await finish_setup(callback, state)
    await callback.answer()


@router.message(FilterSetup.keywords)
async def process_keywords_text(message: types.Message, state: FSMContext):
    await finish_setup(message, state, keywords=message.text.strip())


async def main():
    await init_db()
    router.message.middleware(AccessMiddleware())
    router.callback_query.middleware(AccessMiddleware())
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
