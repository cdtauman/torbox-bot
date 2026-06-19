# 🎬 TorBox Telegram Bot

בוט טלגרם מלא לחיפוש והורדת טורנטים דרך **TorBox** — עם ממשק כפתורים אינטואיטיבי, מערכת ניהול משתמשים, וכל יכולות הסינון והמיון של אתרי החיפוש הטובים בעולם.

---

## ✨ יכולות

**חיפוש חכם**
- חיפוש טקסט חופשי דרך Prowlarr או TorBox Search API
- זיהוי אוטומטי של איכות (480p/720p/1080p/4K), קטגוריה ושפה
- תמיכה ב-magnet ובקבצי `.torrent` ישירות

**סינון ומיון מלאים (כמו 1337x / YTS)**
- 🔽 סינון לפי איכות, גודל מקסימלי, קטגוריה, וזמינות בקאש
- 🔃 מיון לפי זרעים / גודל / תאריך / קאש קודם
- ⚡ סימון תוצאות שכבר בקאש להורדה מיידית

**ניהול משתמשים מלא**
- מערכת אישורים — משתמש חדש ממתין לאישור מנהל
- אישור / השהיה / ביטול השהיה / מחיקה / קידום למנהל
- 4 רמות הרשאה: ממתין → משתמש → מנהל → בעלים
- סטטיסטיקות שימוש ושידור הודעות לכל המשתמשים

**חוויית משתמש**
- הכל בכפתורים — כמעט ללא הקלדה
- מעקב הורדות בזמן אמת עם פס התקדמות
- קישורי הורדה ישירים בלחיצה
- הגדרות אישיות לכל משתמש

---

## 🚀 התקנה

### 1. דרישות מקדימות
- Python 3.10+
- חשבון **TorBox בתשלום** (החיפוש דורש מנוי)
- בוט טלגרם מ-[@BotFather](https://t.me/BotFather)

### 2. הורדה והתקנה
```bash
cd torbox-bot
pip install -r requirements.txt
```

### 3. הגדרה
העתק את קובץ הדוגמה ומלא את הפרטים:
```bash
cp .env.example .env
nano .env
```

מלא:
- `BOT_TOKEN` — מ-@BotFather
- `TORBOX_API_KEY` — מ-https://torbox.app/settings (לשונית API)
- `OWNER_ID` — ה-ID שלך מ-[@userinfobot](https://t.me/userinfobot)
- `SEARCH_PROVIDER=prowlarr` — מומלץ להרצה על Hetzner
- `PROWLARR_API_KEY` — מתוך Prowlarr: `Settings > General`

### 4. הרצה
```bash
python bot.py
```

---

## 🐳 הרצה בטוחה על Hetzner עם Prowlarr

השרת משמש לחיפוש בלבד. אין להריץ עליו qBittorrent/Transmission ואין לבצע הורדות P2P ממנו.
ההורדות בפועל נשלחות ל-TorBox.

```bash
cp .env.example .env
nano .env
docker compose up -d --build
```

Prowlarr לא פתוח לאינטרנט. כדי להגדיר אותו פתח SSH tunnel מהמחשב שלך:

```bash
ssh -L 9696:127.0.0.1:9696 root@YOUR_SERVER_IP
```

ואז בדפדפן:

```text
http://127.0.0.1:9696
```

בתוך Prowlarr:
- הוסף indexers שאתה מורשה להשתמש בהם.
- בדוק חיפוש ידני ל-`Oasis.2026.S01E01`.
- העתק API Key מ-`Settings > General` אל `PROWLARR_API_KEY` בקובץ `.env`.
- הרץ מחדש:

```bash
docker compose up -d --build
```

בדיקת בטיחות:
- פורט `9696` קשור רק ל-`127.0.0.1`.
- הבוט מדבר עם Prowlarr דרך Docker network פנימי: `http://prowlarr:9696`.
- אין download client על השרת, ולכן אין תעבורת P2P מהשרת.

---

## 🖥️ הרצה קבועה על שרת (systemd)

צור קובץ `/etc/systemd/system/torbox-bot.service`:
```ini
[Unit]
Description=TorBox Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/to/torbox-bot
ExecStart=/usr/bin/python3 /path/to/torbox-bot/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

הפעל:
```bash
sudo systemctl enable torbox-bot
sudo systemctl start torbox-bot
sudo systemctl status torbox-bot
```

---

## 📁 מבנה הפרויקט

```
torbox-bot/
├── bot.py                  # נקודת כניסה + ראוטר כפתורים
├── config.py               # הגדרות גלובליות וקבועים
├── database.py             # SQLite — משתמשים, היסטוריה, הגדרות
├── docker-compose.yml      # פריסה בטוחה עם Prowlarr פנימי
├── Dockerfile              # קונטיינר לבוט
│
├── handlers/
│   ├── auth.py             # בדיקות הרשאה
│   ├── menu.py             # תפריט ראשי, /start, עזרה
│   ├── search.py           # חיפוש + תצוגת תוצאות
│   ├── filters.py          # סינון ומיון
│   ├── download.py         # הוספת הורדות
│   ├── status.py           # מעקב הורדות + קישורים
│   ├── settings.py         # הגדרות אישיות
│   └── admin.py            # פאנל ניהול
│
├── services/
│   ├── torbox_api.py       # עטיפת TorBox API
│   ├── prowlarr_api.py     # חיפוש דרך Prowlarr
│   ├── parser.py           # נרמול, סינון, מיון, זיהוי איכות
│   ├── keyboards.py        # כל הכפתורים
│   └── formatter.py        # עיצוב הודעות בעברית
│
├── .env.example
├── requirements.txt
└── README.md
```

---

## 🔧 התאמה אישית

**הוספת זיהוי קטגוריות / איכויות** — ערוך את `CATEGORY_KEYWORDS` ו-`QUALITY_PATTERNS` ב-`config.py`.

**אינדקסרים פרטיים (Prowlarr/Jackett)** — ההמלצה היא לחפש ישירות ב-Prowlarr מתוך הבוט (`SEARCH_PROVIDER=prowlarr`) ולשלוח את ההורדה ל-TorBox. TorBox Search API נשאר fallback בלבד.

---

## ⚠️ הערות

- החיפוש דרך Prowlarr דורש לפחות indexer פעיל אחד ב-Prowlarr.
- TorBox Search API דורש Search Engines מוגדרים בחשבון TorBox, ולכן אינו פתרון ראשי בבוט הזה.
- הבוט מיועד לשימוש אישי/קבוצתי סגור. אתה אחראי לתוכן שאתה מוריד ולחוקי זכויות היוצרים במדינתך.

---

## 📜 רישיון
MIT — שימוש חופשי.
