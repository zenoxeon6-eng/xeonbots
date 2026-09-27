"""
════════════════════════════════════════════════════════════════════════
💎 AdVault Pro — النسخة الجبارة النهائية
════════════════════════════════════════════════════════════════════════
✅ لا يوجد force-join نهائيًا
✅ المالك يرى نفس الترحيب + أزرار إضافية
✅ المستخدم يرى الترحيب + أزرار أساسية
✅ زر تواصل مع @no_vi1
✅ زر التطبيق المصغر
════════════════════════════════════════════════════════════════════════
"""

import os, hmac, json, time, sqlite3, hashlib, asyncio, re
from urllib.parse import parse_qsl
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    WebAppInfo, BotCommand,
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)

# ═══════════════════════════════════════════════════════════════════════
# ⚙️ الإعدادات
# ═══════════════════════════════════════════════════════════════════════
BOT_TOKEN      = os.getenv("BOT_TOKEN",    "8909959176:AAF6V-RuF5nSAyKh1JOYijYoQJH7ZXB8GSM")
WEBAPP_URL     = os.getenv("WEBAPP_URL",   "https://xeonbots.onrender.com/")
BOT_USERNAME   = os.getenv("BOT_USERNAME","Cashbackigfbot").lstrip("@")
ADMIN_CONTACT  = os.getenv("ADMIN_CONTACT", "no_vi1").lstrip("@")
HOST           = os.getenv("HOST", "0.0.0.0")
PORT           = int(os.getenv("PORT", "8000"))
DB_PATH        = os.getenv("DB_PATH", "ads.db")

ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "8233835640").split(",")
             if x.strip().isdigit()]

DEF_AD_REWARD      = 0.20
DEF_DAILY_LIMIT    = 10
DEF_MIN_WITHDRAW   = 10.00
DEF_REFERRAL_BONUS = 0.50
DEF_DAILY_BONUS    = 0.10


# ═══════════════════════════════════════════════════════════════════════
# 🌍 الدول وطرق السحب
# ═══════════════════════════════════════════════════════════════════════
COUNTRIES = {
    "YE": {
        "name": "🇾🇪 اليمن", "flag": "🇾🇪", "label": "اليمن",
        "methods": [
            {"id": "jaib", "name": "💚 محفظة جيب", "fields": [
                {"name": "wallet", "label": "رقم المحفظة",
                 "placeholder": "7XXXXXXXX", "type": "tel", "required": True}]},
            {"id": "onecash", "name": "💙 ون كاش", "fields": [
                {"name": "wallet", "label": "رقم المحفظة",
                 "placeholder": "7XXXXXXXX", "type": "tel", "required": True}]},
            {"id": "kuraimi", "name": "🏦 بنك الكريمي", "fields": [
                {"name": "account", "label": "رقم الحساب",
                 "placeholder": "XXXX-XXXX-XXXX", "type": "text", "required": True}]},
        ],
    },
    "SA": {
        "name": "🇸🇦 السعودية", "flag": "🇸🇦", "label": "السعودية",
        "methods": [
            {"id": "card_topup", "name": "📱 شحن بطاقة", "fields": [
                {"name": "company", "label": "الشركة", "type": "select",
                 "options": [{"v": "stc", "l": "STC"},
                             {"v": "mobily", "l": "موبايلي"},
                             {"v": "zain", "l": "زين"}], "required": True},
                {"name": "phone", "label": "رقم الهاتف",
                 "placeholder": "05XXXXXXXX", "type": "tel", "required": True}]},
            {"id": "bank_iban", "name": "🏦 IBAN", "fields": [
                {"name": "iban", "label": "رقم الآيبان",
                 "placeholder": "SAXXXXXXXXXXXXXXXX", "type": "text", "required": True}]},
            {"id": "wallet_barcode", "name": "📸 باركود محفظة", "fields": [
                {"name": "barcode", "label": "نص الباركود",
                 "placeholder": "الصق الباركود", "type": "text", "required": True}]},
            {"id": "urpay", "name": "💳 UrPay", "fields": [
                {"name": "urpay_id", "label": "رقم UrPay",
                 "placeholder": "05XXXXXXXX", "type": "tel", "required": True}]},
        ],
    },
    "OTHER": {
        "name": "🌍 دولي", "flag": "🌍", "label": "دولي",
        "methods": [
            {"id": "paypal", "name": "💠 PayPal", "fields": [
                {"name": "email", "label": "البريد الإلكتروني",
                 "placeholder": "you@example.com", "type": "email", "required": True}]},
            {"id": "binance", "name": "🟡 Binance Pay", "fields": [
                {"name": "binance_id", "label": "Binance ID",
                 "placeholder": "123456789", "type": "text", "required": True}]},
            {"id": "usdt", "name": "💵 USDT (TRC20)", "fields": [
                {"name": "wallet", "label": "عنوان المحفظة",
                 "placeholder": "TXxxxx...", "type": "text", "required": True}]},
        ],
    },
}


def get_method(country_code, method_id):
    c = COUNTRIES.get(country_code)
    if not c:
        return None
    return next((m for m in c["methods"] if m["id"] == method_id), None)


