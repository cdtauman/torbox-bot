"""
database.py — שכבת בסיס הנתונים (SQLite אסינכרוני)
מנהל: משתמשים, הגדרות אישיות, היסטוריית חיפוש והורדות.
"""
import json
import secrets
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS public_links (
                token       TEXT PRIMARY KEY,
                user_id     INTEGER,
                item_type   TEXT NOT NULL,
                torbox_id   TEXT NOT NULL,
                file_id     TEXT DEFAULT '',
                name        TEXT,
                created_at  INTEGER,
                last_accessed INTEGER,
                access_count INTEGER DEFAULT 0,
                active      INTEGER DEFAULT 1
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


async def mark_download_by_torbox_id_as_notified(torbox_id, user_id: int):
    """מסמן הורדה ככזו שנשלחה עבורה התראה לפי ה-torbox_id ומזהה המשתמש."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE downloads SET notified=1 WHERE torbox_id=? AND user_id=?", (torbox_id, user_id))
        await db.commit()


async def is_download_logged(user_id: int, torbox_id) -> bool:
    """בודק אם כבר קיימת רשומה פעילה (שטרם עודכנה לגביה התראה) עבור משתמש זה והורדה זו."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM downloads WHERE user_id=? AND torbox_id=? AND notified=0",
            (user_id, torbox_id)
        ) as cur:
            return bool(await cur.fetchone())




async def get_or_create_public_link(
    user_id: int,
    item_type: str,
    torbox_id,
    name: str = "",
    file_id=None,
) -> str:
    """יוצר token ציבורי קבוע להורדה, או מחזיר token קיים לאותו פריט."""
    item_type = "webdl" if item_type == "webdl" else "torrent"
    torbox_id = str(torbox_id)
    file_id = "" if file_id is None else str(file_id)
    now = int(time.time())

    async with aiosqlite.connect(config.DB_PATH) as db:
        async with db.execute(
            """
            SELECT token FROM public_links
            WHERE user_id=? AND item_type=? AND torbox_id=? AND file_id=? AND active=1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id, item_type, torbox_id, file_id),
        ) as cur:
            row = await cur.fetchone()
            if row:
                return row[0]

        for _ in range(5):
            token = secrets.token_urlsafe(18)
            try:
                await db.execute(
                    """
                    INSERT INTO public_links
                    (token, user_id, item_type, torbox_id, file_id, name, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (token, user_id, item_type, torbox_id, file_id, name or "", now),
                )
                await db.commit()
                return token
            except aiosqlite.IntegrityError:
                continue

    raise RuntimeError("Failed to create a unique public download token")


async def get_public_link(token: str):
    """מחזיר רשומת קישור ציבורי לפי token."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM public_links WHERE token=? AND active=1",
            (token,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def record_public_link_access(token: str):
    """מעדכן סטטיסטיקת שימוש לקישור ציבורי."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """
            UPDATE public_links
            SET last_accessed=?, access_count=COALESCE(access_count, 0) + 1
            WHERE token=?
            """,
            (int(time.time()), token),
        )
        await db.commit()


async def disable_public_links_for_item(item_type: str, torbox_id):
    """מבטל קישורים ציבוריים לפריט שנמחק ידנית."""
    item_type = "webdl" if item_type == "webdl" else "torrent"
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE public_links SET active=0 WHERE item_type=? AND torbox_id=?",
            (item_type, str(torbox_id)),
        )
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
