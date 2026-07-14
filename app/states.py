from aiogram.fsm.state import State, StatesGroup


class FilterSetup(StatesGroup):
    """Options for step-by-step filter configuration."""

    category = State()  # Choice of category (Laptops, Phones, Tablets)
    brand = State()  # Brand (Multi-select)
    model = State()  # Model (Text)
    price_from = State()  # Price FROM (Digits)
    price_to = State()  # Price TO (Digits)
    diagonal = State()  # Diagonal (Multi-select)

    # Specific to laptops
    cpu = State()  # Processor (Multi-select)

    # Specific to phones/tablets
    storage = State()  # Built-in memory (Multi-select)
    os_type = State()  # Operating system (Multi-select)

    # Common
    ram = State()  # RAM (Multi-select)
    condition = State()  # Condition (Multi-select)
    keywords = State()  # Keywords (Text)
