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
