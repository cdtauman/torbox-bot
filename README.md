# 🔎 TorBox Telegram Bot

בוט טלגרם לחיפוש מאוחד, הוספת הורדות ומעקב דרך **TorBox**.  
הממשק בנוי סביב Smart Input: המשתמש פשוט שולח שם, URL, Magnet, info-hash, ‎.torrent או ‎.nzb, והבוט בוחר אוטומטית את המסלול המתאים.

> השתמש רק במקורות ובתוכן שיש לך הרשאה לגשת אליהם.

---

## ✨ מה הבוט יודע לעשות

### 🧠 Smart Input
- טקסט רגיל → חיפוש מאוחד.
- Magnet או info-hash → Torrent.
- URL רגיל → WebDL דרך TorBox.
- URL שמסתיים ב-`.nzb` → Usenet.
- קובץ `.torrent` או `.nzb` → העלאה ישירה.
- אין צורך לבחור מצב לפני שמדביקים משהו.
- URL/Magnet/hash אינם נכתבים במלואם ללוגי ה-router.

### 🔍 חיפוש מאוחד
- חיפוש אחד שממזג תוצאות מ-**Prowlarr** ומ-**TorBox Search** כאשר הם זמינים.
- תמיכה בתוצאות **Torrent** ו-**Usenet/NZB** באותה רשימה.
- הסרת כפילויות בין מקורות.
- זיהוי אוטומטי של איכות, קטגוריה ושפה.
- סינון לפי איכות, גודל, קטגוריה, מקור וזמינות בקאש.
- מיון לפי זמינות/זרעים, גודל, תאריך וקאש.

### 📥 הורדה אוטומטית לפי סוג התוצאה
- Torrent: magnet, hash או קובץ `.torrent`.
- Usenet: קובץ `.nzb` או NZB שהתקבל דרך Prowlarr.
- WebDL: URL שנתמך על ידי TorBox.
- המשתמש לוחץ על אותו כפתור הורדה; הבוט בוחר את מסלול ה-API המתאים.

### 📡 מסך הורדות אחד
- Torrent, Usenet ו-WebDL מוצגים יחד.
- סטטוס התקדמות ותור.
- ביטול/מחיקה לפי סוג ההורדה.
- קישור הורדה ישיר כשהפריט מוכן.
- התראה אוטומטית בסיום.

### 🔗 קישורים קבועים
אפשר להפעיל endpoint קטן של הבוט שמחזיק URL קבוע משלך.  
בכל לחיצה הוא מבקש מ-TorBox קישור טרי ומבצע redirect, בלי לחשוף את מפתח ה-API.

### 👥 ניהול משתמשים
- משתמש חדש ממתין לאישור.
- משתמש / מנהל / בעלים.
- אישור, השהיה, ביטול השהיה, מחיקה וקידום.
- סטטיסטיקות ושידור הודעות.

---

## 🧱 איך זה בנוי

```text
Telegram
   │
   ▼
Unified Search
   ├── Prowlarr ── Torrent indexers
   │            └─ Usenet / NZB indexers
   └── TorBox Search
           │
           ▼
Normalize + deduplicate + filter
           │
     ┌─────┼────────┐
     ▼     ▼        ▼
 Torrent  Usenet   WebDL
     └─────┼────────┘
           ▼
         TorBox
```

Prowlarr משמש כ-**indexer manager** בלבד. ההורדה עצמה אינה מתבצעת על שרת הבוט.

---

## 🚀 התקנה

### דרישות
- Python 3.10+
- חשבון TorBox עם היכולות הדרושות לסוגי ההורדה שבהם אתה משתמש
- Telegram Bot Token
- Prowlarr מומלץ מאוד לחיפוש רחב

### התקנה מקומית

```bash
git clone https://github.com/cdtauman/torbox-bot.git
cd torbox-bot
pip install -r requirements.txt
cp .env.example .env
```

מלא לפחות:

```env
BOT_TOKEN=
TORBOX_API_KEY=
OWNER_ID=

SEARCH_PROVIDER=auto
SEARCH_INCLUDE_TORRENTS=1
SEARCH_INCLUDE_USENET=1

PROWLARR_URL=http://127.0.0.1:9696
PROWLARR_API_KEY=
```

ואז:

```bash
python bot.py
```

---

## 🐳 Docker + Prowlarr

```bash
cp .env.example .env
docker compose up -d --build
```

Prowlarr נחשף כברירת מחדל רק ל-`127.0.0.1:9696`.

כדי לפתוח אותו מרחוק בצורה בטוחה:

```bash
ssh -L 9696:127.0.0.1:9696 root@YOUR_SERVER_IP
```

לאחר מכן פתח:

```text
http://127.0.0.1:9696
```

