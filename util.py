import asyncio
import logging
from datetime import datetime, timezone

from telegram.error import RetryAfter, TelegramError

import config

log = logging.getLogger("util")


def inr(coins):
    return f"₹{coins / config.COIN_PER_INR:,.2f}"


def is_prem(u):
    """Admin (ADMIN_IDS) ke liye premium hamesha unlocked."""
    if not u:
        return False
    if u["id"] in config.ADMIN_IDS:
        return True
    return bool(u["premium_until"] and u["premium_until"] > datetime.now(timezone.utc))


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