# ═══════════════════════════════════════════════════════════════════════
# 💾 قاعدة البيانات
# ═══════════════════════════════════════════════════════════════════════
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT, first_name TEXT, last_name TEXT,
            language_code TEXT, is_premium INTEGER DEFAULT 0,
            photo_url TEXT,
            balance REAL DEFAULT 0, total_earned REAL DEFAULT 0,
            ads_watched INTEGER DEFAULT 0, ads_today INTEGER DEFAULT 0,
            last_ad_reset INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 0, last_daily INTEGER DEFAULT 0,
            referrals INTEGER DEFAULT 0, referred_by INTEGER,
            country TEXT, withdrawal_method TEXT, withdrawal_data TEXT,
            banned INTEGER DEFAULT 0, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT, description TEXT, url TEXT, contact TEXT,
            type TEXT DEFAULT 'link',
            video_file_id TEXT, image_file_id TEXT,
            reward REAL DEFAULT 0.20, duration INTEGER DEFAULT 15,
            active INTEGER DEFAULT 1, views INTEGER DEFAULT 0,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT, description TEXT, reward REAL DEFAULT 0,
            url TEXT, icon TEXT DEFAULT '🎯',
            active INTEGER DEFAULT 1, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS user_tasks (
            user_id INTEGER, task_id INTEGER, completed_at TEXT,
            PRIMARY KEY (user_id, task_id)
        );
        CREATE TABLE IF NOT EXISTS user_ads (
            user_id INTEGER, ad_id INTEGER, watched_at TEXT,
            PRIMARY KEY (user_id, ad_id, watched_at)
        );
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, amount REAL,
            country TEXT, method TEXT, method_name TEXT,
            account_json TEXT, status TEXT DEFAULT 'pending',
            note TEXT, created_at TEXT, processed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS contact_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, username TEXT,
            message TEXT, status TEXT DEFAULT 'new', created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT
        );
        """)

        for tbl, col, typ in [
            ("ads", "type", "TEXT DEFAULT 'link'"),
            ("ads", "video_file_id", "TEXT"),
            ("ads", "image_file_id", "TEXT"),
            ("ads", "contact", "TEXT"),
            ("users", "last_ad_reset", "INTEGER DEFAULT 0"),
            ("users", "streak", "INTEGER DEFAULT 0"),
            ("users", "last_daily", "INTEGER DEFAULT 0"),
        ]:
            try:
                conn.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {typ}")
            except sqlite3.OperationalError:
                pass

        defaults = {
            "ad_reward": str(DEF_AD_REWARD),
            "daily_limit": str(DEF_DAILY_LIMIT),
            "min_withdraw": str(DEF_MIN_WITHDRAW),
            "referral_bonus": str(DEF_REFERRAL_BONUS),
            "daily_bonus": str(DEF_DAILY_BONUS),
        }
        for k, v in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key,value) VALUES (?,?)",
                (k, v),
            )


def get_setting(key, default=None):
    with db() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ).fetchone()
        return row["value"] if row else default


def set_setting(key, value):
    with db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)",
            (key, str(value)),
        )


# ═══════════════════════════════════════════════════════════════════════
# 👤 المستخدمون
# ═══════════════════════════════════════════════════════════════════════
def user_to_dict(row):
    try:
        account = json.loads(row["withdrawal_data"] or "{}")
    except Exception:
        account = {}
    return {
        "user_id": row["user_id"], "username": row["username"] or "",
        "first_name": row["first_name"] or "User",
        "last_name": row["last_name"] or "",
        "is_premium": bool(row["is_premium"]),
        "photo_url": row["photo_url"] or "",
        "balance": round(row["balance"], 2),
        "total_earned": round(row["total_earned"], 2),
        "ads_watched": row["ads_watched"], "ads_today": row["ads_today"],
        "daily_limit": int(get_setting("daily_limit", "10")),
        "ad_reward": float(get_setting("ad_reward", "0.20")),
        "streak": row["streak"], "last_daily": row["last_daily"],
        "referrals": row["referrals"], "country": row["country"] or "",
        "withdrawal_method": row["withdrawal_method"] or "",
        "withdrawal_fields": account.get("fields", {}),
        "min_withdraw": float(get_setting("min_withdraw", "10.00")),
        "referral_bonus": float(get_setting("referral_bonus", "0.50")),
        "daily_bonus": float(get_setting("daily_bonus", "0.10")),
        "is_admin": row["user_id"] in ADMIN_IDS,
        "bot_username": BOT_USERNAME, "admin_contact": ADMIN_CONTACT,
    }


def get_or_create_user(user, referrer_id=None):
    uid = user["id"]
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id=?", (uid,)
        ).fetchone()
        if row:
            conn.execute(
                """UPDATE users SET username=?, first_name=?, last_name=?,
                   language_code=?, is_premium=? WHERE user_id=?""",
                (user.get("username", ""), user.get("first_name", ""),
                 user.get("last_name", ""), user.get("language_code", ""),
                 1 if user.get("is_premium") else 0, uid),
            )
            return conn.execute(
                "SELECT * FROM users WHERE user_id=?", (uid,)
            ).fetchone()

        now = datetime.now(timezone.utc).isoformat()
        if referrer_id and referrer_id != uid:
            ref_exists = conn.execute(
                "SELECT 1 FROM users WHERE user_id=?", (referrer_id,)
            ).fetchone()
            if ref_exists:
                bonus = float(get_setting("referral_bonus", "0.50"))
                conn.execute(
                    """UPDATE users SET balance=balance+?,
                       total_earned=total_earned+?, referrals=referrals+1
                       WHERE user_id=?""",
                    (bonus, bonus, referrer_id),
                )
        conn.execute(
            """INSERT INTO users (user_id, username, first_name, last_name,
               language_code, is_premium, referred_by, last_ad_reset, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (uid, user.get("username", ""), user.get("first_name", ""),
             user.get("last_name", ""), user.get("language_code", ""),
             1 if user.get("is_premium") else 0, referrer_id,
             int(time.time()), now),
        )
        return conn.execute(
            "SELECT * FROM users WHERE user_id=?", (uid,)
        ).fetchone()


def reset_ads_if_needed(row):
    now = int(time.time())
    if now - (row["last_ad_reset"] or 0) >= 86400:
        with db() as conn:
            conn.execute(
                "UPDATE users SET ads_today=0, last_ad_reset=? WHERE user_id=?",
                (now, row["user_id"]),
            )
        row = dict(row)
        row["ads_today"] = 0
        row["last_ad_reset"] = now
    return row


# ═══════════════════════════════════════════════════════════════════════
# 🔐 التحقق + أدوات Telegram
# ═══════════════════════════════════════════════════════════════════════
def validate_init_data(init_data):
    if not init_data or not BOT_TOKEN:
        return None
    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
        received = parsed.pop("hash", None)
        if not received:
            return None
        check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(),
                          hashlib.sha256).digest()
        calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, received):
            return None
        return {
            "user": json.loads(parsed.get("user", "{}")),
            "start_param": parsed.get("start_param", ""),
        }
    except Exception:
        return None


async def fetch_telegram_file(file_id):
    if not BOT_TOKEN or not file_id:
        return ""
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
                params={"file_id": file_id},
            )
            data = r.json()
            if not data.get("ok"):
                return ""
            return (f"https://api.telegram.org/file/bot{BOT_TOKEN}/"
                    f"{data['result']['file_path']}")
    except Exception:
        return ""


