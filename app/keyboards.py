from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_multi_select_kb(
    options: list[str], selected: list[str], action_prefix: str, allow_skip: bool = True
) -> InlineKeyboardMarkup:
    """
    Generates a multi-select keyboard (with checkboxes).
    :param options: List of all available options
    :param selected: List of already selected options
    :param action_prefix: Prefix for callback_data (e.g., 'brand')
    :param allow_skip: Whether to show the 'Skip' button
    """
    keyboard = []

    for opt in options:
        text = f"✅ {opt}" if opt in selected else opt
        # We pass an index instead of text to stay within the 64-byte limit for `callback_data`
        idx = options.index(opt)
        cb_data = f"{action_prefix}_{idx}"
        keyboard.append([InlineKeyboardButton(text=text, callback_data=cb_data)])

    # Navigation buttons
    nav_buttons = []
    if selected:
        # If at least one item is selected, the "Next" button appears
        nav_buttons.append(
            InlineKeyboardButton(text="➡️ Далі", callback_data=f"{action_prefix}_next")
        )

    if allow_skip:
        nav_buttons.append(
            InlineKeyboardButton(
                text="⏭ Пропустити", callback_data=f"{action_prefix}_skip"
            )
        )

    if nav_buttons:
        keyboard.append(nav_buttons)

    return InlineKeyboardMarkup(inline_keyboard=keyboard)
