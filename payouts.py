"""Withdraw admin alerts. Payout hamesha manual (admin UPI par khud pay karke Approve dabata hai)."""
import asyncio
import html
import logging
import time

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M

import config
import extras
import db
import adminops
import util

log = logging.getLogger("payouts")

async def alert(bot, text, kb=None, wid=None):
    """Buttons wale (approve/reject/mark paid) alerts BACKUP bot se (purana copy delete karke). Baaki info alerts main bot se."""
    if kb and wid:
        await extras.bk_delete(wid)
        try:
            await db.wd_set_msgs(wid, await extras.bk_send(text, kb))
        except Exception:
            log.exception("bk alert failed %s", wid)
    else:
        for a in config.ADMIN_IDS:
            await util.notify(bot, a, text, reply_markup=kb)
    if wid:
        try:
            await db.wd_touch_alert(wid)  # job dobara turant alert na bheje
        except Exception:
            log.exception("wd_touch_alert failed %s", wid)


def admin_kb(wid):
    rows = [[B("✅ Approve", callback_data=f"adm_ok:{wid}"), B("❌ Reject", callback_data=f"adm_no:{wid}")]]
    pr = adminops.panel_row()
    return M(rows + ([pr] if pr else []))


def fix_kb(wid):
    return M([[B("✅ Mark paid", callback_data=f"adm_paid:{wid}"), B("↩️ Refund user", callback_data=f"adm_refund:{wid}")]])