async def fetch_telegram_photo(user_id):
    if not BOT_TOKEN:
        return ""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUserProfilePhotos",
                params={"user_id": user_id, "limit": 1},
            )
            data = r.json()
            if not data.get("ok") or not data["result"]["photos"]:
                return ""
            fid = data["result"]["photos"][0][-1]["file_id"]
            r2 = await c.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
                params={"file_id": fid},
            )
            d2 = r2.json()
            if not d2.get("ok"):
                return ""
            return (f"https://api.telegram.org/file/bot{BOT_TOKEN}/"
                    f"{d2['result']['file_path']}")
    except Exception:
        return ""


def is_admin(uid):
    return uid in ADMIN_IDS


def require_admin(user_id):
    if user_id not in ADMIN_IDS:
        raise HTTPException(403, "مشرف فقط")


# ═══════════════════════════════════════════════════════════════════════
# 🚀 FastAPI
# ═══════════════════════════════════════════════════════════════════════
app = FastAPI(title="AdVault Pro", version="5.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def root():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            html = f.read()
        html = html.replace("__BOT_USERNAME_PLACEHOLDER__", BOT_USERNAME or "")
        html = html.replace("__ADMIN_CONTACT_PLACEHOLDER__", ADMIN_CONTACT or "")
        return html
    except FileNotFoundError:
        return HTMLResponse("<h1>index.html غير موجود</h1>", status_code=500)


@app.get("/health")
async def health():
    return {"ok": True, "bot": BOT_USERNAME,
            "time": datetime.now(timezone.utc).isoformat()}


# ═══════════════════════════════════════════════════════════════════════
# 🔑 Auth
# ═══════════════════════════════════════════════════════════════════════
@app.post("/api/auth")
async def api_auth(req: Request):
    body = await req.json()
    parsed = validate_init_data(body.get("initData", ""))
    if not parsed:
        raise HTTPException(401, "initData غير صالح")
    user = parsed["user"]
    ref = None
    sp = parsed.get("start_param", "")
    if sp.startswith("ref_"):
        try:
            ref = int(sp[4:])
        except ValueError:
            pass
    row = get_or_create_user(user, ref)
    if row["banned"]:
        raise HTTPException(403, "حسابك موقوف")
    if not row["photo_url"]:
        photo = await fetch_telegram_photo(row["user_id"])
        if photo:
            with db() as conn:
                conn.execute("UPDATE users SET photo_url=? WHERE user_id=?",
                             (photo, row["user_id"]))
    reset_ads_if_needed(dict(row))
    fresh = db().execute(
        "SELECT * FROM users WHERE user_id=?", (user["id"],)
    ).fetchone()
    return user_to_dict(fresh)


@app.get("/api/me")
async def api_me(user_id: int):
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "غير موجود")
    reset_ads_if_needed(dict(row))
    fresh = db().execute(
        "SELECT * FROM users WHERE user_id=?", (user_id,)
    ).fetchone()
    return user_to_dict(fresh)


# ═══════════════════════════════════════════════════════════════════════
# 📢 الإعلانات
# ═══════════════════════════════════════════════════════════════════════
@app.get("/api/ads")
async def api_ads(user_id: int):
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "غير موجود")
        reset_ads_if_needed(dict(row))
        ads = conn.execute(
            """SELECT id, title, description, url, contact, type,
                      video_file_id, image_file_id, reward, duration
               FROM ads WHERE active=1 ORDER BY RANDOM() LIMIT 30"""
        ).fetchall()
        fresh = conn.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
    return {
        "ads_today": fresh["ads_today"],
        "daily_limit": int(get_setting("daily_limit", "10")),
        "ad_reward": float(get_setting("ad_reward", "0.20")),
        "ads": [
            {
                "id": a["id"], "title": a["title"],
                "description": a["description"] or "",
                "url": a["url"] or "", "contact": a["contact"] or "",
                "type": a["type"] or "link",
                "has_video": bool(a["video_file_id"]),
                "has_image": bool(a["image_file_id"]),
                "reward": a["reward"] or 0.20,
                "duration": a["duration"] or 15,
            }
            for a in ads
        ],
    }


@app.get("/api/ad-media/{ad_id}")
async def api_ad_media(ad_id: int, range: str = Header(None)):
    with db() as conn:
        row = conn.execute(
            "SELECT video_file_id, image_file_id FROM ads WHERE id=?",
            (ad_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "لا وسائط")
    if row["video_file_id"]:
        file_url = await fetch_telegram_file(row["video_file_id"])
        media_type = "video/mp4"
    elif row["image_file_id"]:
        file_url = await fetch_telegram_file(row["image_file_id"])
        media_type = "image/jpeg"
    else:
        raise HTTPException(404, "لا وسائط")
    if not file_url:
        raise HTTPException(404, "تعذر الجلب")
    async with httpx.AsyncClient(timeout=120) as c:
        headers = {}
        if range:
            headers["Range"] = range
        resp = await c.get(file_url, headers=headers)
        if resp.status_code not in (200, 206):
            raise HTTPException(resp.status_code, "خطأ")
        if media_type == "video/mp4":
            return StreamingResponse(
                resp.aiter_bytes(), status_code=resp.status_code,
                media_type=media_type,
                headers={
                    "Content-Range": resp.headers.get("Content-Range", ""),
                    "Accept-Ranges": "bytes",
                    "Content-Length": resp.headers.get("Content-Length", ""),
                },
            )
        return Response(content=resp.content, media_type=media_type)


@app.post("/api/ads/{ad_id}/watch")
async def api_watch_ad(ad_id: int, req: Request):
    body = await req.json()
    user_id = int(body.get("user_id", 0))
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "غير موجود")
        reset_ads_if_needed(dict(row))
        limit = int(get_setting("daily_limit", "10"))
        row = conn.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        if row["ads_today"] >= limit:
            raise HTTPException(429, f"وصلت الحد اليومي ({limit})")
        ad = conn.execute(
            "SELECT * FROM ads WHERE id=? AND active=1", (ad_id,)
        ).fetchone()
        if not ad:
            raise HTTPException(404, "الإعلان غير متاح")
        recent = conn.execute(
            """SELECT 1 FROM user_ads WHERE user_id=? AND ad_id=?
               AND watched_at > datetime('now','-1 hour')""",
            (user_id, ad_id),
        ).fetchone()
        if recent:
            raise HTTPException(429, "شاهدت هذا الإعلان مؤخرًا")
        reward = ad["reward"] or float(get_setting("ad_reward", "0.20"))
        conn.execute(
            "INSERT INTO user_ads (user_id, ad_id, watched_at) VALUES (?,?,?)",
            (user_id, ad_id, datetime.now(timezone.utc).isoformat()),
        )
        conn.execute(
            """UPDATE users SET balance=balance+?, total_earned=total_earned+?,
               ads_watched=ads_watched+1, ads_today=ads_today+1
               WHERE user_id=?""",
            (reward, reward, user_id),
        )
        conn.execute("UPDATE ads SET views=views+1 WHERE id=?", (ad_id,))
        new_row = conn.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
    return {"reward": reward, "balance": round(new_row["balance"], 2),
            "ads_today": new_row["ads_today"], "daily_limit": limit}


