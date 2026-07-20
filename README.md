# 🛒 OLX Tech Parser (Telegram Bot)

A powerful and flexible Telegram bot for automatic monitoring of new tech listings (laptops, smartphones, tablets) on OLX.ua.

## 🌟 Key Features

- **Multi-category Monitoring**: Supports searching across "Laptops", "Phones", and "Tablets" categories.
- **Detailed Filtering**: Configurable filters for brand, model, CPU, memory (RAM and Storage), screen size, condition, and price.
- **Bypass Protection**: Uses the `curl_cffi` library to successfully execute requests to the OLX API, bypassing Cloudflare protection.
- **Local Filtering**: Intelligent parsing of descriptions and titles for exact matches to specified parameters ("smart" keyword search).
- **Periodic Checks**: Integrated with `apscheduler` to automatically check for new listings (every 20 minutes by default).
- **User-friendly Management**: Interactive In-line menu (with multi-select checkbox support) to configure the bot directly in Telegram.

## 🛠 Technologies

- **Python 3.12+**
- **aiogram 3.x**: For asynchronous interaction with the Telegram API.
- **aiosqlite**: For local storage of filters and monitoring statuses in an SQLite database.
- **curl-cffi**: For browser impersonation during API requests (`impersonate="chrome120"`).
- **APScheduler**: For scheduling background tasks (monitoring).
- **Docker & Docker Compose**: For quick and easy deployment.

## 🚀 Installation and Setup

The bot can be easily deployed using Docker.

### Step 1. Clone the repository
```bash
git clone https://github.com/khomych-dev/olx_laptops_bot.git
cd olx_laptops_bot
```

### Step 2. Configure environment variables
Copy the example configuration file and fill it out:
```bash
cp .env.example .env
```
Open the `.env` file and specify:
- `BOT_TOKEN` — your bot token (obtain it from [@BotFather](https://t.me/BotFather))
- `ALLOWED_USERS` — a comma-separated list of Telegram user IDs authorized to use the bot (e.g., `123456789,987654321`)

### Step 3. Run with Docker
```bash
docker compose up -d --build
```
After this, the bot will start automatically, and the SQLite database will be stored in a Docker volume to persist data across container restarts.

### Alternative Run (Locally via `uv` or `pip`)
If you prefer not to use Docker, you can run the bot locally:
```bash
# Install dependencies (recommended via uv)
uv sync

# Or using standard pip
# pip install aiogram aiosqlite apscheduler beautifulsoup4 curl-cffi pydantic-settings

# Run the bot
python main.py
```

## ⚙️ Usage
1. Find your bot in Telegram and click **Start** (or send the `/start` command).
2. Open the menu via the keyboard button or the `/menu` command.
3. Select **"⚙️ Налаштувати фільтр" (Setup filter)** and complete all the steps (Category -> Brand -> Model -> Memory -> Condition, etc.).
4. Turn on monitoring by clicking **"🟢 Запустити" (Start)**.
5. The bot will now automatically send you new listings that match your filters!

## 📝 Search Notes
- When searching for tablets, the bot searches for the keyword "Планшет" across all tablet categories and then filters the relevant results. This is because OLX splits tablets into separate subcategories by brand.
- Make sure your Telegram ID is added to `ALLOWED_USERS`, otherwise the bot will ignore your messages.
