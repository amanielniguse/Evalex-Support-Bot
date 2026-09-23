import os
import aiosqlite

DB_PATH = os.getenv("DB_PATH", "bot_support.db")

async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True) if os.path.dirname(DB_PATH) else None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_topics (
                user_id INTEGER PRIMARY KEY,
                thread_id INTEGER UNIQUE
            )
        """)
        await db.commit()

async def get_thread_id(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT thread_id FROM user_topics WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def get_user_id(thread_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM user_topics WHERE thread_id = ?", (thread_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def save_mapping(user_id: int, thread_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO user_topics (user_id, thread_id) VALUES (?, ?)",
            (user_id, thread_id)
        )
        await db.commit()