# ═══════════════════════════════════════════════════════════════════════
# 📋 المهام + اليومية + المتصدرون
# ═══════════════════════════════════════════════════════════════════════
@app.get("/api/tasks")
async def api_tasks(user_id: int):
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE active=1 ORDER BY id DESC"
        ).fetchall()
        done = {r["task_id"] for r in conn.execute(
            "SELECT task_id FROM user_tasks WHERE user_id=?", (user_id,)
        ).fetchall()}
    return [{
        "id": r["id"], "title": r["title"],
        "description": r["description"] or "",
        "reward": r["reward"] or 0, "url": r["url"] or "",
        "icon": r["icon"] or "🎯", "completed": r["id"] in done,
    } for r in rows]


@app.post("/api/tasks/{task_id}/claim")
async def api_task_claim(task_id: int, req: Request):
    body = await req.json()
    user_id = int(body.get("user_id", 0))
    with db() as conn:
        task = conn.execute(
            "SELECT * FROM tasks WHERE id=? AND active=1", (task_id,)
        ).fetchone()
        if not task:
            raise HTTPException(404, "غير موجودة")
        if conn.execute(
            "SELECT 1 FROM user_tasks WHERE user_id=? AND task_id=?",
            (user_id, task_id),
        ).fetchone():
            raise HTTPException(400, "منجزة")
        conn.execute(
            "INSERT INTO user_tasks (user_id, task_id, completed_at) VALUES (?,?,?)",
            (user_id, task_id, datetime.now(timezone.utc).isoformat()),
        )
        if task["reward"] and task["reward"] > 0:
            conn.execute(
                """UPDATE users SET balance=balance+?, total_earned=total_earned+?
                   WHERE user_id=?""",
                (task["reward"], task["reward"], user_id),
            )
        row = conn.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
    return {"reward": task["reward"] or 0, "balance": round(row["balance"], 2)}


@app.post("/api/daily")
async def api_daily(req: Request):
    body = await req.json()
    user_id = int(body.get("user_id", 0))
    now = int(time.time()); day = 86400
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "غير موجود")
        since = now - (row["last_daily"] or 0)
        if since < day:
            raise HTTPException(400, f"عد بعد {(day - since)//3600} ساعة")
        streak = row["streak"] + 1 if since < 2 * day else 1
        base = float(get_setting("daily_bonus", "0.10"))
        reward = round(base * min(streak, 7), 2)
        conn.execute(
            """UPDATE users SET balance=balance+?, total_earned=total_earned+?,
               streak=?, last_daily=? WHERE user_id=?""",
            (reward, reward, streak, now, user_id),
        )
        row = conn.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
    return {"reward": reward, "streak": streak,
            "balance": round(row["balance"], 2)}


@app.get("/api/leaderboard")
async def api_leaderboard():
    with db() as conn:
        rows = conn.execute(
            """SELECT user_id, first_name, username, photo_url, total_earned
               FROM users WHERE banned=0
               ORDER BY total_earned DESC LIMIT 20"""
        ).fetchall()
    return [{
        "rank": i + 1, "user_id": r["user_id"],
        "first_name": r["first_name"], "username": r["username"],
        "photo_url": r["photo_url"],
        "total_earned": round(r["total_earned"], 2),
    } for i, r in enumerate(rows)]


@app.get("/api/countries")
async def api_countries():
    return COUNTRIES


@app.post("/api/withdrawal/setup")
async def api_setup_withdrawal(req: Request):
    body = await req.json()
    user_id = int(body.get("user_id", 0))
    country = (body.get("country") or "").strip()
    method_id = (body.get("method") or "").strip()
    fields_in = body.get("fields") or {}
    if country not in COUNTRIES:
        raise HTTPException(400, "دولة غير مدعومة")
    method = get_method(country, method_id)
    if not method:
        raise HTTPException(400, "طريقة غير مدعومة")
    clean = {}
    for f in method["fields"]:
        val = str(fields_in.get(f["name"], "")).strip()
        if f.get("required") and not val:
            raise HTTPException(400, f"حقل مطلوب: {f['label']}")
        clean[f["name"]] = val
    payload = json.dumps(
        {"country": country, "method": method_id, "fields": clean},
        ensure_ascii=False,
    )
    with db() as conn:
        conn.execute(
            """UPDATE users SET country=?, withdrawal_method=?,
               withdrawal_data=? WHERE user_id=?""",
            (country, method_id, payload, user_id),
        )
    return {"ok": True, "country": country,
            "method": method_id, "fields": clean}


