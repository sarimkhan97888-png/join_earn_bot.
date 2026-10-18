"""Withdraw payouts (Elite Pay UPI). Safe state machine:

pending --claim--> sending --gateway OK--> processing --status API--> paid | failed(+refund)
                      |-- definite reject --> pending (admin manual)
                      |-- unsure (timeout/5xx) --> sending (admin check karega, auto retry kabhi nahi)
"""
import asyncio
import html
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
    return bool(enabled() and not u["suspect"] and 10 <= float(net_inr) <= config.AUTO_PAYOUT_MAX_INR
                and recent_count <= config.AUTO_PAYOUT_DAILY)


async def alert(bot, text, kb=None, wid=None):
    for a in config.ADMIN_IDS:
        await util.notify(bot, a, text, reply_markup=kb)
    if wid:
        try:
            await db.wd_touch_alert(wid)  # job dobara turant alert na bheje
        except Exception:
            log.exception("wd_touch_alert failed %s", wid)


def admin_kb(wid):
    return M([[B("✅ Approve", callback_data=f"adm_ok:{wid}"), B("❌ Reject", callback_data=f"adm_no:{wid}")]])


def fix_kb(wid):
    return M([[B("✅ Mark paid", callback_data=f"adm_paid:{wid}"), B("↩️ Refund user", callback_data=f"adm_refund:{wid}")]])


async def send(bot, wid):
    """pending withdraw ko gateway se bhejo. Return: processing / pending (nahi gaya) / stuck / skip"""
    w = await db.wd_move(wid, "pending", "sending")
    if not w:
        return "skip"
    attempt = f"WD{wid}-{int(time.time()) % 1000000}"  # har try ka alag reference/idempotency (pichla fail hua to "in_progress" na aaye)
    try:
        r = await gateway.payout(w["upi"], w["amount_inr"], attempt)
    except Exception as e:  # koi bhi unexpected error = unsure, double payment ka risk nahi lena
        log.exception("payout call crashed")
        r = {"ok": False, "definite": False, "error": type(e).__name__}
    if r["ok"]:
        saved = None
        for i in range(3):  # paisa ja chuka hai: status save karne ke liye retry
            try:
                saved = await db.wd_set_ref(wid, r["ref"])
                break
            except Exception:
                log.exception("wd_set_ref failed #%s try %s", wid, i + 1)
                await asyncio.sleep(1 + i)
        if not saved:
            await alert(bot, f"🚨 <b>Payout bhej diya par status save nahi hua</b> #{wid}\nElite payout id: "
                             f"<code>{html.escape(str(r['ref']))}</code>\nElite dashboard check karo. Paisa gaya ho to "
                             f"Mark paid (Refund mat karna).", fix_kb(wid), wid=wid)
            return "stuck"
        if r["receive"] and abs(r["receive"] - float(w["amount_inr"])) > 0.5:
            pause(10 ** 7)  # galat amount (wallet currency alag?) -> auto payout band, admin dekhe
            await alert(bot, f"🚨 <b>Payout amount mismatch</b> #{wid}\nBheja ₹{float(w['amount_inr']):.2f}, "
                             f"Elite ne receive diya ₹{r['receive']:.2f}.\nAuto payout band kar diya (restart tak). "
                             f"Wallet currency check karo.")
        return "processing"
    if r["definite"]:
        await db.wd_move(wid, "sending", "pending")
        err = r["error"]
        blocked = any(x in err for x in ("plan_restricted", "not_allowed", "forbidden", "scope", "permission"))
        if blocked:
            pause(6 * 3600)  # Elite plan/key me payout allowed nahi: baar baar try nahi, Approve = manual paid
        elif "insufficient" in err or "too_many" in err:
            pause(900)
        hint = ("Elite Pay plan/key me UPI payout allowed nahi hai (Elite support se payout enable karao). "
                "Auto 6 ghante band; ab Approve dabane par manual paid mark hoga, UPI par khud pay karo. "
                if blocked else "Elite wallet me balance daalo. " if "insufficient" in err else "")
        await alert(bot, f"⚠️ Auto payout nahi hua #{wid}: <code>{html.escape(err)}</code>\n"
                         f"₹{float(w['amount_inr']):.2f} → <code>{html.escape(w['upi'])}</code>\n"
                         f"{hint}Ab ye manual approval me hai.", admin_kb(wid), wid=wid)
        return "pending"
    await alert(bot, f"🚨 <b>Payout unsure</b> #{wid} ({html.escape(str(r['error']))})\n₹{float(w['amount_inr']):.2f} → "
                     f"<code>{html.escape(w['upi'])}</code>\nElite Pay dashboard me reference <code>{attempt}</code> check karo. "
                     f"Ho gaya ho to Mark paid, nahi hua to Refund. Auto retry nahi hoga.", fix_kb(wid), wid=wid)
    return "stuck"


async def settle(bot, w, min_gap=0):
    """processing withdraw ko Elite ke status API se verify karke paid / failed karo."""
    if w["status"] != "processing" or not w["gateway_ref"]:
        return w["status"]
    now = time.monotonic()
    if min_gap and now - _last.get(w["id"], 0) < min_gap:
        return "processing"
    _last[w["id"]] = now
    if len(_last) > 5000:  # chhoti memory leak band: purani entries hatao
        for k in [k for k, v in _last.items() if now - v > 600]:
            _last.pop(k, None)
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
        done = await db.wd_move_refund(w["id"], "processing", "failed")
        if done:
            await util.notify(bot, w["user_id"],
                              f"❌ Withdraw #{w['id']} fail hua. {done['coins']} coins wapas balance me add ho gaye.")
            await alert(bot, f"ℹ️ Payout #{w['id']} fail hua, user ko refund ho gaya.")
        return "failed"
    return "processing"


async def job(ctx):
    for w in await db.wd_processing():
        await settle(ctx.bot, w)
        await asyncio.sleep(0.2)
