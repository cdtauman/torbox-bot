"""
database.py — שכבת בסיס הנתונים (SQLite אסינכרוני)
מנהל: משתמשים, הגדרות אישיות, היסטוריית חיפוש והורדות.
"""
import json
import time
import aiosqlite

import config


# ───────────────────────── אתחול ─────────────────────────
async def init_db():
    """יוצר את כל הטבלאות אם אינן קיימות, ומגדיר את הבעלים."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                first_name  TEXT,
                role        INTEGER DEFAULT 1,
                joined_at   INTEGER,
                last_active INTEGER,
                settings    TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS downloads (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                name        TEXT,
                size        INTEGER,
                torbox_id   INTEGER,
                hash        TEXT,
                created_at  INTEGER,
                notified    INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS searches (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                query       TEXT,
                results     INTEGER,
                created_at  INTEGER
            )
        """)
        await db.commit()

        # Migrations
        try:
            await db.execute("ALTER TABLE downloads ADD COLUMN notified INTEGER DEFAULT 0")
            await db.commit()
        except Exception:
            pass

        # הגדרת הבעלים אוטומטית
        if config.OWNER_ID:
            await db.execute("""
                INSERT INTO users (user_id, username, first_name, role, joined_at, last_active, settings)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET role=?
            """, (
                config.OWNER_ID, "owner", "Owner", config.ROLE_OWNER,
                int(time.time()), int(time.time()),
                json.dumps(config.DEFAULT_SETTINGS), config.ROLE_OWNER,
            ))
            await db.commit()


# ───────────────────────── משתמשים ─────────────────────────
async def get_user(user_id: int):
    """מחזיר dict עם נתוני המשתמש, או None אם לא קיים."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            user = dict(row)
            try:
                user["settings"] = json.loads(user["settings"]) if user["settings"] else dict(config.DEFAULT_SETTINGS)
            except (json.JSONDecodeError, TypeError):
                user["settings"] = dict(config.DEFAULT_SETTINGS)
            return user


async def register_user(user_id: int, username: str, first_name: str):
    """רושם משתמש חדש כ'ממתין'. אם כבר קיים — לא משנה דבר."""
    existing = await get_user(user_id)
    if existing:
        return existing
    role = config.ROLE_OWNER if user_id == config.OWNER_ID else config.ROLE_PENDING
    now = int(time.time())
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, first_name, role, joined_at, last_active, settings)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, username, first_name, role, now, now, json.dumps(config.DEFAULT_SETTINGS)))
        await db.commit()
    return await get_user(user_id)


async def set_role(user_id: int, role: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE users SET role=? WHERE user_id=?", (role, user_id))
        await db.commit()


async def delete_user(user_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("DELETE FROM users WHERE user_id=?", (user_id,))
        await db.commit()


async def touch_user(user_id: int):
    """מעדכן את זמן הפעילות האחרון."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE users SET last_active=? WHERE user_id=?", (int(time.time()), user_id))
        await db.commit()


async def list_users(role: int = None):
    """רשימת כל המשתמשים, או רק לפי תפקיד מסוים."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if role is not None:
            q = "SELECT * FROM users WHERE role=? ORDER BY joined_at DESC"
            args = (role,)
        else:
            q = "SELECT * FROM users ORDER BY role DESC, joined_at DESC"
            args = ()
        async with db.execute(q, args) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def count_users_by_role():
    """מחזיר dict {role: count}."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        async with db.execute("SELECT role, COUNT(*) FROM users GROUP BY role") as cur:
            return {row[0]: row[1] for row in await cur.fetchall()}


# ───────────────────────── הגדרות ─────────────────────────
async def update_settings(user_id: int, settings: dict):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE users SET settings=? WHERE user_id=?",
                         (json.dumps(settings), user_id))
        await db.commit()


# ───────────────────────── היסטוריה ─────────────────────────
async def log_search(user_id: int, query: str, results: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO searches (user_id, query, results, created_at) VALUES (?, ?, ?, ?)",
            (user_id, query, results, int(time.time())))
        await db.commit()


async def log_download(user_id: int, name: str, size: int, torbox_id, thash: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("""
            INSERT INTO downloads (user_id, name, size, torbox_id, hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, name, size, torbox_id, thash, int(time.time())))
        await db.commit()


async def get_unnotified_downloads():
    """מחזיר את כל ההורדות שעדיין לא קיבלו התראה ב-7 הימים האחרונים."""
    seven_days_ago = int(time.time()) - (7 * 86400)
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM downloads WHERE notified=0 AND torbox_id IS NOT NULL AND created_at > ?",
            (seven_days_ago,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def mark_download_as_notified(download_id: int):
    """מסמן הורדה ככזו שנשלחה עבורה התראה."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE downloads SET notified=1 WHERE id=?", (download_id,))
        await db.commit()


async def get_stats():
    """סטטיסטיקות כלליות לפאנל אדמין."""
    day_ago = int(time.time()) - 86400
    async with aiosqlite.connect(config.DB_PATH) as db:
        async def scalar(q, args=()):
            async with db.execute(q, args) as cur:
                row = await cur.fetchone()
                return row[0] if row and row[0] is not None else 0

        return {
            "downloads_today": await scalar("SELECT COUNT(*) FROM downloads WHERE created_at>?", (day_ago,)),
            "searches_today": await scalar("SELECT COUNT(*) FROM searches WHERE created_at>?", (day_ago,)),
            "total_downloads": await scalar("SELECT COUNT(*) FROM downloads"),
            "total_volume": await scalar("SELECT SUM(size) FROM downloads"),
        }