@app.post("/api/withdraw")
async def api_withdraw(req: Request):
    body = await req.json()
    user_id = int(body.get("user_id", 0))
    amount = float(body.get("amount", 0))
    min_w = float(get_setting("min_withdraw", "10.00"))
    if amount < min_w:
        raise HTTPException(400, f"الحد الأدنى ${min_w:.2f}")
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "غير موجود")
        if not row["country"] or not row["withdrawal_method"] or not row["withdrawal_data"]:
            raise HTTPException(400, "أضف بيانات السحب أولًا")
        if row["balance"] < amount:
            raise HTTPException(400, "رصيدك غير كافٍ")
        method = get_method(row["country"], row["withdrawal_method"])
        method_name = method["name"] if method else row["withdrawal_method"]
        conn.execute(
            "UPDATE users SET balance=balance-? WHERE user_id=?",
            (amount, user_id),
        )
        cur = conn.execute(
            """INSERT INTO withdrawals (user_id, amount, country, method,
               method_name, account_json, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (user_id, amount, row["country"], row["withdrawal_method"],
             method_name, row["withdrawal_data"],
             datetime.now(timezone.utc).isoformat()),
        )
        wid = cur.lastrowid
        new_row = conn.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
    for admin in ADMIN_IDS:
        try:
            await notify_admin_withdrawal(
                admin, wid, user_id, amount,
                row["country"], method_name, row["withdrawal_data"],
            )
        except Exception:
            pass
    return {"ok": True, "balance": round(new_row["balance"], 2),
            "amount": amount, "id": wid}


@app.get("/api/withdrawals")
async def api_withdrawals(user_id: int):
    with db() as conn:
        rows = conn.execute(
            """SELECT id, amount, method_name, status, created_at
               FROM withdrawals WHERE user_id=?
               ORDER BY id DESC LIMIT 30""",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/contact-request")
async def api_contact_request(req: Request):
    body = await req.json()
    user_id = int(body.get("user_id", 0))
    message = (body.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "الرسالة مطلوبة")
    with db() as conn:
        row = conn.execute(
            "SELECT username, first_name FROM users WHERE user_id=?",
            (user_id,),
        ).fetchone()
        username = row["username"] if row else ""
        conn.execute(
            """INSERT INTO contact_requests
               (user_id, username, message, created_at)
               VALUES (?,?,?,?)""",
            (user_id, username, message,
             datetime.now(timezone.utc).isoformat()),
        )
    for admin in ADMIN_IDS:
        try:
            await notify_admin_contact(admin, user_id, username, message)
        except Exception:
            pass
    return {"ok": True, "message": "تم إرسال طلبك"}


# ═══════════════════════════════════════════════════════════════════════
# 🔔 إشعارات
# ═══════════════════════════════════════════════════════════════════════
async def notify_admin_withdrawal(admin, wid, user_id, amount,
                                  country, method_name, account_json):
    if not BOT_TOKEN:
        return
    try:
        f = json.loads(account_json).get("fields", {})
    except Exception:
        f = {}
    fields_txt = "\n".join(f"  • {k}: `{v}`" for k, v in f.items())
    text = (
        f"💸 *طلب سحب جديد*\n▬▬▬▬▬▬▬▬▬▬\n"
        f"🆔 `#{wid}`\n👤 `{user_id}`\n💵 `${amount:.2f}`\n"
        f"🌍 {COUNTRIES.get(country, {}).get('name', country)}\n"
        f"💳 {method_name}\n📄 البيانات:\n{fields_txt}"
    )
    kb = {"inline_keyboard": [[
        {"text": "✅ موافقة", "callback_data": f"wd_ok_{wid}"},
        {"text": "❌ رفض", "callback_data": f"wd_no_{wid}"},
    ]]}
    async with httpx.AsyncClient() as c:
        await c.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": admin, "text": text,
                  "parse_mode": "Markdown", "reply_markup": kb},
        )


async def notify_admin_contact(admin, user_id, username, message):
    if not BOT_TOKEN:
        return
    text = (
        f"📞 *طلب تواصل جديد*\n▬▬▬▬▬▬▬▬▬▬\n"
        f"👤 `{user_id}`\n🔗 @{username or '—'}\n\n"
        f"💬 {message}"
    )
    async with httpx.AsyncClient() as c:
        await c.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": admin, "text": text, "parse_mode": "Markdown"},
        )


# ═══════════════════════════════════════════════════════════════════════
# 👑 Admin API
# ═══════════════════════════════════════════════════════════════════════
@app.get("/api/admin/stats")
async def adm_stats(user_id: int):
    require_admin(user_id)
    with db() as conn:
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        ads = conn.execute("SELECT COUNT(*) FROM ads WHERE active=1").fetchone()[0]
        tasks = conn.execute("SELECT COUNT(*) FROM tasks WHERE active=1").fetchone()[0]
        pw = conn.execute("SELECT COUNT(*) FROM withdrawals WHERE status='pending'").fetchone()[0]
        cr = conn.execute("SELECT COUNT(*) FROM contact_requests WHERE status='new'").fetchone()[0]
        paid = conn.execute("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE status='approved'").fetchone()[0]
        views = conn.execute("SELECT COALESCE(SUM(views),0) FROM ads").fetchone()[0]
    return {"users": users, "ads": ads, "tasks": tasks,
            "pending_wd": pw, "contact_req": cr,
            "paid": round(paid, 2), "views": views}


@app.get("/api/admin/ads")
async def adm_ads_list(user_id: int):
    require_admin(user_id)
    with db() as conn:
        rows = conn.execute(
            """SELECT id, title, description, url, contact, type,
                      reward, duration, views, active
               FROM ads ORDER BY id DESC LIMIT 100"""
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/admin/ads")
async def adm_add_ad(req: Request):
    body = await req.json()
    require_admin(int(body.get("user_id", 0)))
    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "العنوان مطلوب")
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO ads (title, description, url, contact, type,
               reward, duration, created_at) VALUES (?,?,?,?,?,?,?,?)""",
            (title, body.get("description", ""), body.get("url", ""),
             body.get("contact", ""), "link",
             float(get_setting("ad_reward", "0.20")),
             int(body.get("duration", 15)),
             datetime.now(timezone.utc).isoformat()),
        )
    return {"ok": True, "id": cur.lastrowid}


@app.delete("/api/admin/ads/{ad_id}")
async def adm_del_ad(ad_id: int, user_id: int):
    require_admin(user_id)
    with db() as conn:
        conn.execute("UPDATE ads SET active=0 WHERE id=?", (ad_id,))
    return {"ok": True}