ב-Prowlarr:
1. הוסף indexers שאתה מורשה להשתמש בהם.
2. ניתן להוסיף גם indexers בפרוטוקול Torrent וגם Usenet.
3. בדוק חיפוש ידני.
4. העתק את ה-API Key מ-`Settings > General` אל `PROWLARR_API_KEY`.
5. הפעל מחדש את הבוט.

### מצב החיפוש

```env
# מומלץ: ממזג Prowlarr + TorBox Search כאשר שניהם זמינים
SEARCH_PROVIDER=auto

# אפשר גם לכפות מקור יחיד:
# SEARCH_PROVIDER=prowlarr
# SEARCH_PROVIDER=torbox
```

אם TorBox Search אינו מוגדר בחשבון או מחזיר שגיאה, מצב `auto` ממשיך לעבוד עם Prowlarr ולא מפיל את החיפוש כולו.

---

## 📰 Usenet

הבוט מקבל תוצאות Usenet מ-Prowlarr במקום למחוק אותן כפי שעשה בעבר.

מסלול טיפוסי:

```text
Prowlarr result
   ↓
NZB
   ↓
TorBox /usenet/createusenetdownload
   ↓
Status / notification / download link
```

אפשר גם לשלוח לבוט קובץ `.nzb` ישירות.

לפי מגבלות TorBox, יצירת הורדות Usenet כפופה ל-rate limits של החשבון/API, ולכן הבוט אינו אמור להציף את endpoint היצירה.

---

## 🔗 קישורי הורדה קבועים

הגדרה לדוגמה:

```env
PUBLIC_BASE_URL=https://downloads.example.com
PUBLIC_LINKS_ENABLED=1
PUBLIC_LINK_HOST=0.0.0.0
PUBLIC_LINK_PORT=8080
PUBLIC_LINK_PATH_PREFIX=d

# 0 = לא למחוק אוטומטית הורדות שהושלמו
AUTO_DELETE_COMPLETED_AFTER_MINUTES=0
```

ב-Docker, פורט 8080 קשור כברירת מחדל רק ל-`127.0.0.1`.  
חבר אליו reverse proxy עם HTTPS.

URL לדוגמה:

```text
https://downloads.example.com/d/<token>
```

הקישור נשאר שימושי רק כל עוד הפריט עדיין קיים בחשבון TorBox וניתן ליצור עבורו קישור הורדה חדש.

---

## ⚙️ משתני סביבה חשובים

| משתנה | משמעות |
|---|---|
| `BOT_TOKEN` | Telegram Bot Token |
| `TORBOX_API_KEY` | מפתח API של TorBox |
| `OWNER_ID` | מזהה הבעלים |
| `SEARCH_PROVIDER` | `auto`, `prowlarr` או `torbox` |
| `SEARCH_INCLUDE_TORRENTS` | האם לקבל תוצאות Torrent |
| `SEARCH_INCLUDE_USENET` | האם לקבל תוצאות Usenet |
| `PROWLARR_URL` | כתובת Prowlarr |
| `PROWLARR_API_KEY` | API Key של Prowlarr |
| `PROWLARR_LIMIT` | מקסימום תוצאות שמבקשים מ-Prowlarr |
| `SEARCH_CONCURRENCY` | מספר חיפושים מקבילים |
| `PUBLIC_BASE_URL` | דומיין לקישורים קבועים |
| `AUTO_DELETE_COMPLETED_AFTER_MINUTES` | retention מקומי ב-TorBox; 0 משבית מחיקה אוטומטית |
| `QUEUE_ROTATE_ACTIVE_AFTER_MINUTES` | מתי ניתן לפנות הורדה פעילה ישנה לטובת התור |

---

## 🧪 בדיקות

```bash
python -m compileall -q .
python -m unittest discover -s tests -p "test_*.py" -v
```

GitHub Actions מריץ את שתי הבדיקות אוטומטית בכל PR ל-`master` וגם אחרי push ל-`master`.

---

## 📁 מבנה מרכזי

```text
torbox-bot/
├── bot.py
├── config.py
├── database.py
├── handlers/
│   ├── search.py
│   ├── download.py
│   ├── status.py
│   ├── filters.py
│   ├── settings.py
│   └── admin.py
├── services/
│   ├── prowlarr_api.py
│   ├── torbox_api.py
│   ├── parser.py
│   ├── monitor.py
│   ├── formatter.py
│   ├── keyboards.py
│   ├── public_links.py
│   └── link_server.py
└── tests/
```

---

## 🔐 אבטחה ותפעול

- אל תכניס API keys לקוד או ל-Git.
- Prowlarr ושרת הקישורים קשורים ל-localhost ב-Docker כברירת מחדל.
- פרסם את שרת הקישורים רק מאחורי HTTPS/reverse proxy.
- הבוט אינו זקוק ל-qBittorrent/Transmission על השרת: TorBox מטפל בהורדות.
- מומלץ להשתמש רק ב-indexers ובתוכן שאתה מורשה לגשת אליהם.

---

## 📜 רישיון

MIT
