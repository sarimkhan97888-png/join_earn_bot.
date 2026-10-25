import asyncio
import logging
from datetime import datetime, timezone

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M
from telegram.error import RetryAfter, TelegramError

import config
import i18n

log = logging.getLogger("util")
WELCOME = (
    "💰 <b>𝐂𝐎𝐌𝐏𝐋𝐄𝐓𝐄 𝐓𝐀𝐒𝐊𝐒 &amp; 𝐄𝐀𝐑𝐍 𝐂𝐎𝐈𝐍𝐒</b> 🪙\n\n"
    "🔥 Complete Tasks &amp; Earn Coins\n"
    "💸 Instant UPI Withdrawal\n"
    "🎯 Create Tasks Using Coins\n"
    "📺 Watch Ads &amp; Earn Rewards\n"
    "👥 Get Subscribers &amp; Referrals\n\n"
    "🚀 <b>𝐒𝐭𝐚𝐫𝐭 𝐄𝐚𝐫𝐧𝐢𝐧𝐠 𝐓𝐨𝐝𝐚𝐲!</b> 💎")
LANG_PROMPT = "🌐 <b>Choose your language</b>\nअपनी भाषा चुनें\nApni bhasha chuno"
LANG_NAMES = {"hn": "Hinglish", "hi": "हिन्दी", "en": "English"}


def lang_kb(prefix="lang"):
    return M([[B("🇮🇳 Hinglish", callback_data=f"{prefix}:hn")], [B("🇮🇳 हिन्दी", callback_data=f"{prefix}:hi")],
              [B("🇬🇧 English", callback_data=f"{prefix}:en")]])


main_bot = None  # main bot object (backup bot ke callbacks me bhi user ko main bot se hi DM jaata hai)


def inr(coins):
    return f"₹{coins / config.COIN_PER_INR:,.2f}"


def _g(u, k, d=None):
    try:
        return u[k]
    except (KeyError, IndexError, TypeError):
        return d


def real_level(u):
    """Kharide hue premium ka level (admin override ke bina)."""
    pu = _g(u, "premium_until")
    if u and pu and pu > datetime.now(timezone.utc):
        return max(1, int(_g(u, "premium_level", 0) or 0))
    return 0


def level(u):
    """0 = free, 1..3 = premium level. Admin hamesha top level."""
    if not u:
        return 0
    if u["id"] in config.ADMIN_IDS:
        return max(config.PLANS)
    return real_level(u)


def plan_of(lvl):
    """Is level ke limits/fees. Free ke liye bhi poora dict (free: roz FREE_TASKS_DAILY channel task, bot work nahi)."""
    if lvl in config.PLANS:
        p = dict(config.PLANS[lvl])
    else:
        p = dict(members=config.FREE_TASK_MEMBERS, price=0, days=0, tasks=config.FREE_TASKS_DAILY, wd=1, fee=None, wd_hours=config.WITHDRAW_EXPIRE_HOURS, ref=config.REFER_REWARD, top=False)
    if p["fee"] is None:
        p["fee"] = config.WITHDRAW_TAX_PERCENT
    p["level"] = lvl
    return p


def plan(u):
    return plan_of(level(u))


def is_prem(u):
    """Admin (ADMIN_IDS) ke liye premium hamesha unlocked."""
    return level(u) > 0


def tag(lvl):
    """Admin ko dikhne wala chhota tag."""
    return f"⭐ L{lvl}" if lvl else "Free"


def in_chat(cm):
    return cm.status in ("member", "administrator", "creator") or (cm.status == "restricted" and cm.is_member)


async def member_status(bot, chat_id, uid):
    """True = member, False = nahi, None = verify nahi ho paya."""
    try:
        m = await bot.get_chat_member(chat_id, uid)
    except TelegramError:
        return None
    return in_chat(m)


async def notify(bot, uid, text, **kw):
    """Message bhejo. Telegram flood limit aaye to ek baar ruk ke retry."""
    try:
        text = await i18n.tr_for(uid, text)  # user ki chuni hui bhasha
    except Exception:
        pass
    for _ in range(2):
        try:
            await bot.send_message(uid, text, parse_mode="HTML", **kw)
            return True
        except RetryAfter as e:
            ra = e.retry_after
            await asyncio.sleep(min(ra.total_seconds() if hasattr(ra, "total_seconds") else float(ra), 8) + 0.5)
        except TelegramError:
            return False
    return False