@app.post("/api/admin/ads/{ad_id}/toggle")
async def adm_toggle_ad(ad_id: int, req: Request):
    body = await req.json()
    require_admin(int(body.get("user_id", 0)))
    with db() as conn:
        row = conn.execute(
            "SELECT active FROM ads WHERE id=?", (ad_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "غير موجود")
        conn.execute("UPDATE ads SET active=? WHERE id=?",
                     (0 if row["active"] else 1, ad_id))
    return {"ok": True}


@app.get("/api/admin/tasks")
async def adm_tasks_list(user_id: int):
    require_admin(user_id)
    with db() as conn:
        rows = conn.execute(
            "SELECT id, title, description, reward, url, icon, active FROM tasks ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/admin/tasks")
async def adm_add_task(req: Request):
    body = await req.json()
    require_admin(int(body.get("user_id", 0)))
    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "العنوان مطلوب")
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO tasks (title, description, reward, url, icon, created_at)
               VALUES (?,?,?,?,?,?)""",
            (title, body.get("description", ""),
             float(body.get("reward", 0)), body.get("url", ""),
             body.get("icon", "🎯"), datetime.now(timezone.utc).isoformat()),
        )
    return {"ok": True, "id": cur.lastrowid}


@app.delete("/api/admin/tasks/{task_id}")
async def adm_del_task(task_id: int, user_id: int):
    require_admin(user_id)
    with db() as conn:
        conn.execute("UPDATE tasks SET active=0 WHERE id=?", (task_id,))
    return {"ok": True}


@app.get("/api/admin/withdrawals")
async def adm_withdrawals(user_id: int, status: str = None):
    require_admin(user_id)
    q = """SELECT w.*, u.first_name, u.username FROM withdrawals w
           LEFT JOIN users u ON u.user_id = w.user_id"""
    params = []
    if status:
        q += " WHERE w.status=?"
        params.append(status)
    q += " ORDER BY w.id DESC LIMIT 100"
    with db() as conn:
        rows = conn.execute(q, params).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["account"] = json.loads(d.get("account_json") or "{}").get("fields", {})
        except Exception:
            d["account"] = {}
        result.append(d)
    return result


@app.post("/api/admin/withdrawals/{wid}/approve")
async def adm_wd_approve(wid: int, req: Request):
    body = await req.json()
    require_admin(int(body.get("user_id", 0)))
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM withdrawals WHERE id=?", (wid,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "غير موجود")
        conn.execute(
            "UPDATE withdrawals SET status='approved', processed_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), wid),
        )
    try:
        async with httpx.AsyncClient() as c:
            await c.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": row["user_id"],
                      "text": f"✅ تمت الموافقة على سحبك `${row['amount']:.2f}`",
                      "parse_mode": "Markdown"},
            )
    except Exception:
        pass
    return {"ok": True}


@app.post("/api/admin/withdrawals/{wid}/reject")
async def adm_wd_reject(wid: int, req: Request):
    body = await req.json()
    require_admin(int(body.get("user_id", 0)))
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM withdrawals WHERE id=?", (wid,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "غير موجود")
        if row["status"] == "pending":
            conn.execute(
                "UPDATE users SET balance=balance+? WHERE user_id=?",
                (row["amount"], row["user_id"]),
            )
            conn.execute(
                "UPDATE withdrawals SET status='rejected', processed_at=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), wid),
            )
    try:
        async with httpx.AsyncClient() as c:
            await c.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": row["user_id"],
                      "text": f"❌ رُفض سحبك وأُرجع `${row['amount']:.2f}` لرصيدك",
                      "parse_mode": "Markdown"},
            )
    except Exception:
        pass
    return {"ok": True}


@app.get("/api/admin/contacts")
async def adm_contacts(user_id: int):
    require_admin(user_id)
    with db() as conn:
        rows = conn.execute(
            """SELECT * FROM contact_requests WHERE status='new'
               ORDER BY id DESC LIMIT 100"""
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/admin/contacts/{cid}/done")
async def adm_contact_done(cid: int, req: Request):
    body = await req.json()
    require_admin(int(body.get("user_id", 0)))
    with db() as conn:
        conn.execute(
            "UPDATE contact_requests SET status='done' WHERE id=?", (cid,)
        )
    return {"ok": True}


@app.get("/api/admin/settings")
async def adm_settings_get(user_id: int):
    require_admin(user_id)
    return {
        "ad_reward": get_setting("ad_reward"),
        "daily_limit": get_setting("daily_limit"),
        "min_withdraw": get_setting("min_withdraw"),
        "referral_bonus": get_setting("referral_bonus"),
        "daily_bonus": get_setting("daily_bonus"),
    }


@app.post("/api/admin/settings")
async def adm_settings_set(req: Request):
    body = await req.json()
    require_admin(int(body.get("user_id", 0)))
    for k in ["ad_reward", "daily_limit", "min_withdraw",
              "referral_bonus", "daily_bonus"]:
        if k in body:
            set_setting(k, body[k])
    return {"ok": True}


@app.get("/api/admin/users")
async def adm_users(user_id: int, q: str = None, limit: int = 50):
    require_admin(user_id)
    with db() as conn:
        if q:
            rows = conn.execute(
                """SELECT user_id, username, first_name, balance,
                          total_earned, banned FROM users
                   WHERE username LIKE ? OR first_name LIKE ? OR user_id=?
                   ORDER BY total_earned DESC LIMIT ?""",
                (f"%{q}%", f"%{q}%", q if q.isdigit() else 0, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT user_id, username, first_name, balance,
                          total_earned, banned FROM users
                   ORDER BY total_earned DESC LIMIT ?""",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/admin/users/{uid}/toggle-ban")
async def adm_user_ban(uid: int, req: Request):
    body = await req.json()
    require_admin(int(body.get("user_id", 0)))
    with db() as conn:
        r = conn.execute(
            "SELECT banned FROM users WHERE user_id=?", (uid,)
        ).fetchone()
        if not r:
            raise HTTPException(404, "غير موجود")
        conn.execute(
            "UPDATE users SET banned=? WHERE user_id=?",
            (0 if r["banned"] else 1, uid),
        )
    return {"ok": True}


@app.post("/api/admin/broadcast")
async def adm_broadcast(req: Request):
    body = await req.json()
    require_admin(int(body.get("user_id", 0)))
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "النص مطلوب")
    with db() as conn:
        users = conn.execute(
            "SELECT user_id FROM users WHERE banned=0"
        ).fetchall()
    sent = 0
    async with httpx.AsyncClient(timeout=10) as c:
        for u in users:
            try:
                r = await c.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={"chat_id": u["user_id"], "text": text,
                          "parse_mode": "Markdown"},
                )
                if r.json().get("ok"):
                    sent += 1
                await asyncio.sleep(0.05)
            except Exception:
                pass
    return {"ok": True, "sent": sent}


