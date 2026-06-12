# 🎬 TorBox Telegram Bot

בוט טלגרם מלא לחיפוש והורדת טורנטים דרך **TorBox** — עם ממשק כפתורים אינטואיטיבי, מערכת ניהול משתמשים, וכל יכולות הסינון והמיון של אתרי החיפוש הטובים בעולם.

---

## ✨ יכולות

**חיפוש חכם**
- חיפוש טקסט חופשי בכל המקורות של TorBox
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

### 4. הרצה
```bash
python bot.py
```

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

**אינדקסרים פרטיים (Prowlarr/Jackett)** — TorBox תומך בהוספת מנועי חיפוש משלך (BYOI) דרך ההגדרות באתר. הבוט ישתמש בהם אוטומטית דרך אותו Search API.

---

## ⚠️ הערות

- החיפוש ב-TorBox דורש **מנוי בתשלום**. במנוי חינמי החיפוש לא יחזיר תוצאות.
- מבנה תגובת ה-Search API עשוי להשתנות בין גרסאות. אם החיפוש לא מחזיר תוצאות, בדוק את התיעוד העדכני ב-https://api-docs.torbox.app והתאם את `services/torbox_api.py`.
- הבוט מיועד לשימוש אישי/קבוצתי סגור. אתה אחראי לתוכן שאתה מוריד ולחוקי זכויות היוצרים במדינתך.

---

## 📜 רישיון
MIT — שימוש חופשי.
