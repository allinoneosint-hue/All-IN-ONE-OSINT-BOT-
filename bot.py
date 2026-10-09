import asyncio
import html
import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from aiohttp import web
import httpx
from telegram import (
    BotCommand,
    ChatMember,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    MenuButtonCommands,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError, Conflict
from telegram.request import HTTPXRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ============================================================
# ANIMATED EMOJI CONSTANTS (LOADED FROM IDS.TXT)
# ============================================================
EMOJI_SKULL = '<tg-emoji id="5978722100985205002">☠️</tg-emoji>'
EMOJI_SHIELD = '<tg-emoji id="5251203410396458957">🛡</tg-emoji>'
EMOJI_LIGHTNING = '<tg-emoji id="5456140674028019486">⚡️</tg-emoji>'
EMOJI_FIRE = '<tg-emoji id="5424972470023104089">🔥</tg-emoji>'
EMOJI_CROWN = '<tg-emoji id="5217822164362739968">👑</tg-emoji>'
EMOJI_WARN = '<tg-emoji id="5447644880824181073">⚠️</tg-emoji>'
EMOJI_CHECK = '<tg-emoji id="5084979757905347540">✅</tg-emoji>'
EMOJI_CROSS = '<tg-emoji id="5210952531676504517">❌</tg-emoji>'
EMOJI_RADAR = '<tg-emoji id="5116508099213001597">🚨</tg-emoji>'
EMOJI_USER = '<tg-emoji id="5116582462276764538">👤</tg-emoji>'
EMOJI_SEARCH = '<tg-emoji id="5231012545799666522">🔍</tg-emoji>'

# ============================================================
# CONFIGURATION
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

ADMIN_ID_1 = int(os.getenv("ADMIN_ID_1", "0"))
ADMIN_ID_2 = int(os.getenv("ADMIN_ID_2", "0"))
AUDIT_LOG_CHANNEL_ID = int(os.getenv("AUDIT_LOG_CHANNEL_ID", "0"))

BRAND = "OBSIDIAN TRACE"
DB_FILE = "bot.db"
REQUEST_TIMEOUT = 35.0
MAX_MESSAGE_LENGTH = 3900

DEFAULT_PRIVATE_LIMIT = int(os.getenv("DEFAULT_PRIVATE_LIMIT", "3"))
DEFAULT_GROUP_LIMIT = int(os.getenv("DEFAULT_GROUP_LIMIT", "4"))
DEFAULT_REFERRAL_BONUS = 2
DEFAULT_FREEZE_MINUTES = 5

OWNER_CONTACTS = "@pulkitinfobot, @KRUTIK_CYBER_DEVELOPER0"

RESTRICTED_QUERY_NUMBERS = {
    "6354013541",
    "9313565791",
    "9978463026",
    "8679678741",
}

RESTRICTED_TG_IDS = {
    "6653985765",
    "8051539455",
    "7272787842",
    "8221567311",
}

SEMAPHORE = asyncio.Semaphore(35)
HTTP_CLIENT: Optional[httpx.AsyncClient] = None

USER_SPAM_MAP = {}
USER_FREEZE_MAP = {}
ADMIN_STATE = {}

# ============================================================
# EXTERNAL APIS CONFIG
# ============================================================

NUMBER_API_URL = "https://reuters-memorabilia-insulin-disclose.trycloudflare.com/num"
NUMBER_API_KEY = os.getenv("NUMBER_API_KEY", "")

VEHICLE_API_URL = "https://rajfflivebot.onrender.com/pub/rajfflive/vnum"
VEHICLE_API_KEY = os.getenv("VEHICLE_API_KEY", "")

ADHAR_API_URL = "https://rajfflivebot.onrender.com/pub/rajfflive/adhar"
ADHAR_API_KEY = os.getenv("ADHAR_API_KEY", "")

TG_TO_NUM_PRIMARY = "https://tg-to-num.backemdhub.workers.dev/"
TG_TO_NUM_BACKUP = "https://ftosint.world/api/tg?key=ravixnobita&info="

GMAIL_PRIMARY = "https://rack-72au.onrender.com/gmail-info"
GMAIL_BACKUP = "https://ftosint.world/api/email?key=ravixnobita&email="

TRUECALLER_API_URL = "https://rack-72au.onrender.com/truecaller"
PINCODE_API_URL = "https://rack-pincodeapi.vercel.app/api"
IFSC_API_URL = "https://vercei-kappa.vercel.app/ifsc"
IP_API_URL = "https://ip-dwy8.onrender.com/api/rackipapi"
WEATHER_API_BASE_URL = "https://rack-weather.vercel.app/api/weather"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("OBSIDIAN_TRACE")

# ============================================================
# TIME HELPERS
# ============================================================

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def iso_now() -> str:
    return now_utc().isoformat()

def today_key() -> str:
    return now_utc().date().isoformat()

def parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None

# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE, timeout=45.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=45000;")
    conn.execute("PRAGMA mmap_size=134217728;")
    conn.execute("PRAGMA cache_size=-16000;")
    return conn

def column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)

def add_column_if_missing(conn, table: str, column: str, definition: str):
    if not column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

def init_db():
    conn = db_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                is_banned INTEGER DEFAULT 0,
                is_unlimited INTEGER DEFAULT 0,
                custom_private_limit INTEGER DEFAULT -1,
                custom_group_limit INTEGER DEFAULT -1,
                one_day_credits INTEGER DEFAULT 0,
                plan_id INTEGER,
                plan_name TEXT,
                plan_started_at TEXT,
                plan_expires_at TEXT,
                plan_total_uses INTEGER DEFAULT 0,
                plan_used_uses INTEGER DEFAULT 0,
                daily_private_used INTEGER DEFAULT 0,
                daily_group_used INTEGER DEFAULT 0,
                referral_credits INTEGER DEFAULT 0,
                referred_by INTEGER,
                daily_date TEXT,
                total_searches INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                days INTEGER NOT NULL,
                uses INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tracked_groups (
                group_id INTEGER PRIMARY KEY,
                group_title TEXT,
                total_searches INTEGER DEFAULT 0,
                last_active TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS force_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                invite_link TEXT NOT NULL
            )
            """
        )

        add_column_if_missing(conn, "users", "is_unlimited", "INTEGER DEFAULT 0")
        add_column_if_missing(conn, "users", "custom_private_limit", "INTEGER DEFAULT -1")
        add_column_if_missing(conn, "users", "custom_group_limit", "INTEGER DEFAULT -1")
        add_column_if_missing(conn, "users", "one_day_credits", "INTEGER DEFAULT 0")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_banned ON users(is_banned);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_daily_date ON users(daily_date);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tracked_searches ON tracked_groups(total_searches DESC);")

        defaults = {
            "bot_enabled": "1",
            "force_join_enabled": "1",
            "private_limit": str(DEFAULT_PRIVATE_LIMIT),
            "group_limit": str(DEFAULT_GROUP_LIMIT),
            "referral_bonus": str(DEFAULT_REFERRAL_BONUS),
            "freeze_minutes": str(DEFAULT_FREEZE_MINUTES),
            "audit_log_channel": str(AUDIT_LOG_CHANNEL_ID),
            "admin_1": str(ADMIN_ID_1),
            "admin_2": str(ADMIN_ID_2),
            "welcome_text": "",
            "welcome_media_id": "",
            "welcome_media_type": "",
            "api_num": "1",
            "api_vehicle": "1",
            "api_adh": "1",
            "api_tg": "1",
            "api_gm": "1",
            "api_tc": "1",
            "api_pin": "1",
            "api_ifsc": "1",
            "api_ip": "1",
            "api_weather": "1",
        }

        for key, value in defaults.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO settings (key, value)
                VALUES (?, ?)
                """,
                (key, value),
            )

        conn.execute(
            """
            INSERT OR IGNORE INTO force_channels (username, invite_link)
            VALUES (?, ?)
            """,
            ("@KRUTIK_OSINT", "https://t.me/KRUTIK_OSINT"),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO force_channels (username, invite_link)
            VALUES (?, ?)
            """,
            ("@pulkit_osint", "https://t.me/pulkit_osint"),
        )

        conn.commit()
    finally:
        conn.close()

# ============================================================
# SETTINGS ENGINE
# ============================================================

def get_setting(key: str, default: str = "") -> str:
    conn = db_connection()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()

def set_setting(key: str, value: str):
    conn = db_connection()
    try:
        conn.execute(
            """
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, str(value)),
        )
        conn.commit()
    finally:
        conn.close()

def get_int_setting(key: str, default: int) -> int:
    try:
        return int(get_setting(key, str(default)))
    except Exception:
        return default

def bot_enabled() -> bool:
    return get_setting("bot_enabled", "1") == "1"

def force_join_active() -> bool:
    return get_setting("force_join_enabled", "1") == "1"

def api_is_active(api_name: str) -> bool:
    return get_setting(f"api_{api_name}", "1") == "1"

def toggle_api_status(api_name: str) -> bool:
    new_val = "0" if api_is_active(api_name) else "1"
    set_setting(f"api_{api_name}", new_val)
    return new_val == "1"

def get_private_limit() -> int:
    return get_int_setting("private_limit", DEFAULT_PRIVATE_LIMIT)

def get_group_limit() -> int:
    return get_int_setting("group_limit", DEFAULT_GROUP_LIMIT)

def get_referral_bonus() -> int:
    return get_int_setting("referral_bonus", DEFAULT_REFERRAL_BONUS)

def get_freeze_minutes() -> int:
    return get_int_setting("freeze_minutes", DEFAULT_FREEZE_MINUTES)

def get_audit_channel() -> int:
    return get_int_setting("audit_log_channel", AUDIT_LOG_CHANNEL_ID)

# ============================================================
# AUDIT LOGGING
# ============================================================