# ═══════════════════════════════════════════════════════════════════════
# 🤖 /start — الترحيب الفخم
# ═══════════════════════════════════════════════════════════════════════
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user

    user_dict = {
        "id": u.id, "username": u.username,
        "first_name": u.first_name, "last_name": u.last_name,
        "language_code": u.language_code,
        "is_premium": getattr(u, "is_premium", False),
    }

    sp = context.args[0] if context.args else ""
    ref = None
    if sp.startswith("ref_"):
        try:
            ref = int(sp[4:])
        except ValueError:
            pass

    get_or_create_user(user_dict, ref)

    with db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id=?", (u.id,)
        ).fetchone()

    # جلب صورة البروفايل
    if row and not row["photo_url"]:
        photo = await fetch_telegram_photo(u.id)
        if photo:
            with db() as conn:
                conn.execute(
                    "UPDATE users SET photo_url=? WHERE user_id=?",
                    (photo, u.id),
                )
            row = db().execute(
                "SELECT * FROM users WHERE user_id=?", (u.id,)
            ).fetchone()

    if not row:
        await update.message.reply_text("حدث خطأ، حاول مجددًا")
        return

    balance = row["balance"] or 0
    total_earned = row["total_earned"] or 0
    ads_today = row["ads_today"] or 0
    referrals = row["referrals"] or 0
    streak = row["streak"] or 0

    daily_limit = get_setting("daily_limit", "10")
    ad_reward = get_setting("ad_reward", "0.20")
    min_w = get_setting("min_withdraw", "10.00")
    ref_bonus = get_setting("referral_bonus", "0.50")

    is_owner = u.id in ADMIN_IDS
    premium = "⭐ " if getattr(u, "is_premium", False) else ""
    owner_badge = "👑 " if is_owner else ""
    rank_icon = "💎" if is_owner else "🎯"

    welcome = (
        f"✨━━━━━━━━━━━━━━━━━━━━━━━━━✨\n"
        f"    💎 *AdVault Pro* 💎\n"
        f"      _{rank_icon} منصة الربح الأولى_\n"
        f"✨━━━━━━━━━━━━━━━━━━━━━━━━━✨\n\n"

        f"{owner_badge}{premium}*أهلاً {u.first_name or 'صديقي'}*\n"
        f"╭─────────────────────────╮\n"
        f"│ 🆔 *المعرّف:* `{u.id}`\n"
        f"│ 🔗 *اليوزر:* {('@'+u.username) if u.username else '—'}\n"
        f"│ 💰 *رصيدك:* `${balance:.2f}`\n"
        f"│ 📊 *إجمالي أرباحك:* `${total_earned:.2f}`\n"
        f"│ 👁️ *إعلانات اليوم:* `{ads_today}/{daily_limit}`\n"
        f"│ 🤝 *إحالاتك:* `{referrals}`\n"
        f"│ 🔥 *Streak:* `{streak}` يوم\n"
        f"╰─────────────────────────╯\n\n"

        f"⚡ *ماذا يمكنك؟*\n"
        f"┌─────────────────────────┐\n"
        f"│ 👁️ اربح `${ad_reward}` لكل إعلان\n"
        f"│ 🎁 مكافأة يومية + Streak\n"
        f"│ 📋 مهام بمكافآت فورية\n"
        f"│ 🤝 اربح `${ref_bonus}` عن كل صديق\n"
        f"│ 💸 اسحب من `${min_w}`\n"
        f"└─────────────────────────┘\n"
    )

    if is_owner:
        welcome += (
            f"\n👑 *أنت المالك — أزرار خاصة ظاهرة لك:*\n"
            f"• استخدم `/admin` لفتح لوحة التحكم\n"
            f"• أرسل فيديو/صورة + تعليق: `العنوان | رابط | المدة`\n"
        )

    welcome += f"\n👇 *اضغط الزر أدناه للبدء الآن*"

    # ═══ الأزرار ═══
    kb = [
        [InlineKeyboardButton(
            "🚀 افتح التطبيق وابدأ الربح",
            web_app=WebAppInfo(url=WEBAPP_URL),
        )],
        [
            InlineKeyboardButton("🤝 رابط الإحالة", callback_data="get_ref"),
            InlineKeyboardButton("💰 رصيدي", callback_data="my_balance"),
        ],
        [
            InlineKeyboardButton(
                "📞 تواصل معنا",
                url=f"https://t.me/{ADMIN_CONTACT}",
            ),
            InlineKeyboardButton("📊 المتصدرون", callback_data="show_lb"),
        ],
    ]

    if is_owner:
        kb.append([InlineKeyboardButton(
            "👑 لوحة التحكم الكاملة",
            web_app=WebAppInfo(url=WEBAPP_URL),
        )])

    photo_url = row["photo_url"] or ""

    try:
        if photo_url:
            await update.message.reply_photo(
                photo=photo_url,
                caption=welcome,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(kb),
            )
        else:
            await update.message.reply_text(
                welcome, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(kb),
                disable_web_page_preview=True,
            )
    except Exception:
        try:
            await update.message.reply_text(
                welcome, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(kb),
                disable_web_page_preview=True,
            )
        except Exception as e:
            print(f"❌ خطأ إرسال الترحيب: {e}")


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ غير مصرح")
        return
    await update.message.reply_text(
        "👑 *لوحة التحكم*\n\n"
        "افتح التطبيق المصغر وستجد تبويب 👑 المشرف\n\n"
        "📌 *لإضافة إعلان فيديو/صورة:*\n"
        "أرسل الوسائط مع تعليق بالشكل:\n"
        "`العنوان | رابط أو رقم تواصل | المدة`",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("👑 فتح لوحة التحكم",
                                 web_app=WebAppInfo(url=WEBAPP_URL))
        ]]),
        parse_mode="Markdown",
    )


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id=?", (uid,)
        ).fetchone()
    if not row:
        await update.message.reply_text("افتح التطبيق أولاً")
        return
    await update.message.reply_text(
        f"💰 *رصيدك:* `${row['balance']:.2f}`\n"
        f"📊 *إجمالي:* `${row['total_earned']:.2f}`\n"
        f"👁️ *إعلانات اليوم:* `{row['ads_today']}/{get_setting('daily_limit')}`",
        parse_mode="Markdown",
    )


async def cmd_ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bot = context.bot.username
    link = f"https://t.me/{bot}?start=ref_{uid}"
    bonus = get_setting("referral_bonus", "0.50")
    await update.message.reply_text(
        f"🤝 *رابط الإحالة الخاص بك*\n"
        f"▬▬▬▬▬▬▬▬▬▬\n"
        f"`{link}`\n\n"
        f"💰 اربح `${bonus}` عن كل صديق ينضم عبرك.",
        parse_mode="Markdown",
    )


