import json
import aiosqlite

DB_NAME = "bot_data.sqlite3"


async def init_db():
    """Initialization of the database and creation of tables."""
    async with aiosqlite.connect(DB_NAME) as db:
        # User Table: Monitoring Enabled/Disabled
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                is_active BOOLEAN DEFAULT 0
            )
        """)

        # Filter Table: Stores JSON as different categories have different fields
        await db.execute("""
            CREATE TABLE IF NOT EXISTS filters (
                user_id INTEGER,
                category TEXT,
                filter_data TEXT,
                PRIMARY KEY (user_id, category)
            )
        """)

        # History Table: Records which ads have already been sent to the user
        await db.execute("""
            CREATE TABLE IF NOT EXISTS history (
                user_id INTEGER,
                ad_id TEXT,
                PRIMARY KEY (user_id, ad_id)
            )
        """)
        await db.commit()


async def get_user_status(user_id: int) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT is_active FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return bool(row[0]) if row else False


async def set_user_status(user_id: int, is_active: bool):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO users (user_id, is_active) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET is_active = ?",
            (user_id, is_active, is_active),
        )
        await db.commit()


async def save_filter(user_id: int, category: str, filter_data: dict):
    """Saves or updates the user's filters for a specific category."""
    async with aiosqlite.connect(DB_NAME) as db:
        data_json = json.dumps(filter_data, ensure_ascii=False)
        await db.execute(
            """
            INSERT INTO filters (user_id, category, filter_data) 
            VALUES (?, ?, ?) 
            ON CONFLICT(user_id, category) 
            DO UPDATE SET filter_data = ?
            """,
            (user_id, category, data_json, data_json),
        )
        await db.commit()


async def get_all_filters(user_id: int) -> dict:
    """Returns all saved user filters for all categories."""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT category, filter_data FROM filters WHERE user_id = ?", (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return {row[0]: json.loads(row[1]) for row in rows}


async def add_to_history(user_id: int, ad_id: str):
    """Adds the ad ID to the history to avoid sending it again."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR IGNORE INTO history (user_id, ad_id) VALUES (?, ?)",
            (user_id, ad_id),
        )
        await db.commit()


async def is_in_history(user_id: int, ad_id: str) -> bool:
    """Checks if this ad has already been sent to the user."""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT 1 FROM history WHERE user_id = ? AND ad_id = ?", (user_id, ad_id)
        ) as cursor:
            return await cursor.fetchone() is not None


async def clear_history(user_id: int):
    """Clears the history of sent ads for the user."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM history WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_active_users() -> list[int]:
    """Returns a list of user IDs for whom monitoring is enabled."""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT user_id FROM users WHERE is_active = 1"
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]