async def send_audit_log(context: ContextTypes.DEFAULT_TYPE, log_text: str):
    log_ch = get_audit_channel()
    if not log_ch or log_ch == 0:
        return
    try:
        await context.bot.send_message(
            chat_id=log_ch,
            text=log_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as exc:
        logger.warning("Surveillance log forwarding failed: %s", exc)

def dispatch_audit_log(context: ContextTypes.DEFAULT_TYPE, log_text: str):
    asyncio.create_task(send_audit_log(context, log_text))

# ============================================================
# ADMIN AUTHENTICATION
# ============================================================

def get_admin_ids() -> set[int]:
    ids = set()
    adm1 = get_int_setting("admin_1", ADMIN_ID_1)
    adm2 = get_int_setting("admin_2", ADMIN_ID_2)
    if adm1:
        ids.add(adm1)
    if adm2:
        ids.add(adm2)
    return ids

def is_admin(user_id: int) -> bool:
    return user_id in get_admin_ids()

async def require_admin(update: Update) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    if not user or not is_admin(user.id):
        if update.message:
            await update.message.reply_text(f"{EMOJI_CROSS} Unauthorized access.", parse_mode=ParseMode.HTML)
        return False
    if chat and chat.type != "private":
        if update.message:
            await update.message.reply_text("🔒 Admin panel operates exclusively in private chat.")
        return False
    ensure_user(user)
    return True

# ============================================================
# FLOOD CONTROL
# ============================================================

def check_spam_and_freeze(user_id: int) -> tuple[bool, int]:
    if is_admin(user_id):
        return False, 0

    now_t = now_utc()
    if user_id in USER_FREEZE_MAP:
        unfreeze_time = USER_FREEZE_MAP[user_id]
        if now_t < unfreeze_time:
            rem_seconds = int((unfreeze_time - now_t).total_seconds())
            rem_mins = max(1, rem_seconds // 60)
            return True, rem_mins
        else:
            del USER_FREEZE_MAP[user_id]
            USER_SPAM_MAP.pop(user_id, None)

    history = USER_SPAM_MAP.get(user_id, [])
    cutoff = now_t - timedelta(seconds=10)
    history = [t for t in history if t > cutoff]
    history.append(now_t)
    USER_SPAM_MAP[user_id] = history

    if len(history) > 8:
        freeze_mins = get_freeze_minutes()
        USER_FREEZE_MAP[user_id] = now_t + timedelta(minutes=freeze_mins)
        return True, freeze_mins

    return False, 0

# ============================================================
# USERS & TRACKING
# ============================================================

def ensure_user(user, referrer_id: Optional[int] = None) -> tuple[bool, Optional[int]]:
    if not user:
        return False, None
    conn = db_connection()
    awarded_referrer = None
    try:
        row = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user.id,)).fetchone()
        cur_iso = iso_now()

        if row is None:
            valid_referrer = None
            if referrer_id and referrer_id != user.id:
                ref_user = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (referrer_id,)).fetchone()
                if ref_user:
                    valid_referrer = referrer_id

            conn.execute(
                """
                INSERT INTO users (
                    user_id, username, first_name, last_name,
                    daily_private_used, daily_group_used, referral_credits,
                    referred_by, daily_date, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 0, 0, 0, ?, ?, ?, ?)
                """,
                (
                    user.id,
                    user.username,
                    user.first_name,
                    user.last_name,
                    valid_referrer,
                    today_key(),
                    cur_iso,
                    cur_iso,
                ),
            )

            if valid_referrer:
                bonus = get_referral_bonus()
                conn.execute(
                    """
                    UPDATE users
                    SET referral_credits = referral_credits + ?,
                        updated_at = ?
                    WHERE user_id = ?
                    """,
                    (bonus, cur_iso, valid_referrer),
                )
                awarded_referrer = valid_referrer

            conn.commit()
            return True, awarded_referrer
        else:
            conn.execute(
                """
                UPDATE users
                SET username = ?, first_name = ?, last_name = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (user.username, user.first_name, user.last_name, cur_iso, user.id),
            )
            conn.commit()
            return False, None
    finally:
        conn.close()

def get_user(user_id: int):
    conn = db_connection()
    try:
        return conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    finally:
        conn.close()

def reset_daily_usage_if_needed(user_id: int):
    today = today_key()
    conn = db_connection()
    try:
        row = conn.execute("SELECT daily_date FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row and row["daily_date"] != today:
            conn.execute(
                """
                UPDATE users
                SET daily_private_used = 0,
                    daily_group_used = 0,
                    one_day_credits = 0,
                    daily_date = ?,
                    updated_at = ?
                WHERE user_id = ?
                """,
                (today, iso_now(), user_id),
            )
            conn.commit()
    finally:
        conn.close()

def record_group_activity(chat):
    if not chat or chat.type not in ("group", "supergroup"):
        return
    conn = db_connection()
    try:
        conn.execute(
            """
            INSERT INTO tracked_groups (group_id, group_title, total_searches, last_active)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(group_id) DO UPDATE SET
                group_title = excluded.group_title,
                total_searches = total_searches + 1,
                last_active = excluded.last_active
            """,
            (chat.id, chat.title or "Untitled Group", iso_now()),
        )
        conn.commit()
    finally:
        conn.close()

# ============================================================
# FORCE JOIN CHANNELS
# ============================================================

def get_force_channels() -> list[sqlite3.Row]:
    conn = db_connection()
    try:
        return conn.execute("SELECT * FROM force_channels ORDER BY id ASC").fetchall()
    finally:
        conn.close()

def add_force_channel(username: str, invite_link: str) -> bool:
    if not username.startswith("@"):
        username = f"@{username}"
    conn = db_connection()
    try:
        conn.execute("INSERT INTO force_channels (username, invite_link) VALUES (?, ?)", (username, invite_link))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def remove_force_channel(channel_id: int):
    conn = db_connection()
    try:
        conn.execute("DELETE FROM force_channels WHERE id = ?", (channel_id,))
        conn.commit()
    finally:
        conn.close()

async def check_single_member(bot, chat_id: str, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        if member.status in (ChatMember.LEFT, ChatMember.BANNED, "kicked"):
            return False
        return True
    except Exception as exc:
        logger.warning("Verification check failure on %s for %s: %s", chat_id, user_id, exc)
        return False

async def is_user_verified(bot, user_id: int) -> bool:
    if is_admin(user_id) or not force_join_active():
        return True
    channels = get_force_channels()
    if not channels:
        return True
    tasks = [check_single_member(bot, ch["username"], user_id) for ch in channels]
    results = await asyncio.gather(*tasks)
    return all(results)

# ============================================================
# PLANS MANAGEMENT
# ============================================================

def get_plan(plan_id: int):
    conn = db_connection()
    try:
        return conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
    finally:
        conn.close()

def list_plans():
    conn = db_connection()
    try:
        return conn.execute("SELECT * FROM plans ORDER BY id ASC").fetchall()
    finally:
        conn.close()

def create_plan(name: str, days: int, uses: int):
    conn = db_connection()
    try:
        cur = conn.execute("INSERT INTO plans (name, days, uses, created_at) VALUES (?, ?, ?, ?)", (name, days, uses, iso_now()))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()

def delete_plan(plan_id: int):
    conn = db_connection()
    try:
        conn.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
        conn.commit()
    finally:
        conn.close()

def assign_plan(user_id: int, plan_id: int):
    plan = get_plan(plan_id)
    if not plan:
        return False, "Plan not found."
    start_time = now_utc()
    expire_time = start_time + timedelta(days=plan["days"])
    conn = db_connection()
    try:
        conn.execute(
            """
            UPDATE users
            SET plan_id = ?, plan_name = ?, plan_started_at = ?,
                plan_expires_at = ?, plan_total_uses = ?, plan_used_uses = 0,
                updated_at = ?
            WHERE user_id = ?
            """,
            (
                plan["id"],
                plan["name"],
                start_time.isoformat(),
                expire_time.isoformat(),
                plan["uses"],
                iso_now(),
                user_id,
            ),
        )
        conn.commit()
        return True, f"Plan <code>{html.escape(plan['name'])}</code> assigned."
    finally:
        conn.close()

def revoke_plan(user_id: int):
    conn = db_connection()
    try:
        conn.execute(
            """
            UPDATE users
            SET plan_id = NULL, plan_name = NULL, plan_started_at = NULL,
                plan_expires_at = NULL, plan_total_uses = 0, plan_used_uses = 0,
                updated_at = ?
            WHERE user_id = ?
            """,
            (iso_now(), user_id),
        )
        conn.commit()
    finally:
        conn.close()

def plan_is_active(user_row) -> bool:
    if not user_row or not user_row["plan_id"]:
        return False
    expires = parse_iso(user_row["plan_expires_at"])
    if not expires or expires <= now_utc():
        return False
    if user_row["plan_total_uses"] <= user_row["plan_used_uses"]:
        return False
    return True

# ============================================================
# UI FORMATTERS & ANIMATED CARDS
# ============================================================

def make_bar(current: int, total: int, length: int = 8) -> str:
    if total <= 0:
        return "■" * length
    fraction = min(max(current / total, 0.0), 1.0)
    filled = int(fraction * length)
    return "■" * filled + "□" * (length - filled)

def format_status_card(row, user) -> str:
    p_lim = row["custom_private_limit"] if row["custom_private_limit"] >= 0 else get_private_limit()
    g_lim = row["custom_group_limit"] if row["custom_group_limit"] >= 0 else get_group_limit()

    p_used = row["daily_private_used"]
    g_used = row["daily_group_used"]

    p_bar = make_bar(p_used, p_lim) if p_lim > 0 else "■" * 8
    g_bar = make_bar(g_used, g_lim) if g_lim > 0 else "■" * 8

    plan_title = "None (Free Tier)"
    plan_quota = "N/A"
    plan_expiry = "N/A"

    if row["is_unlimited"]:
        plan_title = f"{EMOJI_LIGHTNING} UNLIMITED MASTER ACCESS"
        plan_quota = "Unlimited"
        plan_expiry = "Lifetime"
    elif row["plan_id"]:
        plan_title = row["plan_name"] or "Active Plan"
        rem_plan = max(0, row["plan_total_uses"] - row["plan_used_uses"])
        plan_quota = f"{rem_plan} / {row['plan_total_uses']}"
        exp = parse_iso(row["plan_expires_at"])
        plan_expiry = exp.strftime("%d %b %Y, %H:%M UTC") if exp else "Unknown"

    text = (
        f"┌───「 {EMOJI_SHIELD} <b>{BRAND}</b> 」───\n"
        f"│ {EMOJI_USER} <b>Operative:</b> {html.escape(user.first_name or 'User')}\n"
        f"│ 🆔 <b>ID:</b> <code>{user.id}</code>\n"
        f"│ 🚫 <b>Banned:</b> {'YES ' + EMOJI_CROSS if row['is_banned'] else 'NO ' + EMOJI_CHECK}\n"
        f"├───「 {EMOJI_LIGHTNING} <b>USAGE MATRIX</b> 」───\n"
        f"│ 💬 <b>Private Daily:</b> <code>[{p_bar}]</code> {p_used}/{p_lim if p_lim > 0 else '∞'}\n"
        f"│ 👥 <b>Group Daily:</b>   <code>[{g_bar}]</code> {g_used}/{g_lim if g_lim > 0 else '∞'}\n"
        f"│ 🎟 <b>1-Day Temporary Credits:</b> <code>{row['one_day_credits']}</code>\n"
        f"│ 🎁 <b>Referral Credits:</b> <code>{row['referral_credits']}</code>\n"
        f"│ 📈 <b>Total Operations:</b> <code>{row['total_searches']}</code>\n"
        f"├───「 📦 <b>SUBSCRIPTION</b> 」───\n"
        f"│ 🏷 <b>Plan:</b> {html.escape(plan_title)}\n"
        f"│ 🔢 <b>Plan Quota:</b> {plan_quota}\n"
        f"│ ⏳ <b>Valid Till:</b> {plan_expiry}\n"
        f"└──────────────────────────────"
    )
    return text

def format_result_card(data_content: str) -> str:
    return (
        f"┌───「 {EMOJI_SEARCH} <b>INTELLIGENCE REPORT</b> 」───\n"
        f"│\n"
        f"<pre>{html.escape(data_content)}</pre>\n"
        f"│\n"
        f"├───「 {EMOJI_SHIELD} <b>POWERED BY {BRAND}</b> 」\n"
        f"│ {EMOJI_LIGHTNING} <i>@pulkitinfobot</i>\n"
        f"│ {EMOJI_CROWN} <b>@KRUTIK_CYBER_DEVELOPER0</b>\n"
        f"└──────────────────────────────────"
    )

# ============================================================
# ACCESS CONTROLLER
# ============================================================

async def check_search_access(update: Update, context: ContextTypes.DEFAULT_TYPE, api_cmd: str) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return False

    ensure_user(user)
    reset_daily_usage_if_needed(user.id)
    record_group_activity(chat)

    is_frozen, rem_mins = check_spam_and_freeze(user.id)
    if is_frozen:
        if update.message:
            await update.message.reply_text(
                f"┌───「 {EMOJI_WARN} <b>FLOOD CONTROL ENGAGED</b> 」───\n"
                f"│ Excessive query requests detected!\n"
                f"│ Terminal frozen for <b>{rem_mins} minute(s)</b>.\n"
                f"└────────────────────────────────────────",
                parse_mode=ParseMode.HTML,
            )
        return False

    if is_admin(user.id):
        return True

    row = get_user(user.id)
    if not row:
        return False

    if row["is_banned"]:
        if update.message:
            await update.message.reply_text(f"{EMOJI_CROSS} <b>Access Revoked:</b> You are permanently blacklisted.", parse_mode=ParseMode.HTML)
        return False

    if not bot_enabled():
        if update.message:
            await update.message.reply_text("🔴 <b>System Offline:</b> Maintenance in progress.", parse_mode=ParseMode.HTML)
        return False

    if not api_is_active(api_cmd):
        if update.message:
            await update.message.reply_text(f"{EMOJI_WARN} <b>Suspended:</b> <code>/{api_cmd}</code> disabled by admin.", parse_mode=ParseMode.HTML)
        return False

    verified = await is_user_verified(context.bot, user.id)
    if not verified:
        channels = get_force_channels()
        ch_list = "\n".join([f"• {c['username']} ➔ {c['invite_link']}" for c in channels])
        if update.message:
            await update.message.reply_text(
                f"┌───「 {EMOJI_WARN} <b>CHANNEL VERIFICATION REQUIRED</b> 」───\n"
                f"│ Please subscribe to official channels:\n\n{ch_list}\n\n"
                f"│ Tap /start once joined to unlock access.\n"
                f"└────────────────────────────────────────",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        return False

    if row["is_unlimited"]:
        return True

    is_private = (chat.type == "private")
    limit = row["custom_private_limit"] if (is_private and row["custom_private_limit"] >= 0) else (get_private_limit() if is_private else get_group_limit())
    if not is_private and row["custom_group_limit"] >= 0:
        limit = row["custom_group_limit"]

    used = row["daily_private_used"] if is_private else row["daily_group_used"]

    if limit == 0 or used < limit:
        return True

    if row["one_day_credits"] > 0 or row["referral_credits"] > 0 or plan_is_active(row):
        return True

    if update.message:
        await update.message.reply_text(
            f"┌───「 {EMOJI_CROSS} <b>SEARCH LIMIT EXHAUSTED</b> 」───\n"
            f"│ Daily search balance is complete.\n"
            f"├───「 {EMOJI_CROWN} <b>CONTACT ADMINS</b> 」───\n"
            f"│ {EMOJI_LIGHTNING} <b>{OWNER_CONTACTS}</b>\n"
            f"└────────────────────────────────────────",
            parse_mode=ParseMode.HTML,
        )
    return False

def consume_search(user_id: int, is_private: bool):
    if is_admin(user_id):
        return

    reset_daily_usage_if_needed(user_id)
    conn = db_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            return

        cur_iso = iso_now()
        limit = row["custom_private_limit"] if (is_private and row["custom_private_limit"] >= 0) else (get_private_limit() if is_private else get_group_limit())
        if not is_private and row["custom_group_limit"] >= 0:
            limit = row["custom_group_limit"]

        used = row["daily_private_used"] if is_private else row["daily_group_used"]

        if limit == 0 or used < limit:
            col = "daily_private_used" if is_private else "daily_group_used"
            conn.execute(f"UPDATE users SET {col} = {col} + 1, total_searches = total_searches + 1, updated_at = ? WHERE user_id = ?", (cur_iso, user_id))
        elif row["one_day_credits"] > 0:
            conn.execute("UPDATE users SET one_day_credits = one_day_credits - 1, total_searches = total_searches + 1, updated_at = ? WHERE user_id = ?", (cur_iso, user_id))
        elif row["referral_credits"] > 0:
            conn.execute("UPDATE users SET referral_credits = referral_credits - 1, total_searches = total_searches + 1, updated_at = ? WHERE user_id = ?", (cur_iso, user_id))
        else:
            conn.execute("UPDATE users SET plan_used_uses = plan_used_uses + 1, total_searches = total_searches + 1, updated_at = ? WHERE user_id = ?", (cur_iso, user_id))
        conn.commit()
    finally:
        conn.close()

# ============================================================
# RESPONSE SANITIZATION & BLOCKLIST
# ============================================================

REPLACEMENT_TARGET = "@pulkitinfobot,@KRUTIK_CYBER_DEVELOPER0"
SENSITIVE_REPLACEMENTS = [
    "@pulkitinfobot,@KRUTIK_CYBER_DEVELOPER5",
    "@KRUTIK_CYBER_DEVELOPER5BOT",
    "@BackemdHub",
    "CREDIT / INFO Owner: @shiva_158 Free API: @Osintinfooobot Free API ke liye Channel Join karein: https://t.me/osintinfoooo For Any Kind of API: @shiva_158",
    "@Osintinfooobot",
    "https://t.me/osintinfoooo",
    "@shiva_158",
    "@YeuIin",
    "@kihoerack",
    "@ftgamer2",
    "@RAJFFLIVE",
    "https://t.me/+QUg-JvyJizkxMzA1",
    "@RAJFFLIVEBOT",
    "@rajfflivebot",
    "@rajfflive",
    "t.me/AbyssOsintToolBot",
]

def sanitize_response(text: str) -> str:
    if not text:
        return text
    for old_val in SENSITIVE_REPLACEMENTS:
        text = re.sub(re.escape(old_val), REPLACEMENT_TARGET, text, flags=re.IGNORECASE)
    return text

def is_empty_payload(data) -> bool:
    if data is None:
        return True
    if isinstance(data, (dict, list)) and len(data) == 0:
        return True
    if isinstance(data, str):
        cleaned = data.strip().lower()
        if cleaned in ("", "null", "none", "{}", "[]", "not found", "no data found", "record not found", "error"):
            return True
        if "usage" in cleaned and "api/tg" in cleaned:
            return True
    if isinstance(data, dict):
        if "usage" in data and ("api/tg" in str(data["usage"]).lower() or "6858648491" in str(data)):
            return True
        if data.get("found") is False:
            return True
        if data.get("count") == 0:
            return True
        if "result" in data and is_empty_payload(data.get("result")):
            return True
        if "data" in data and is_empty_payload(data.get("data")):
            return True
        if data.get("status") in (False, "failed", "error"):
            return True
    return False

def format_json_response(raw_text: str) -> str:
    cleaned = sanitize_response(raw_text.strip())
    if not cleaned or is_empty_payload(cleaned):
        return "NOT FOUND"
    try:
        data = json.loads(cleaned)
        if is_empty_payload(data):
            return "NOT FOUND"
        return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception:
        return cleaned

async def send_result(update: Update, result: str):
    if not update.message:
        return
    card = format_result_card(result)
    if len(card) <= MAX_MESSAGE_LENGTH:
        try:
            await update.message.reply_text(card, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            return
        except Exception:
            pass

    chunks = []
    start_pos = 0
    while start_pos < len(result):
        end_pos = min(start_pos + 3500, len(result))
        chunks.append(result[start_pos:end_pos])
        start_pos = end_pos
    for idx, c in enumerate(chunks, 1):
        await update.message.reply_text(
            f"<b>[PART {idx}/{len(chunks)}]</b>\n<pre>{html.escape(c)}</pre>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

# ============================================================
# HTTP DISPATCHER
# ============================================================

async def fetch_endpoint(url: str, params: dict) -> tuple[Optional[str], Optional[dict], str]:
    global HTTP_CLIENT
    async with SEMAPHORE:
        try:
            if HTTP_CLIENT is None or HTTP_CLIENT.is_closed:
                HTTP_CLIENT = httpx.AsyncClient(
                    timeout=REQUEST_TIMEOUT,
                    headers=BROWSER_HEADERS,
                    follow_redirects=True,
                )
            resp = await HTTP_CLIENT.get(url, params=params)
            if resp.status_code in (404, 400, 422, 500, 502, 503):
                return None, None, f"HTTP_{resp.status_code}"
            resp.raise_for_status()
            raw = resp.text.strip()
            if not raw or is_empty_payload(raw):
                return None, None, "EMPTY"
            try:
                parsed = json.loads(raw)
                if is_empty_payload(parsed):
                    return None, None, "EMPTY_JSON"
                return raw, parsed, "SUCCESS"
            except Exception:
                return raw, None, "RAW_SUCCESS"
        except (httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException):
            return None, None, "TIMEOUT_OR_FAULT"
        except Exception as exc:
            logger.exception("Fetch error on %s: %s", url, exc)
            return None, None, "FAULT"

async def execute_api_search(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str, params: dict, cmd_name: str, target_val: str):
    user = update.effective_user
    chat = update.effective_chat
    searching_msg = None

    if update.message:
        try:
            searching_msg = await update.message.reply_text(f"{EMOJI_LIGHTNING} <code>Connecting to decentralized nodes... querying ⏳</code>", parse_mode=ParseMode.HTML)
        except Exception:
            pass

    raw_text, _, status = await fetch_endpoint(url, params)
    formatted_output = "NOT FOUND"
    log_status = status

    if raw_text:
        formatted_output = format_json_response(raw_text)
        if formatted_output != "NOT FOUND":
            log_status = "SUCCESS"
            if user and not is_admin(user.id):
                consume_search(user.id, (chat.type == "private") if chat else True)
        else:
            log_status = "NOT FOUND"

    if searching_msg:
        try:
            await searching_msg.delete()
        except Exception:
            pass

    if user:
        c_title = "DM (Personal)" if (chat and chat.type == "private") else (chat.title or "Group")
        audit_msg = (
            f"┌───「 {EMOJI_RADAR} <b>SURVEILLANCE TELEMETRY</b> 」───\n"
            f"│ {EMOJI_USER} <b>Operative:</b> {html.escape(user.first_name)} (<code>{user.id}</code>)\n"
            f"│ 🏷 <b>Handle:</b> @{html.escape(user.username or 'none')}\n"
            f"│ {EMOJI_LIGHTNING} <b>Command:</b> <code>/{cmd_name}</code>\n"
            f"│ 🎯 <b>Target:</b> <code>{html.escape(target_val)}</code>\n"
            f"│ 📍 <b>Origin:</b> {html.escape(c_title)}\n"
            f"│ 📊 <b>Status:</b> <code>{log_status}</code>\n"
            f"└────────────────────────────────────────"
        )
        dispatch_audit_log(context, audit_msg)

    await send_result(update, formatted_output)

# ============================================================
# USER COMMAND HANDLERS
# ============================================================

def default_welcome_text(user) -> str:
    admin_tag = f"{EMOJI_CROWN} <b>Admin Status:</b> Unlimited Access Active\n" if is_admin(user.id) else ""
    return (
        f"┌───「 {EMOJI_SHIELD} <b>{BRAND}</b> 」───\n"
        f"│ 👋 <b>Greetings Operative:</b> {html.escape(user.first_name or 'User')}\n"
        f"│ 🆔 <b>Client ID:</b> <code>{user.id}</code>\n"
        f"│ {admin_tag}"
        f"├───「 🎁 <b>FREE SEARCH QUOTA</b> 」───\n"
        f"│ 💬 <b>Personal DM:</b> 3 Searches / Day\n"
        f"│ 👥 <b>Any Group:</b>   4 Searches / Day\n"
        f"├───「 {EMOJI_FIRE} <b>ALL PROTOCOLS &amp; COMMANDS</b> 」───\n"
        f"│ 1. <code>/start</code> - Restart terminal\n"
        f"│ 2. <code>/num &lt;val&gt;</code> - Mobile Search (10-Digit)\n"
        f"│ 3. <code>/vehicle &lt;rc&gt;</code> - Vehicle RC Lookup\n"
        f"│ 4. <code>/adh &lt;val&gt;</code> - ID Record Lookup\n"
        f"│ 5. <code>/tg &lt;id|username&gt;</code> - Telegram ID/User (Auto-Num Intel)\n"
        f"│ 6. <code>/gm &lt;email&gt;</code> - Gmail Account Lookup (Dual Node)\n"
        f"│ 7. <code>/tc &lt;val&gt;</code> - Truecaller Intelligence\n"
        f"│ 8. <code>/pin &lt;code&gt;</code> - Postal PIN Directory\n"
        f"│ 9. <code>/ifsc &lt;code&gt;</code> - Bank Branch Lookup\n"
        f"│ 10. <code>/ip &lt;ip&gt;</code> - IP Geolocation Intel\n"
        f"│ 11. <code>/weather &lt;city&gt;</code> - Realtime Weather Intel\n"
        f"│ 12. <code>/ref</code> - Recruitment Referral Link\n"
        f"│ 13. <code>/status</code> - Real-time Limits &amp; Quota\n"
        f"│ 14. <code>/help</code> - Full Documentation\n"
        f"└───「 {EMOJI_CROWN} <b>SUPPORT &amp; CREDITS</b> 」───\n"
        f"│ {EMOJI_LIGHTNING} Contact: {OWNER_CONTACTS}\n"
        f"└──────────────────────────────\n\n"
        f"{EMOJI_LIGHTNING} <i>Tap the Menu button on input bar for instant commands!</i>"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user = update.effective_user
    chat = update.effective_chat
    if not user:
        return

    referrer_id = None
    if context.args and context.args[0].isdigit():
        referrer_id = int(context.args[0])

    is_new, awarded_to = ensure_user(user, referrer_id)
    record_group_activity(chat)

    if is_new and awarded_to:
        bonus = get_referral_bonus()
        try:
            await context.bot.send_message(
                chat_id=awarded_to,
                text=(
                    f"┌───「 🎉 <b>RECRUITMENT BONUS AWARDED</b> 」───\n"
                    f"│ {EMOJI_USER} Operative <code>{user.id}</code> registered through your link.\n"
                    f"│ 🎁 <b>+{bonus} Extra Search Credit(s)</b> credited to your balance!\n"
                    f"└────────────────────────────────────────"
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    verified = await is_user_verified(context.bot, user.id)
    if not verified:
        channels = get_force_channels()
        ch_list = "\n".join([f"• {c['username']} ➔ {c['invite_link']}" for c in channels])
        await update.message.reply_text(
            f"┌───「 {EMOJI_SHIELD} <b>{BRAND}</b> 」───\n"
            f"│ 🔒 <b>ACCESS DENIED: Dual Subscription Required!</b>\n"
            f"├───「 <b>MANDATORY CHANNELS</b> 」───\n"
            f"{ch_list}\n\n"
            f"Join both channels, then send /start again to proceed.\n"
            f"└──────────────────────────────",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return

    w_text = get_setting("welcome_text")
    if not w_text:
        caption = default_welcome_text(user)
    else:
        caption = (
            w_text.replace("{name}", html.escape(user.first_name or ""))
            .replace("{id}", str(user.id))
            .replace("{mention}", f"<a href='tg://user?id={user.id}'>{html.escape(user.first_name or 'User')}</a>")
        )

    m_id = get_setting("welcome_media_id")
    m_type = get_setting("welcome_media_type")

    if m_id and m_type == "video":
        try:
            await update.message.reply_video(video=m_id, caption=caption, parse_mode=ParseMode.HTML)
            return
        except Exception:
            pass
    elif m_id and m_type == "photo":
        try:
            await update.message.reply_photo(photo=m_id, caption=caption, parse_mode=ParseMode.HTML)
            return
        except Exception:
            pass

    await update.message.reply_text(caption, parse_mode=ParseMode.HTML)

async def ref_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user = update.effective_user
    if not user:
        return

    ensure_user(user)
    bot_info = await context.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user.id}"
    row = get_user(user.id)
    ref_credits = row["referral_credits"] if row else 0
    bonus = get_referral_bonus()

    card = (
        f"┌───「 👥 <b>ALLIED RECRUITMENT</b> 」───\n"
        f"│ Share your unique transmission link.\n"
        f"│ Each successful recruit provides <b>+{bonus} Extra Search Credit(s)</b>!\n"
        f"├───「 <b>TRANSMISSION LINK</b> 」───\n"
        f"│ 🔗 <b>Your Link:</b>\n"
        f"│ <code>{ref_link}</code>\n"
        f"├───「 <b>ACTIVE CREDITS</b> 」───\n"
        f"│ 🎁 <b>Available Referral Balance:</b> <code>{ref_credits}</code> Searches\n"
        f"└────────────────────────────────"
    )
    await update.message.reply_text(card, parse_mode=ParseMode.HTML)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user = update.effective_user
    if not user:
        return

    ensure_user(user)
    reset_daily_usage_if_needed(user.id)
    row = get_user(user.id)
    if not row:
        return

    card = format_status_card(row, user)
    await update.message.reply_text(card, parse_mode=ParseMode.HTML)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    text = (
        f"┌───「 📚 <b>COMMAND DIRECTORY</b> 」───\n"
        f"│ 1. <code>/start</code> - Initialize terminal\n"
        f"│ 2. <code>/num &lt;val&gt;</code> - Mobile Search (Strict 10-Digit)\n"
        f"│ 3. <code>/vehicle &lt;rc&gt;</code> - Vehicle RC Registration Search\n"
        f"│ 4. <code>/adh &lt;val&gt;</code> - ID Record Lookup\n"
        f"│ 5. <code>/tg &lt;id|username&gt;</code> - Telegram ID/Handle to Mobile\n"
        f"│ 6. <code>/gm &lt;email&gt;</code> - Gmail Intelligence (Dual Node)\n"
        f"│ 7. <code>/tc &lt;val&gt;</code> - Truecaller Intelligence\n"
        f"│ 8. <code>/pin &lt;code&gt;</code> - Postal PIN Directory\n"
        f"│ 9. <code>/ifsc &lt;code&gt;</code> - Bank Branch Lookup\n"
        f"│ 10. <code>/ip &lt;ip&gt;</code> - IP Geolocation Intel\n"
        f"│ 11. <code>/weather &lt;city&gt;</code> - Live Weather Intel\n"
        f"│ 12. <code>/ref</code> - Recruitment Link\n"
        f"│ 13. <code>/status</code> - Live Account Balance\n"
        f"│ 14. <code>/help</code> - Documentation\n"
        f"├───「 {EMOJI_CROWN} <b>UPGRADE ACCESS</b> 」───\n"
        f"│ Contact: {OWNER_CONTACTS}\n"
        f"└──────────────────────────────"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ============================================================
# SEARCH PROTOCOLS
# ============================================================

async def num_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not await check_search_access(update, context, "num"):
        return
    if not context.args:
        await update.message.reply_text("<b>Syntax:</b> <code>/num &lt;10_digit_number&gt;</code>", parse_mode=ParseMode.HTML)
        return

    val = context.args[0].strip()
    if not re.fullmatch(r"\d{10}", val):
        await update.message.reply_text(
            f"┌───「 {EMOJI_CROSS} <b>INVALID NUMBER FORMAT</b> 」───\n"
            f"│ Mobile lookup requires exactly <b>10 digits</b>.\n"
            f"└────────────────────────────────────────",
            parse_mode=ParseMode.HTML,
        )
        return

    if val in RESTRICTED_QUERY_NUMBERS:
        await update.message.reply_text(f"{EMOJI_CROSS} Target identifier is protected under high-security classification.", parse_mode=ParseMode.HTML)
        return

    await execute_api_search(update, context, NUMBER_API_URL, {"number": val, "key": NUMBER_API_KEY}, "num", val)

async def vehicle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not await check_search_access(update, context, "vehicle"):
        return
    if not context.args:
        await update.message.reply_text("<b>Syntax:</b> <code>/vehicle &lt;vehicle_number&gt;</code>", parse_mode=ParseMode.HTML)
        return
    val = " ".join(context.args).strip().upper()
    await execute_api_search(update, context, VEHICLE_API_URL, {"num2r": val, "key": VEHICLE_API_KEY}, "vehicle", val)

async def adhar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not await check_search_access(update, context, "adh"):
        return
    if not context.args:
        await update.message.reply_text("<b>Syntax:</b> <code>/adh &lt;target_id&gt;</code>", parse_mode=ParseMode.HTML)
        return
    val = " ".join(context.args).strip()
    await execute_api_search(update, context, ADHAR_API_URL, {"num": val, "key": ADHAR_API_KEY}, "adh", val)

# ------------------------------------------------------------
# /tg (DUAL RESOLVER & AUTO-CHAINING ENGINE)
# ------------------------------------------------------------
async def tg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not await check_search_access(update, context, "tg"):
        return
    if not context.args:
        await update.message.reply_text("<b>Syntax:</b> <code>/tg &lt;id_or_username&gt;</code>", parse_mode=ParseMode.HTML)
        return

    raw_input = context.args[0].strip()
    target_id_str = raw_input

    # Username to ID Resolver
    if not raw_input.isdigit():
        uname = raw_input.lstrip("@")
        try:
            chat_obj = await context.bot.get_chat(f"@{uname}")
            target_id_str = str(chat_obj.id)
        except Exception:
            target_id_str = raw_input

    if not re.fullmatch(r"\d{5,16}", target_id_str):
        await update.message.reply_text(
            f"┌───「 {EMOJI_CROSS} <b>IDENTIFIER RESOLUTION FAILED</b> 」───\n"
            f"│ Could not resolve to a valid numeric Telegram ID.\n"
            f"│ <b>Format:</b> <code>/tg 6123456789</code> or <code>/tg @handle</code>\n"
            f"└──────────────────────────────",
            parse_mode=ParseMode.HTML,
        )
        return

    if target_id_str in RESTRICTED_TG_IDS:
        await update.message.reply_text(f"{EMOJI_CROSS} Telegram ID is protected under security protocols.", parse_mode=ParseMode.HTML)
        return

    user = update.effective_user
    chat = update.effective_chat
    searching_msg = None

    if update.message:
        try:
            searching_msg = await update.message.reply_text(f"{EMOJI_LIGHTNING} <code>Chaining nodes &amp; querying Telegram directory... ⏳</code>", parse_mode=ParseMode.HTML)
        except Exception:
            pass

    # Primary lookup
    raw_text, parsed_data, status = await fetch_endpoint(TG_TO_NUM_PRIMARY, {"tg": target_id_str})
    resolved_via = "PRIMARY"

    # Backup lookup
    if not raw_text or is_empty_payload(parsed_data or raw_text):
        backup_url = f"{TG_TO_NUM_BACKUP}{target_id_str}"
        raw_text, parsed_data, status = await fetch_endpoint(backup_url, {})
        resolved_via = "FAILOVER"

    extracted_number = None
    final_output = "NOT FOUND"
    log_status = status

    if raw_text and not is_empty_payload(parsed_data or raw_text):
        if isinstance(parsed_data, dict):
            for k in ("mobile", "number", "phone", "phone_number"):
                if parsed_data.get(k):
                    c_num = re.sub(r"\D", "", str(parsed_data[k]))
                    if len(c_num) >= 10:
                        extracted_number = c_num[-10:]
                        break

        num_raw, num_parsed = None, None
        if extracted_number and extracted_number != "6858648491":
            num_raw, num_parsed, _ = await fetch_endpoint(NUMBER_API_URL, {"number": extracted_number, "key": NUMBER_API_KEY})

        composite_report = {}
        composite_report["telegram_profile"] = parsed_data if parsed_data else raw_text
        if num_raw and not is_empty_payload(num_parsed or num_raw):
            composite_report["linked_mobile_intel"] = num_parsed if num_parsed else num_raw

        cleaned_json = sanitize_response(json.dumps(composite_report, indent=2, ensure_ascii=False))
        final_output = cleaned_json
        log_status = f"SUCCESS_{resolved_via}" + ("_CHAINED" if extracted_number else "")

        if user and not is_admin(user.id):
            consume_search(user.id, (chat.type == "private") if chat else True)

    if searching_msg:
        try:
            await searching_msg.delete()
        except Exception:
            pass

    if user:
        c_title = "DM (Personal)" if (chat and chat.type == "private") else (chat.title or "Group")
        audit_msg = (
            f"┌───「 {EMOJI_RADAR} <b>SURVEILLANCE TELEMETRY</b> 」───\n"
            f"│ {EMOJI_USER} <b>Operative:</b> {html.escape(user.first_name)} (<code>{user.id}</code>)\n"
            f"│ 🏷 <b>Handle:</b> @{html.escape(user.username or 'none')}\n"
            f"│ {EMOJI_LIGHTNING} <b>Command:</b> <code>/tg</code> (Auto-Chain Engine)\n"
            f"│ 🎯 <b>Target:</b> <code>{html.escape(target_id_str)}</code>\n"
            f"│ 📱 <b>Extracted Phone:</b> <code>{extracted_number or 'None'}</code>\n"
            f"│ 📍 <b>Origin:</b> {html.escape(c_title)}\n"
            f"│ 📊 <b>Status:</b> <code>{log_status}</code>\n"
            f"└────────────────────────────────────────"
        )
        dispatch_audit_log(context, audit_msg)

    await send_result(update, final_output)

# ------------------------------------------------------------
# /gm (GMAIL FAILOVER ENGINE)
# ------------------------------------------------------------
async def gmail_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not await check_search_access(update, context, "gm"):
        return
    if not context.args:
        await update.message.reply_text("<b>Syntax:</b> <code>/gm &lt;target_email&gt;</code>", parse_mode=ParseMode.HTML)
        return
    email = " ".join(context.args).strip()
    if "@" not in email or "." not in email:
        await update.message.reply_text(f"{EMOJI_CROSS} Provide a valid email format.", parse_mode=ParseMode.HTML)
        return

    user = update.effective_user
    chat = update.effective_chat
    searching_msg = None

    if update.message:
        try:
            searching_msg = await update.message.reply_text(f"{EMOJI_LIGHTNING} <code>Scanning email registries... ⏳</code>", parse_mode=ParseMode.HTML)
        except Exception:
            pass

    raw_text, _, status = await fetch_endpoint(GMAIL_PRIMARY, {"q": email})
    if not raw_text or is_empty_payload(raw_text):
        backup_url = f"{GMAIL_BACKUP}{email}"
        raw_text, _, status = await fetch_endpoint(backup_url, {})

    formatted_output = "NOT FOUND"
    log_status = status

    if raw_text:
        formatted_output = format_json_response(raw_text)
        if formatted_output != "NOT FOUND":
            log_status = "SUCCESS"
            if user and not is_admin(user.id):
                consume_search(user.id, (chat.type == "private") if chat else True)
        else:
            log_status = "NOT FOUND"

    if searching_msg:
        try:
            await searching_msg.delete()
        except Exception:
            pass

    if user:
        c_title = "DM (Personal)" if (chat and chat.type == "private") else (chat.title or "Group")
        audit_msg = (
            f"┌───「 {EMOJI_RADAR} <b>SURVEILLANCE TELEMETRY</b> 」───\n"
            f"│ {EMOJI_USER} <b>Operative:</b> {html.escape(user.first_name)} (<code>{user.id}</code>)\n"
            f"│ 🏷 <b>Handle:</b> @{html.escape(user.username or 'none')}\n"
            f"│ {EMOJI_LIGHTNING} <b>Command:</b> <code>/gm</code> (Dual Node)\n"
            f"│ 🎯 <b>Target:</b> <code>{html.escape(email)}</code>\n"
            f"│ 📍 <b>Origin:</b> {html.escape(c_title)}\n"
            f"│ 📊 <b>Status:</b> <code>{log_status}</code>\n"
            f"└────────────────────────────────────────"
        )
        dispatch_audit_log(context, audit_msg)

    await send_result(update, formatted_output)

async def truecaller_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not await check_search_access(update, context, "tc"):
        return
    if not context.args:
        await update.message.reply_text("<b>Syntax:</b> <code>/tc &lt;phone_number&gt;</code>", parse_mode=ParseMode.HTML)
        return
    number = " ".join(context.args).strip()
    await execute_api_search(update, context, TRUECALLER_API_URL, {"q": number}, "tc", number)

async def pin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not await check_search_access(update, context, "pin"):
        return
    if not context.args:
        await update.message.reply_text("<b>Syntax:</b> <code>/pin &lt;pincode&gt;</code>", parse_mode=ParseMode.HTML)
        return
    pin = " ".join(context.args).strip()
    if not re.fullmatch(r"\d{4,10}", pin):
        await update.message.reply_text(f"{EMOJI_CROSS} Postal code must be numeric digits.", parse_mode=ParseMode.HTML)
        return
    await execute_api_search(update, context, PINCODE_API_URL, {"search": pin}, "pin", pin)

async def ifsc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not await check_search_access(update, context, "ifsc"):
        return
    if not context.args:
        await update.message.reply_text("<b>Syntax:</b> <code>/ifsc &lt;ifsc_code&gt;</code>", parse_mode=ParseMode.HTML)
        return
    code = " ".join(context.args).strip().upper()
    await execute_api_search(update, context, IFSC_API_URL, {"code": code}, "ifsc", code)

async def ip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not await check_search_access(update, context, "ip"):
        return
    if not context.args:
        await update.message.reply_text("<b>Syntax:</b> <code>/ip &lt;ip_address&gt;</code>", parse_mode=ParseMode.HTML)
        return
    ip_val = " ".join(context.args).strip()
    await execute_api_search(update, context, IP_API_URL, {"ip": ip_val}, "ip", ip_val)

async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not await check_search_access(update, context, "weather"):
        return
    if not context.args:
        await update.message.reply_text("<b>Syntax:</b> <code>/weather &lt;city&gt;</code>", parse_mode=ParseMode.HTML)
        return
    location = " ".join(context.args).strip()
    target_url = f"{WEATHER_API_BASE_URL}/{location}"
    await execute_api_search(update, context, target_url, {}, "weather", location)

# ============================================================
# SAFE MESSAGE EDIT HELPER
# ============================================================

async def safe_edit_text(query, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None):
    try:
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            logger.warning("safe_edit_text error: %s", e)
    except Exception as e:
        logger.exception("safe_edit_text exception: %s", e)

# ============================================================
# ADMIN PANEL (ADMINS ONLY BUTTON INTERFACE)
# ============================================================

def admin_dashboard_keyboard():
    status = "🟢 Bot: ACTIVE" if bot_enabled() else "🔴 Bot: OFFLINE"
    fj_status = "🟢 Force-Join: ON" if force_join_active() else "🔴 Force-Join: OFF"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(status, callback_data="adm_toggle_bot"),
                InlineKeyboardButton(fj_status, callback_data="adm_toggle_fj"),
            ],
            [
                InlineKeyboardButton("📊 Terminal Status", callback_data="adm_all_status"),
                InlineKeyboardButton("👥 Users Registry", callback_data="adm_users_0"),
            ],
            [
                InlineKeyboardButton("🚫 Blocked Directory", callback_data="adm_blocked_0"),
                InlineKeyboardButton("🌐 Active Groups", callback_data="adm_groups_0"),
            ],
            [
                InlineKeyboardButton("📦 Subscriptions", callback_data="adm_plans"),
                InlineKeyboardButton("⚡ API Switches", callback_data="adm_apis"),
            ],
            [
                InlineKeyboardButton("🎨 Welcome Studio", callback_data="adm_welcome"),
                InlineKeyboardButton("📢 Channel Lock", callback_data="adm_channels"),
            ],
            [
                InlineKeyboardButton("⚙️ System Config", callback_data="adm_settings"),
                InlineKeyboardButton("📢 Mass Broadcast", callback_data="adm_broadcast_prompt"),
            ],
            [
                InlineKeyboardButton("🔄 Refresh Terminal", callback_data="adm_home"),
            ],
        ]
    )

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    text = (
        f"┌───「 {EMOJI_SHIELD} <b>{BRAND} ADMIN CENTRAL</b> 」───\n"
        f"│ Welcome to Central Command Terminal.\n"
        f"│ Stealth Buttons enabled exclusively for Administrators.\n"
        f"└────────────────────────────────────────"
    )
    await update.message.reply_text(text, reply_markup=admin_dashboard_keyboard(), parse_mode=ParseMode.HTML)

# ============================================================
# ADMIN SUBMENUS
# ============================================================

USERS_PER_PAGE = 8

async def show_all_status(query):
    conn = db_connection()
    try:
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        banned_users = conn.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1").fetchone()[0]
        unlimited_users = conn.execute("SELECT COUNT(*) FROM users WHERE is_unlimited = 1").fetchone()[0]
        paid_users = conn.execute("SELECT COUNT(*) FROM users WHERE plan_id IS NOT NULL").fetchone()[0]
        total_searches = conn.execute("SELECT COALESCE(SUM(total_searches), 0) FROM users").fetchone()[0]

        total_groups = conn.execute("SELECT COUNT(*) FROM tracked_groups").fetchone()[0]
        group_searches = conn.execute("SELECT COALESCE(SUM(total_searches), 0) FROM tracked_groups").fetchone()[0]
    finally:
        conn.close()

    bot_st = "🟢 ONLINE" if bot_enabled() else "🔴 OFFLINE"
    fj_st = "🟢 ENFORCED" if force_join_active() else "🔴 BYPASSED"
    p_lim = get_private_limit()
    g_lim = get_group_limit()
    ref_b = get_referral_bonus()
    frz_t = get_freeze_minutes()
    audit_ch = get_audit_channel()
    ch_status = f"<code>{audit_ch}</code>" if audit_ch != 0 else "🔴 Not Configured"

    apis = ["num", "vehicle", "adh", "tg", "gm", "tc", "pin", "ifsc", "ip", "weather"]
    api_stat_str = " ".join([f"/{a}:{'🟢' if api_is_active(a) else '🔴'}" for a in apis])

    text = (
        f"┌───「 📊 <b>{BRAND} | LIVE TELEMETRY</b> 」───\n"
        f"│ 🤖 <b>Mainframe Engine:</b> {bot_st}\n"
        f"│ 📢 <b>Force-Join Engine:</b> {fj_st}\n"
        f"├───「 👥 <b>USER BASE METRICS</b> 」───\n"
        f"│ • Total Registered: <code>{total_users}</code>\n"
        f"│ • Active Unlimited: <code>{unlimited_users}</code>\n"
        f"│ • Plan Subscribers: <code>{paid_users}</code>\n"
        f"│ • Blacklisted: <code>{banned_users}</code>\n"
        f"├───「 🌐 <b>OPERATIONS</b> 」───\n"
        f"│ • Total Group Hubs: <code>{total_groups}</code>\n"
        f"│ • Group Operations: <code>{group_searches}</code>\n"
        f"│ • Lifetime Operations: <code>{total_searches}</code>\n"
        f"├───「 ⚙️ <b>LIVE POLICIES</b> 」───\n"
        f"│ • DM Limit: <code>{p_lim}</code> | Group Limit: <code>{g_lim}</code>\n"
        f"│ • Referral Bonus: <code>{ref_b}</code> Credits/Invite\n"
        f"│ • Freeze Timer: <code>{frz_t}</code> Min | Audit Log: {ch_status}\n"
        f"├───「 {EMOJI_LIGHTNING} <b>API GATEWAYS</b> 」───\n"
        f"│ {api_stat_str}\n"
        f"└──────────────────────────────────────"
    )

    buttons = [
        [InlineKeyboardButton("🔄 Refresh Telemetry", callback_data="adm_all_status")],
        [InlineKeyboardButton("🔙 Return", callback_data="adm_home")],
    ]
    await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(buttons))

async def show_admin_users(query, page: int):
    conn = db_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        offset = page * USERS_PER_PAGE
        rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?", (USERS_PER_PAGE, offset)).fetchall()
    finally:
        conn.close()

    if not rows:
        await safe_edit_text(query, "👥 <b>No operatives logged.</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Return", callback_data="adm_home")]]))
        return

    text = f"┌───「 👥 <b>OPERATIVE DIRECTORY (Total: {total})</b> 」───\n"
    for r in rows:
        uname = f"@{html.escape(r['username'])}" if r["username"] else "No Handle"
        plan = f"{EMOJI_LIGHTNING} Unlimited" if r["is_unlimited"] else (html.escape(str(r["plan_name"])) if r["plan_name"] else "Free")
        state = f"{EMOJI_CROSS}" if r["is_banned"] else f"{EMOJI_CHECK}"
        text += f"│ {state} <code>{r['user_id']}</code> | {uname}\n│    🏷 Plan: {plan} | Ref: {r['referral_credits']} | Searches: {r['total_searches']}\n"
    text += "└────────────────────────────────────────"

    buttons = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"adm_users_{page - 1}"))
    if offset + USERS_PER_PAGE < total:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"adm_users_{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("🔙 Return", callback_data="adm_home")])

    await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(buttons))

async def show_admin_blocked(query, page: int):
    conn = db_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1").fetchone()[0]
        offset = page * USERS_PER_PAGE
        rows = conn.execute("SELECT * FROM users WHERE is_banned = 1 ORDER BY updated_at DESC LIMIT ? OFFSET ?", (USERS_PER_PAGE, offset)).fetchall()
    finally:
        conn.close()

    if not rows:
        await safe_edit_text(query, f"{EMOJI_CHECK} <b>No operatives currently blocked.</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Return", callback_data="adm_home")]]))
        return

    text = f"┌───「 🚫 <b>BLACKLIST DIRECTORY (Total: {total})</b> 」───\n"
    for r in rows:
        uname = f"@{html.escape(r['username'])}" if r["username"] else "No Handle"
        text += f"│ {EMOJI_CROSS} <code>{r['user_id']}</code> | {uname}\n"
    text += f"├───「 <b>ACTION</b> 」───\n│ Use <code>/unban &lt;id&gt;</code> to unban.\n└──────────────────────────────"

    buttons = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"adm_blocked_{page - 1}"))
    if offset + USERS_PER_PAGE < total:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"adm_blocked_{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("🔙 Return", callback_data="adm_home")])

    await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(buttons))

async def show_admin_groups(query, page: int):
    conn = db_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM tracked_groups").fetchone()[0]
        offset = page * USERS_PER_PAGE
        rows = conn.execute("SELECT * FROM tracked_groups ORDER BY total_searches DESC LIMIT ? OFFSET ?", (USERS_PER_PAGE, offset)).fetchall()
    finally:
        conn.close()

    if not rows:
        await safe_edit_text(query, "🌐 <b>No active groups tracked.</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Return", callback_data="adm_home")]]))
        return

    text = f"┌───「 🌐 <b>ACTIVE GROUPS MATRIX (Total: {total})</b> 」───\n"
    for r in rows:
        title = html.escape(r["group_title"] or "Group")
        last_act = r["last_active"][:16].replace("T", " ") if r["last_active"] else "N/A"
        text += f"│ 👥 <b>{title}</b>\n│    🆔 <code>{r['group_id']}</code> | Searches: <code>{r['total_searches']}</code> | Active: <code>{last_act}</code>\n"
    text += "└────────────────────────────────────────"

    buttons = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"adm_groups_{page - 1}"))
    if offset + USERS_PER_PAGE < total:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"adm_groups_{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("🔙 Return", callback_data="adm_home")])

    await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(buttons))

async def show_admin_apis(query):
    api_list = ["num", "vehicle", "adh", "tg", "gm", "tc", "pin", "ifsc", "ip", "weather"]
    buttons = []
    row = []
    for item in api_list:
        status = "🟢" if api_is_active(item) else "🔴"
        row.append(InlineKeyboardButton(f"{status} /{item}", callback_data=f"adm_tglapi_{item}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🔙 Return", callback_data="adm_home")])
    await safe_edit_text(query, "<b>Tap an endpoint to Toggle 🟢 ON / 🔴 OFF:</b>", reply_markup=InlineKeyboardMarkup(buttons))

async def show_admin_plans(query):
    plans = list_plans()
    buttons = []
    text = f"┌───「 📦 <b>SUBSCRIPTIONS DIRECTORY</b> 」───\n"
    if not plans:
        text += "│ <i>No custom subscription packages created.</i>\n"
    else:
        for p in plans:
            p_name = html.escape(str(p['name']))
            text += f"│ 🆔 <code>{p['id']}</code> | <b>{p_name}</b> | {p['days']}d | {p['uses']} Quota\n"
            buttons.append([InlineKeyboardButton(f"🗑 Delete '{p_name}'", callback_data=f"adm_delplan_{p['id']}")])
    text += (
        f"├───「 <b>COMMANDS</b> 」───\n"
        f"│ • <code>/createplan &lt;NAME&gt; &lt;DAYS&gt; &lt;USES&gt;</code>\n"
        f"│ • <code>/grant &lt;USER_ID&gt; &lt;PLAN_ID&gt;</code>\n"
        f"│ • <code>/revoke &lt;USER_ID&gt;</code>\n"
        f"└──────────────────────────────────"
    )
    buttons.append([InlineKeyboardButton("🔙 Return", callback_data="adm_home")])
    await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(buttons))

async def show_admin_channels(query):
    channels = get_force_channels()
    buttons = []
    text = f"┌───「 📢 <b>FORCE-JOIN CHANNELS</b> 」───\n"
    if not channels:
        text += "│ <i>No force channels configured.</i>\n"
    else:
        for ch in channels:
            text += f"│ 📢 <b>{ch['username']}</b> ➔ <a href='{ch['invite_link']}'>Link</a>\n"
            buttons.append([InlineKeyboardButton(f"🗑 Remove {ch['username']}", callback_data=f"adm_delch_{ch['id']}")])

    buttons.append([InlineKeyboardButton("➕ Add New Channel", callback_data="adm_addch_prompt")])
    buttons.append([InlineKeyboardButton("🔙 Return", callback_data="adm_home")])
    await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(buttons))

async def show_admin_welcome(query):
    w_text = get_setting("welcome_text")
    m_id = get_setting("welcome_media_id")
    m_type = get_setting("welcome_media_type")

    text_status = "Custom HTML Text" if w_text else "Default Layout"
    media_status = f"Active ({m_type.upper()})" if m_id else "None (Pure Text)"

    text = (
        f"┌───「 🎨 <b>WELCOME STUDIO</b> 」───\n"
        f"│ 📝 <b>Text Engine:</b> {text_status}\n"
        f"│ 🎬 <b>Media:</b> {media_status}\n"
        f"├───「 <b>PLACEHOLDERS</b> 」───\n"
        f"│ • <code>{{name}}</code>, <code>{{id}}</code>, <code>{{mention}}</code>\n"
        f"└──────────────────────────────────────"
    )

    buttons = [
        [InlineKeyboardButton("📝 Set Custom Text", callback_data="adm_set_wtext")],
        [InlineKeyboardButton("🎬 Upload Photo/Video", callback_data="adm_set_wmedia")],
    ]
    if m_id:
        buttons.append([InlineKeyboardButton("🗑 Remove Media", callback_data="adm_del_wmedia")])
    if w_text:
        buttons.append([InlineKeyboardButton("🔄 Reset to Default Layout", callback_data="adm_reset_wtext")])
    buttons.append([InlineKeyboardButton("🔙 Return", callback_data="adm_home")])
    await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(buttons))

async def show_admin_settings(query):
    p_lim = get_private_limit()
    g_lim = get_group_limit()
    ref_b = get_referral_bonus()
    freeze_t = get_freeze_minutes()
    audit_ch = get_audit_channel()
    status = "🟢 Active" if bot_enabled() else "🔴 Inactive"
    fj_status = "🟢 Enforced" if force_join_active() else "🔴 Bypassed"

    text = (
        f"┌───「 ⚙️ <b>SYSTEM CONFIGURATION</b> 」───\n"
        f"│ 🤖 <b>Mainframe:</b> {status}\n"
        f"│ 📢 <b>Force-Join:</b> {fj_status}\n"
        f"│ 💬 <b>DM Limit:</b> <code>{p_lim}</code> | 👥 <b>Group Limit:</b> <code>{g_lim}</code>\n"
        f"│ 🎁 <b>Referral Bonus:</b> <code>{ref_b}</code> Credits/Invite\n"
        f"│ ❄️ <b>Freeze Timer:</b> <code>{freeze_t}</code> Min\n"
        f"│ 🛰 <b>Surveillance Channel:</b> <code>{audit_ch if audit_ch != 0 else 'None'}</code>\n"
        f"├───「 <b>ADMIN COMMANDS</b> 」───\n"
        f"│ • <code>/setreferral &lt;credits&gt;</code>\n"
        f"│ • <code>/setprivate &lt;limit&gt;</code>\n"
        f"│ • <code>/setgroupcredit &lt;limit&gt;</code>\n"
        f"│ • <code>/setfreeze &lt;minutes&gt;</code>\n"
        f"│ • <code>/setlogchannel &lt;channel_id&gt;</code>\n"
        f"│ • <code>/setunlimited &lt;user_id&gt;</code>\n"
        f"│ • <code>/setuserlimit &lt;user_id&gt; &lt;limit&gt;</code>\n"
        f"│ • <code>/giveoneday &lt;user_id&gt; &lt;credits&gt;</code>\n"
        f"│ • <code>/blockall</code> | <code>/unblockall</code>\n"
        f"└──────────────────────────────────────"
    )
    buttons = [[InlineKeyboardButton("🔙 Return", callback_data="adm_home")]]
    await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(buttons))

# ============================================================
# CALLBACK QUERY ROUTER (ADMIN ONLY)
# ============================================================

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    user = query.from_user

    if not user or not is_admin(user.id):
        await query.answer("❌ Stealth Console: Restricted to Administrators only.", show_alert=True)
        return

    await query.answer()
    data = query.data or ""

    try:
        if data == "adm_home":
            ADMIN_STATE.pop(user.id, None)
            text = (
                f"┌───「 {EMOJI_SHIELD} <b>{BRAND} ADMIN CENTRAL</b> 」───\n"
                f"│ Command Console active.\n"
                f"└────────────────────────────────────────"
            )
            await safe_edit_text(query, text, reply_markup=admin_dashboard_keyboard())
        elif data == "adm_all_status":
            await show_all_status(query)
        elif data == "adm_toggle_bot":
            new_st = not bot_enabled()
            set_setting("bot_enabled", "1" if new_st else "0")
            await safe_edit_text(query, "Bot status updated.", reply_markup=admin_dashboard_keyboard())
        elif data == "adm_toggle_fj":
            new_fj = not force_join_active()
            set_setting("force_join_enabled", "1" if new_fj else "0")
            await safe_edit_text(query, "Force-join status updated.", reply_markup=admin_dashboard_keyboard())
        elif data.startswith("adm_users_"):
            page = int(data.split("_")[-1])
            await show_admin_users(query, page)
        elif data.startswith("adm_blocked_"):
            page = int(data.split("_")[-1])
            await show_admin_blocked(query, page)
        elif data.startswith("adm_groups_"):
            page = int(data.split("_")[-1])
            await show_admin_groups(query, page)
        elif data == "adm_apis":
            await show_admin_apis(query)
        elif data.startswith("adm_tglapi_"):
            api_target = data.replace("adm_tglapi_", "")
            toggle_api_status(api_target)
            await show_admin_apis(query)
        elif data == "adm_plans":
            await show_admin_plans(query)
        elif data.startswith("adm_delplan_"):
            pid = int(data.split("_")[-1])
            delete_plan(pid)
            await show_admin_plans(query)
        elif data == "adm_channels":
            await show_admin_channels(query)
        elif data.startswith("adm_delch_"):
            cid = int(data.split("_")[-1])
            remove_force_channel(cid)
            await show_admin_channels(query)
        elif data == "adm_addch_prompt":
            ADMIN_STATE[user.id] = "awaiting_channel"
            await safe_edit_text(
                query,
                "<b>Send channel details:</b>\n\n<code>@channel_username https://t.me/invite_link</code>",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="adm_channels")]]),
            )
        elif data == "adm_welcome":
            await show_admin_welcome(query)
        elif data == "adm_set_wtext":
            ADMIN_STATE[user.id] = "awaiting_welcome_text"
            await safe_edit_text(
                query,
                "<b>Send Custom Welcome Text (HTML supported):</b>\nPlaceholders: <code>{name}</code>, <code>{id}</code>, <code>{mention}</code>",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="adm_welcome")]]),
            )
        elif data == "adm_set_wmedia":
            ADMIN_STATE[user.id] = "awaiting_welcome_media"
            await safe_edit_text(
                query,
                "<b>Send Welcome Photo or Video:</b>",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="adm_welcome")]]),
            )
        elif data == "adm_del_wmedia":
            set_setting("welcome_media_id", "")
            set_setting("welcome_media_type", "")
            await show_admin_welcome(query)
        elif data == "adm_reset_wtext":
            set_setting("welcome_text", "")
            await show_admin_welcome(query)
        elif data == "adm_broadcast_prompt":
            ADMIN_STATE[user.id] = "awaiting_broadcast_payload"
            await safe_edit_text(
                query,
                "<b>Send the message or media to broadcast to all users:</b>",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="adm_home")]]),
            )
        elif data == "adm_settings":
            await show_admin_settings(query)
    except Exception as exc:
        logger.exception("Callback error: %s", exc)

# ============================================================
# ADMIN INPUT LISTENER
# ============================================================

async def handle_admin_inputs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_admin(user.id):
        return
    if user.id not in ADMIN_STATE:
        return

    state = ADMIN_STATE[user.id]

    if state == "awaiting_broadcast_payload":
        ADMIN_STATE.pop(user.id, None)
        status_msg = await update.message.reply_text(f"{EMOJI_LIGHTNING} <code>Broadcasting message...</code>", parse_mode=ParseMode.HTML)

        conn = db_connection()
        try:
            users = conn.execute("SELECT user_id FROM users").fetchall()
        finally:
            conn.close()

        sent = 0
        failed = 0
        admin_chat_id = update.effective_chat.id
        source_msg_id = update.message.message_id

        for u in users:
            try:
                await context.bot.copy_message(
                    chat_id=u["user_id"],
                    from_chat_id=admin_chat_id,
                    message_id=source_msg_id,
                )
                sent += 1
                await asyncio.sleep(0.04)
            except Exception:
                failed += 1

        try:
            await status_msg.delete()
        except Exception:
            pass

        await update.message.reply_text(
            f"┌───「 <b>TRANSMISSION REPORT</b> 」───\n"
            f"│ 📤 Delivered: {sent}\n"
            f"│ {EMOJI_CROSS} Failed: {failed}\n"
            f"└────────────────────────────────",
            parse_mode=ParseMode.HTML,
        )
        await admin_command(update, context)
        return

    elif state == "awaiting_welcome_text":
        if update.message and update.message.text:
            set_setting("welcome_text", update.message.text)
            ADMIN_STATE.pop(user.id, None)
            await update.message.reply_text(f"{EMOJI_CHECK} <b>Welcome Text Updated!</b>", parse_mode=ParseMode.HTML)
            await admin_command(update, context)
            return

    elif state == "awaiting_welcome_media":
        if update.message and update.message.video:
            set_setting("welcome_media_id", update.message.video.file_id)
            set_setting("welcome_media_type", "video")
            ADMIN_STATE.pop(user.id, None)
            await update.message.reply_text(f"{EMOJI_CHECK} <b>Welcome Video Updated!</b>", parse_mode=ParseMode.HTML)
            await admin_command(update, context)
            return
        elif update.message and update.message.photo:
            set_setting("welcome_media_id", update.message.photo[-1].file_id)
            set_setting("welcome_media_type", "photo")
            ADMIN_STATE.pop(user.id, None)
            await update.message.reply_text(f"{EMOJI_CHECK} <b>Welcome Photo Updated!</b>", parse_mode=ParseMode.HTML)
            await admin_command(update, context)
            return

    elif state == "awaiting_channel":
        if update.message and update.message.text:
            parts = update.message.text.strip().split()
            if len(parts) >= 2:
                ok = add_force_channel(parts[0], parts[1])
                ADMIN_STATE.pop(user.id, None)
                if ok:
                    await update.message.reply_text(f"{EMOJI_CHECK} <b>Channel added!</b>", parse_mode=ParseMode.HTML)
                else:
                    await update.message.reply_text(f"{EMOJI_CROSS} Channel already exists.")
                await admin_command(update, context)
                return

# ============================================================
# ADMIN USER MANAGEMENT PROTOCOLS
# ============================================================

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args:
        await update.message.reply_text("<b>Syntax:</b> <code>/info &lt;user_id&gt;</code>", parse_mode=ParseMode.HTML)
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text(f"{EMOJI_CROSS} Numeric User ID required.", parse_mode=ParseMode.HTML)
        return

    reset_daily_usage_if_needed(uid)
    row = get_user(uid)
    if not row:
        await update.message.reply_text(f"{EMOJI_CROSS} Operative not found in database.", parse_mode=ParseMode.HTML)
        return

    class DummyUser:
        first_name = row["first_name"] or "Operative"
        id = uid

    card = format_status_card(row, DummyUser)
    await update.message.reply_text(card, parse_mode=ParseMode.HTML)

async def setreferral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args:
        await update.message.reply_text("<b>Syntax:</b> <code>/setreferral &lt;credits&gt;</code>", parse_mode=ParseMode.HTML)
        return
    try:
        val = int(context.args[0])
        if val < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(f"{EMOJI_CROSS} Positive integer required.", parse_mode=ParseMode.HTML)
        return
    set_setting("referral_bonus", str(val))
    await update.message.reply_text(f"{EMOJI_CHECK} Referral Bonus set to: <b>+{val} Search Credits / Invite</b>", parse_mode=ParseMode.HTML)

async def setprivate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args:
        await update.message.reply_text("<b>Syntax:</b> <code>/setprivate &lt;limit&gt;</code>", parse_mode=ParseMode.HTML)
        return
    try:
        val = int(context.args[0])
        if val < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(f"{EMOJI_CROSS} Positive integer required.", parse_mode=ParseMode.HTML)
        return
    set_setting("private_limit", str(val))
    await update.message.reply_text(f"{EMOJI_CHECK} Global Private Daily Limit set to: <b>{val}</b>", parse_mode=ParseMode.HTML)

async def setgroupcredit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args:
        await update.message.reply_text("<b>Syntax:</b> <code>/setgroupcredit &lt;limit&gt;</code>", parse_mode=ParseMode.HTML)
        return
    try:
        val = int(context.args[0])
        if val < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(f"{EMOJI_CROSS} Positive integer required.", parse_mode=ParseMode.HTML)
        return
    set_setting("group_limit", str(val))
    await update.message.reply_text(f"{EMOJI_CHECK} Global Group Daily Limit set to: <b>{val}</b>", parse_mode=ParseMode.HTML)

async def setfreeze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args:
        await update.message.reply_text("<b>Syntax:</b> <code>/setfreeze &lt;minutes&gt;</code>", parse_mode=ParseMode.HTML)
        return
    try:
        mins = int(context.args[0])
        if mins <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(f"{EMOJI_CROSS} Positive integer in minutes required.", parse_mode=ParseMode.HTML)
        return
    set_setting("freeze_minutes", str(mins))
    await update.message.reply_text(f"{EMOJI_CHECK} Freeze Timer set to: <b>{mins} Minutes</b>", parse_mode=ParseMode.HTML)

async def setlogchannel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args:
        await update.message.reply_text("<b>Syntax:</b> <code>/setlogchannel &lt;channel_id&gt;</code>", parse_mode=ParseMode.HTML)
        return
    try:
        ch_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(f"{EMOJI_CROSS} Integer Channel ID required (e.g. -100123456789).", parse_mode=ParseMode.HTML)
        return
    set_setting("audit_log_channel", str(ch_id))
    await update.message.reply_text(f"{EMOJI_CHECK} Log Channel configured: <code>{ch_id}</code>", parse_mode=ParseMode.HTML)

async def setunlimited_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args:
        await update.message.reply_text("<b>Syntax:</b> <code>/setunlimited &lt;user_id&gt;</code>", parse_mode=ParseMode.HTML)
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text(f"{EMOJI_CROSS} Integer User ID required.", parse_mode=ParseMode.HTML)
        return
    conn = db_connection()
    try:
        row = conn.execute("SELECT is_unlimited FROM users WHERE user_id = ?", (uid,)).fetchone()
        if not row:
            await update.message.reply_text(f"{EMOJI_CROSS} Operative not found in database.", parse_mode=ParseMode.HTML)
            return
        new_state = 0 if row["is_unlimited"] else 1
        conn.execute("UPDATE users SET is_unlimited = ?, updated_at = ? WHERE user_id = ?", (new_state, iso_now(), uid))
        conn.commit()
    finally:
        conn.close()

    status_str = "GRANTED (Unlimited Active)" if new_state else "REVOKED (Standard Quota)"
    await update.message.reply_text(f"{EMOJI_CHECK} Unlimited Status for <code>{uid}</code>: <b>{status_str}</b>", parse_mode=ParseMode.HTML)

async def setuserlimit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if len(context.args) < 2:
        await update.message.reply_text("<b>Syntax:</b> <code>/setuserlimit &lt;user_id&gt; &lt;limit&gt;</code>", parse_mode=ParseMode.HTML)
        return
    try:
        uid = int(context.args[0])
        limit_val = int(context.args[1])
    except ValueError:
        await update.message.reply_text(f"{EMOJI_CROSS} User ID and Limit must be integers.", parse_mode=ParseMode.HTML)
        return

    conn = db_connection()
    try:
        row = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (uid,)).fetchone()
        if not row:
            await update.message.reply_text(f"{EMOJI_CROSS} Operative not found in database.", parse_mode=ParseMode.HTML)
            return
        conn.execute(
            """
            UPDATE users
            SET custom_private_limit = ?,
                custom_group_limit = ?,
                updated_at = ?
            WHERE user_id = ?
            """,
            (limit_val, limit_val, iso_now(), uid),
        )
        conn.commit()
    finally:
        conn.close()

    desc = "Global Default" if limit_val < 0 else f"{limit_val} Searches / Day"
    await update.message.reply_text(f"{EMOJI_CHECK} Custom Daily Limit for <code>{uid}</code>: <b>{desc}</b>", parse_mode=ParseMode.HTML)

async def giveoneday_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if len(context.args) < 2:
        await update.message.reply_text("<b>Syntax:</b> <code>/giveoneday &lt;user_id&gt; &lt;credits&gt;</code>", parse_mode=ParseMode.HTML)
        return
    try:
        uid = int(context.args[0])
        credits_val = int(context.args[1])
        if credits_val < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(f"{EMOJI_CROSS} User ID and Credits must be positive integers.", parse_mode=ParseMode.HTML)
        return

    conn = db_connection()
    try:
        row = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (uid,)).fetchone()
        if not row:
            await update.message.reply_text(f"{EMOJI_CROSS} Operative not found in database.", parse_mode=ParseMode.HTML)
            return
        conn.execute(
            """
            UPDATE users
            SET one_day_credits = one_day_credits + ?,
                updated_at = ?
            WHERE user_id = ?
            """,
            (credits_val, iso_now(), uid),
        )
        conn.commit()
    finally:
        conn.close()

    await update.message.reply_text(f"{EMOJI_CHECK} Added <b>+{credits_val} 1-Day Temporary Credits</b> to operative <code>{uid}</code>.", parse_mode=ParseMode.HTML)

async def blockall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    conn = db_connection()
    try:
        admin_tuple = tuple(get_admin_ids())
        conn.execute(f"UPDATE users SET is_banned = 1, updated_at = ? WHERE user_id NOT IN ({','.join(['?']*len(admin_tuple))})", (iso_now(), *admin_tuple))
        conn.commit()
    finally:
        conn.close()
    await update.message.reply_text(f"{EMOJI_CROSS} <b>All non-admin operatives have been blacklisted.</b>", parse_mode=ParseMode.HTML)

async def unblockall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    conn = db_connection()
    try:
        conn.execute("UPDATE users SET is_banned = 0, updated_at = ?", (iso_now(),))
        conn.commit()
    finally:
        conn.close()
    await update.message.reply_text(f"{EMOJI_CHECK} <b>All operatives unblocked.</b>", parse_mode=ParseMode.HTML)

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args:
        await update.message.reply_text("<b>Syntax:</b> <code>/ban &lt;user_id&gt;</code>", parse_mode=ParseMode.HTML)
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text(f"{EMOJI_CROSS} Numeric ID required.", parse_mode=ParseMode.HTML)
        return
    if is_admin(uid):
        await update.message.reply_text(f"{EMOJI_SHIELD} Administrators cannot be blacklisted.", parse_mode=ParseMode.HTML)
        return
    conn = db_connection()
    try:
        conn.execute("UPDATE users SET is_banned = 1, updated_at = ? WHERE user_id = ?", (iso_now(), uid))
        conn.commit()
    finally:
        conn.close()
    await update.message.reply_text(f"{EMOJI_CROSS} Operative <code>{uid}</code> blacklisted.", parse_mode=ParseMode.HTML)

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args:
        await update.message.reply_text("<b>Syntax:</b> <code>/unban &lt;user_id&gt;</code>", parse_mode=ParseMode.HTML)
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text(f"{EMOJI_CROSS} Numeric ID required.", parse_mode=ParseMode.HTML)
        return
    conn = db_connection()
    try:
        conn.execute("UPDATE users SET is_banned = 0, updated_at = ? WHERE user_id = ?", (iso_now(), uid))
        conn.commit()
    finally:
        conn.close()
    await update.message.reply_text(f"{EMOJI_CHECK} Operative <code>{uid}</code> whitelisted.", parse_mode=ParseMode.HTML)

async def createplan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if len(context.args) < 3:
        await update.message.reply_text("<b>Syntax:</b> <code>/createplan &lt;NAME&gt; &lt;DAYS&gt; &lt;USES&gt;</code>", parse_mode=ParseMode.HTML)
        return
    try:
        name = " ".join(context.args[:-2]).strip()
        days = int(context.args[-2])
        uses = int(context.args[-1])
        if days <= 0 or uses <= 0 or not name:
            raise ValueError
    except ValueError:
        await update.message.reply_text(f"{EMOJI_CROSS} Positive integers required for Days and Uses.", parse_mode=ParseMode.HTML)
        return
    try:
        pid = create_plan(name, days, uses)
        await update.message.reply_text(f"{EMOJI_CHECK} Plan Created! 🆔 <code>{pid}</code> | 📛 <b>{html.escape(name)}</b> | ⏳ {days}d | 🔢 {uses} Quota", parse_mode=ParseMode.HTML)
    except sqlite3.IntegrityError:
        await update.message.reply_text(f"{EMOJI_CROSS} Plan with this name already exists.", parse_mode=ParseMode.HTML)

async def grant_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if len(context.args) != 2:
        await update.message.reply_text("<b>Syntax:</b> <code>/grant &lt;USER_ID&gt; &lt;PLAN_ID&gt;</code>", parse_mode=ParseMode.HTML)
        return
    try:
        uid = int(context.args[0])
        pid = int(context.args[1])
    except ValueError:
        await update.message.reply_text(f"{EMOJI_CROSS} Numbers required for IDs.", parse_mode=ParseMode.HTML)
        return
    row = get_user(uid)
    if not row:
        await update.message.reply_text(f"{EMOJI_CROSS} User must trigger /start first.", parse_mode=ParseMode.HTML)
        return
    ok, msg = assign_plan(uid, pid)
    await update.message.reply_text((f"{EMOJI_CHECK} " if ok else f"{EMOJI_CROSS} ") + msg, parse_mode=ParseMode.HTML)

async def revoke_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args:
        await update.message.reply_text("<b>Syntax:</b> <code>/revoke &lt;USER_ID&gt;</code>", parse_mode=ParseMode.HTML)
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text(f"{EMOJI_CROSS} Numeric ID required.", parse_mode=ParseMode.HTML)
        return
    revoke_plan(uid)
    await update.message.reply_text(f"{EMOJI_CHECK} Subscription revoked for <code>{uid}</code>.", parse_mode=ParseMode.HTML)

# ============================================================
# RENDER HTTP HEALTH CHECK
# ============================================================

async def health_check_server():
    async def handle_ping(request):
        return web.Response(text="OBSIDIAN TRACE CORE IS ACTIVE 🟢")

    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Render Web Service health check listening on port %s", port)

# ============================================================
# LIFECYCLE HOOKS
# ============================================================

async def post_init(application: Application):
    asyncio.create_task(health_check_server())

    commands = [
        BotCommand("start", "Initialize / Wake terminal"),
        BotCommand("num", "Mobile search (10-digit only)"),
        BotCommand("vehicle", "Vehicle registration RC search"),
        BotCommand("adh", "Identification record lookup"),
        BotCommand("tg", "Telegram User ID/Handle to mobile"),
        BotCommand("gm", "Gmail account lookup"),
        BotCommand("tc", "Truecaller registry intel"),
        BotCommand("pin", "Postal PIN code directory"),
        BotCommand("ifsc", "Bank branch IFSC directory"),
        BotCommand("ip", "IP Geolocation lookup"),
        BotCommand("weather", "Weather intelligence lookup"),
        BotCommand("ref", "Recruitment referral link"),
        BotCommand("status", "View operational limits"),
        BotCommand("help", "Command documentation"),
    ]
    await application.bot.set_my_commands(commands)
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    logger.info("Menu commands & Chat Menu Button set successfully.")

async def post_shutdown(application: Application):
    global HTTP_CLIENT
    if HTTP_CLIENT and not HTTP_CLIENT.is_closed:
        await HTTP_CLIENT.aclose()
        logger.info("Async HTTP client closed cleanly.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    if isinstance(context.error, NetworkError):
        logger.warning("Network fluctuation: %s", context.error)
        return
    if isinstance(context.error, Conflict):
        logger.warning("Bot instance conflict (409) detected. Resolving and waiting...")
        await asyncio.sleep(2)
        return
    logger.exception("Update handler encountered error:", exc_info=context.error)

# ============================================================
# ENTRYPOINT
# ============================================================

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is not set. Please configure it.")

    init_db()

    t_request = HTTPXRequest(
        connection_pool_size=60,
        connect_timeout=10.0,
        read_timeout=25.0,
        write_timeout=25.0,
    )

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .request(t_request)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Core User Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ref", ref_command))
    app.add_handler(CommandHandler("referral", ref_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))

    # Intel Query Handlers
    app.add_handler(CommandHandler("num", num_command))
    app.add_handler(CommandHandler("query", num_command))
    app.add_handler(CommandHandler("vehicle", vehicle_command))
    app.add_handler(CommandHandler("adh", adhar_command))
    app.add_handler(CommandHandler("tg", tg_command))
    app.add_handler(CommandHandler("gm", gmail_command))
    app.add_handler(CommandHandler("tc", truecaller_command))
    app.add_handler(CommandHandler("pin", pin_command))
    app.add_handler(CommandHandler("ifsc", ifsc_command))
    app.add_handler(CommandHandler("ip", ip_command))
    app.add_handler(CommandHandler("weather", weather_command))

    # Admin Command Handlers
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("user", info_command))
    app.add_handler(CommandHandler("setreferral", setreferral_command))
    app.add_handler(CommandHandler("setprivate", setprivate_command))
    app.add_handler(CommandHandler("setgroupcredit", setgroupcredit_command))
    app.add_handler(CommandHandler("setfreeze", setfreeze_command))
    app.add_handler(CommandHandler("setlogchannel", setlogchannel_command))
    app.add_handler(CommandHandler("setunlimited", setunlimited_command))
    app.add_handler(CommandHandler("setuserlimit", setuserlimit_command))
    app.add_handler(CommandHandler("giveoneday", giveoneday_command))
    app.add_handler(CommandHandler("blockall", blockall_command))
    app.add_handler(CommandHandler("unblockall", unblockall_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("createplan", createplan_command))
    app.add_handler(CommandHandler("grant", grant_command))
    app.add_handler(CommandHandler("revoke", revoke_command))

    # Admin Interactive Callbacks
    app.add_handler(CallbackQueryHandler(admin_callback))

    # Admin Prompts Handler
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_admin_inputs))

    # Error Handler
    app.add_error_handler(error_handler)

    print(
        f"\n{BRAND}\n"
        "=====================================================\n"
        "🚀 Terminal Online: Obsidian Trace Core Activated\n"
        "✨ Animated Emojis: Loaded from ids.txt & Injected\n"
        "🛡 Clean Text for Users | Stealth Buttons for Admins\n"
        "🔄 Auto-Chaining (/tg -> /num) & Dual Resolvers: Ready\n"
        "=====================================================\n"
    )
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
