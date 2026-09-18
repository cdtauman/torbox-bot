import os
import tempfile
import unittest

import aiosqlite

import config
import database as db


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.old_path = config.DB_PATH
        config.DB_PATH = self.path
        await db.init_db()

    async def asyncTearDown(self):
        config.DB_PATH = self.old_path
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass

    async def test_download_type_is_persisted(self):
        await db.log_download(
            user_id=1,
            name="Example",
            size=100,
            torbox_id=55,
            thash="",
            item_type="usenet",
        )
        rows = await db.get_unnotified_downloads()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["item_type"], "usenet")

    async def test_public_link_preserves_usenet_type(self):
        token = await db.get_or_create_public_link(
            user_id=1,
            item_type="usenet",
            torbox_id=77,
            name="Example",
        )
        row = await db.get_public_link(token)
        self.assertEqual(row["item_type"], "usenet")

        await db.disable_public_links_for_item("usenet", 77)
        self.assertIsNone(await db.get_public_link(token))

    async def test_notification_state_is_scoped_by_item_type(self):
        await db.log_download(1, "Torrent", 1, 99, "hash", item_type="torrent")
        await db.log_download(1, "Usenet", 1, 99, "", item_type="usenet")

        await db.mark_download_by_torbox_id_as_notified(99, 1, item_type="usenet")

        async with aiosqlite.connect(config.DB_PATH) as conn:
            async with conn.execute(
                "SELECT item_type, notified FROM downloads WHERE torbox_id=99 ORDER BY item_type"
            ) as cur:
                states = dict(await cur.fetchall())

        self.assertEqual(states["torrent"], 0)
        self.assertEqual(states["usenet"], 1)

    async def test_schema_contains_item_type_after_init(self):
        async with aiosqlite.connect(config.DB_PATH) as conn:
            async with conn.execute("PRAGMA table_info(downloads)") as cur:
                columns = {row[1] for row in await cur.fetchall()}
        self.assertIn("item_type", columns)


if __name__ == "__main__":
    unittest.main()
