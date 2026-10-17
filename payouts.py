"""Withdraw payouts (Elite Pay UPI). Safe state machine:

pending --claim--> sending --gateway OK--> processing --status API--> paid | failed(+refund)
                      |-- definite reject --> pending (admin manual)
                      |-- unsure (timeout/5xx) --> sending (admin check karega, auto retry kabhi nahi)
"""
import asyncio
import logging
import time

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M

import config
import db
import gateway
import util

log = logging.getLogger("payouts")
_pause = {"until": 0.0}
_last = {}


def enabled():
    return config.AUTO_PAYOUT and time.monotonic() >= _pause["until"]


def pause(seconds):
    _pause["until"] = time.monotonic() + seconds


def eligible(u, net_inr, recent_count):
    """Is withdraw ko auto payout kar sakte hain?"""
    return bool(enabled() and not u["suspect"] and float(net_inr) <= config.AUTO_PAYOUT_MAX_INR
                and recent_count <= config.AUTO_PAYOUT_DAILY)


async def alert(bot, text, kb=None):
    for a in config.ADMIN_IDS:
        await util.notify(bot, a, text, reply_markup=kb)


def admin_kb(wid):
    return M([[B("✅ Approve", callback_data=f"adm_ok:{wid}"), B("❌ Reject", callback_data=f"adm_no:{wid}")]])


def fix_kb(wid):
    return M([[B("✅ Mark paid", callback_data=f"adm_paid:{wid}"), B("↩️ Refund user", callback_data=f"adm_refund:{wid}")]])


async def send(bot, wid):
    """pending withdraw ko gateway se bhejo. Return: processing / pending (nahi gaya) / stuck / skip"""
    w = await db.wd_move(wid, "pending", "sending")
    if not w:
        return "skip"
    try:
        r = await gateway.payout(w["upi"], w["amount_inr"], f"WD{wid}")
    except Exception as e:  # koi bhi unexpected error = unsure, double payment ka risk nahi lena
        log.exception("payout call crashed")
        r = {"ok": False, "definite": False, "error": type(e).__name__}
    if r["ok"]:
        await db.wd_set_ref(wid, r["ref"])
        if r["receive"] and abs(r["receive"] - float(w["amount_inr"])) > 0.5:
            pause(10 ** 7)  # galat amount (wallet currency alag?) -> auto payout band, admin dekhe
            await alert(bot, f"🚨 <b>Payout amount mismatch</b> #{wid}\nBheja ₹{float(w['amount_inr']):.2f}, "
                             f"Elite ne receive diya ₹{r['receive']:.2f}.\nAuto payout band kar diya (restart tak). "
                             f"Wallet currency check karo.")
        return "processing"
    if r["definite"]:
        await db.wd_move(wid, "sending", "pending")
        err = r["error"]
        if "insufficient" in err or "too_many" in err:
            pause(900)
        await alert(bot, f"⚠️ Auto payout nahi hua #{wid}: <code>{err}</code>\n"
                         f"₹{float(w['amount_inr']):.2f} → <code>{w['upi']}</code>\n"
                         f"{'Elite wallet me balance daalo. ' if 'insufficient' in err else ''}"
                         f"Ab ye manual approval me hai.", admin_kb(wid))
        return "pending"
    await alert(bot, f"🚨 <b>Payout unsure</b> #{wid} ({r['error']})\n₹{float(w['amount_inr']):.2f} → "
                     f"<code>{w['upi']}</code>\nElite Pay dashboard me reference <code>WD{wid}</code> check karo. "
                     f"Ho gaya ho to Mark paid, nahi hua to Refund. Auto retry nahi hoga.", fix_kb(wid))
    return "stuck"


async def settle(bot, w, min_gap=0):
    """processing withdraw ko Elite ke status API se verify karke paid / failed karo."""
    if w["status"] != "processing" or not w["gateway_ref"]:
        return w["status"]
    now = time.monotonic()
    if min_gap and now - _last.get(w["id"], 0) < min_gap:
        return "processing"
    _last[w["id"]] = now
    try:
        state, _ = await gateway.check_payout(w["gateway_ref"])
    except Exception:
        log.exception("check_payout failed %s", w["id"])
        return "processing"
    if state == "paid":
        done = await db.wd_move(w["id"], "processing", "paid")
        _last.pop(w["id"], None)
        if done:
            await util.notify(bot, w["user_id"],
                              f"✅ Withdraw #{w['id']} paid: ₹{float(w['amount_inr']):.2f} → {w['upi']}")
        return "paid"
    if state == "failed":
        done = await db.wd_move(w["id"], "processing", "failed")
        if done:
            await db.wd_refund(done)
            await util.notify(bot, w["user_id"],
                              f"❌ Withdraw #{w['id']} fail hua. {done['coins']} coins wapas balance me add ho gaye.")
            await alert(bot, f"ℹ️ Payout #{w['id']} fail hua, user ko refund ho gaya.")
        return "failed"
    return "processing"


async def job(ctx):
    for w in await db.wd_processing():
        await settle(ctx.bot, w)
        await asyncio.sleep(0.2)
