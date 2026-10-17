import logging
from datetime import datetime, timezone

from telegram.error import TelegramError

import config

log = logging.getLogger("util")


def inr(coins):
    return f"₹{coins / config.COIN_PER_INR:,.2f}"


def is_prem(u):
    return bool(u and u["premium_until"] and u["premium_until"] > datetime.now(timezone.utc))


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
    try:
        await bot.send_message(uid, text, parse_mode="HTML", **kw)
    except TelegramError:
        pass