# ═══════════════════════════════════════════════════════════════════════
# 🔘 Callback Handlers
# ═══════════════════════════════════════════════════════════════════════
async def callback_get_ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    bot = context.bot.username
    link = f"https://t.me/{bot}?start=ref_{uid}"
    bonus = get_setting("referral_bonus", "0.50")
    await q.message.reply_text(
        f"🤝 *رابط الإحالة*\n▬▬▬▬▬▬▬▬▬▬\n"
        f"`{link}`\n\n"
        f"💰 اربح `${bonus}` عن كل صديق.",
        parse_mode="Markdown",
    )


async def callback_my_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id=?", (uid,)
        ).fetchone()
    if not row:
        await q.answer("افتح التطبيق أولاً", show_alert=True)
        return
    await q.answer(
        f"💰 رصيدك: ${row['balance']:.2f}\n"
        f"📊 إجمالي: ${row['total_earned']:.2f}",
        show_alert=True,
    )


async def callback_show_lb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    with db() as conn:
        rows = conn.execute(
            """SELECT first_name, username, total_earned FROM users
               WHERE banned=0 ORDER BY total_earned DESC LIMIT 10"""
        ).fetchall()
    if not rows:
        await q.message.reply_text("لا يوجد متصدرون بعد")
        return
    medals = ["🥇", "🥈", "🥉"]
    txt = "🏆 *أعلى 10 رابحين*\n▬▬▬▬▬▬▬▬▬▬\n"
    for i, r in enumerate(rows):
        ico = medals[i] if i < 3 else f"{i+1}."
        name = r["first_name"] or "User"
        txt += f"{ico} {name} — `${r['total_earned']:.2f}`\n"
    await q.message.reply_text(txt, parse_mode="Markdown")


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        await q.edit_message_text("⛔ غير مصرح")
        return
    d = q.data

    if d.startswith("wd_ok_"):
        wid = int(d.split("_")[-1])
        with db() as conn:
            row = conn.execute(
                "SELECT * FROM withdrawals WHERE id=?", (wid,)
            ).fetchone()
            conn.execute(
                "UPDATE withdrawals SET status='approved', processed_at=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), wid),
            )
        if row:
            try:
                await context.bot.send_message(
                    chat_id=row["user_id"],
                    text=f"✅ تمت الموافقة على سحبك `${row['amount']:.2f}`",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
        await q.answer("✅ تمت الموافقة", show_alert=True)
        return

    if d.startswith("wd_no_"):
        wid = int(d.split("_")[-1])
        with db() as conn:
            row = conn.execute(
                "SELECT * FROM withdrawals WHERE id=?", (wid,)
            ).fetchone()
            if row and row["status"] == "pending":
                conn.execute(
                    "UPDATE users SET balance=balance+? WHERE user_id=?",
                    (row["amount"], row["user_id"]),
                )
                conn.execute(
                    "UPDATE withdrawals SET status='rejected', processed_at=? WHERE id=?",
                    (datetime.now(timezone.utc).isoformat(), wid),
                )
        if row:
            try:
                await context.bot.send_message(
                    chat_id=row["user_id"],
                    text=f"❌ رُفض سحبك وأُرجع `${row['amount']:.2f}` لرصيدك",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
        await q.answer("❌ تم الرفض والإرجاع", show_alert=True)
        return


async def handle_admin_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    msg = update.message
    if not (msg.video or msg.photo):
        return
    caption = msg.caption or ""
    parts = [p.strip() for p in caption.split("|")]
    if not parts or not parts[0]:
        await msg.reply_text(
            "❌ أرسل الوسائط مع تعليق:\n"
            "`العنوان | رابط أو رقم تواصل | المدة`",
            parse_mode="Markdown",
        )
        return
    title = parts[0]
    contact = parts[1] if len(parts) > 1 else ""
    duration = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 15
    ad_url = contact if contact.startswith("http") else ""
    contact_val = "" if contact.startswith("http") else contact
    video_id = msg.video.file_id if msg.video else None
    image_id = msg.photo[-1].file_id if msg.photo else None
    atype = "video" if video_id else "image"
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO ads (title, description, url, contact, type,
               video_file_id, image_file_id, reward, duration, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (title, "", ad_url, contact_val, atype,
             video_id, image_id,
             float(get_setting("ad_reward", "0.20")),
             duration, datetime.now(timezone.utc).isoformat()),
        )
        aid = cur.lastrowid
    await msg.reply_text(
        f"✅ *تمت إضافة الإعلان*\n"
        f"🆔 `#{aid}`\n📌 {title}\n🎬 {atype} • ⏱ {duration}s",
        parse_mode="Markdown",
    )


async def set_bot_commands(app_bot):
    try:
        await app_bot.bot.set_my_commands([
            BotCommand("start", "🏠 ابدأ"),
            BotCommand("balance", "💰 رصيدي"),
            BotCommand("ref", "🤝 رابط الإحالة"),
        ])
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════
# 🚀 التشغيل
# ═══════════════════════════════════════════════════════════════════════
async def run_bot():
    if not BOT_TOKEN:
        print("⚠️ BOT_TOKEN غير مضبوط")
        return
    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()

    app_bot.add_handler(CommandHandler("start", cmd_start))
    app_bot.add_handler(CommandHandler("admin", cmd_admin))
    app_bot.add_handler(CommandHandler("balance", cmd_balance))
    app_bot.add_handler(CommandHandler("ref", cmd_ref))

    app_bot.add_handler(CallbackQueryHandler(callback_get_ref, pattern=r"^get_ref$"))
    app_bot.add_handler(CallbackQueryHandler(callback_my_balance, pattern=r"^my_balance$"))
    app_bot.add_handler(CallbackQueryHandler(callback_show_lb, pattern=r"^show_lb$"))
    app_bot.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^(wd_ok_|wd_no_)"))

    app_bot.add_handler(MessageHandler(
        (filters.VIDEO | filters.PHOTO) & filters.User(ADMIN_IDS),
        handle_admin_media,
    ))

    await app_bot.initialize()
    await set_bot_commands(app_bot)
    await app_bot.start()
    await app_bot.updater.start_polling()
    print("✅ البوت يعمل...")
    print(f"📞 للتواصل: @{ADMIN_CONTACT}")
    while True:
        await asyncio.sleep(3600)


async def run_web():
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    init_db()
    print(f"🌐 التطبيق: {WEBAPP_URL}")
    print(f"👑 المشرفون: {ADMIN_IDS}")
    print(f"🤖 اسم البوت: {BOT_USERNAME}")
    print(f"📞 للتواصل: @{ADMIN_CONTACT}")
    await asyncio.gather(run_bot(), run_web())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 تم الإيقاف")
