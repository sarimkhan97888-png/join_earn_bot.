"""Bot Work: poster ka Done/Reject (Telegram message buttons), reject par Report, admin decision, background job.
Baaki saari UI Mini App me hai (api.py)."""
import html
import logging

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M
from telegram.error import TelegramError

import config
import db
import util

log = logging.getLogger("botwork")
h = html.escape


async def mark(q, suffix):
    try:
        await q.edit_message_caption((q.message.caption_html or "") + suffix, parse_mode="HTML", reply_markup=None)
    except TelegramError:
        pass


async def send_report(bot, sid):
    s = await db.bw_sub(sid)
    if not s:
        return
    cap = (f"🚩 <b>Bot Work Report</b> #{sid}\nTask: {h(s['title'])} (#{s['bw_id']})\n"
           f"Poster: <code>{s['owner_id']}</code>\nWorker: <code>{s['worker_id']}</code>\n"
           f"Reward: {s['reward']} coins\nRefer link: {h(s['ref_link'])}\nReason: {h(s['reason'] or '-')}")
    kb = M([[B("✅ Pay worker", callback_data=f"bwa_pay:{sid}"), B("❌ Uphold reject", callback_data=f"bwa_no:{sid}")]])
    sent = False
    for a in config.ADMIN_IDS:
        try:
            await bot.send_photo(a, s["photo_id"], caption=cap, parse_mode="HTML", reply_markup=kb)
            sent = True
        except TelegramError:
            log.warning("report send failed to admin %s", a)
    if sent:
        await db.bw_mark_report_sent(sid)


async def on_cb(update, ctx):
    q = update.callback_query
    d = q.data
    uid = q.from_user.id
    act, sid = d.split(":")
    sid = int(sid)

    async def popup(text):
        await q.answer(text, show_alert=True)

    if act in ("bws_ok", "bws_no"):
        approve = act == "bws_ok"
        s = await db.bw_review(sid, uid, approve)
        if not s:
            return await popup("Already processed ya tum is task ke owner nahi ho.")
        await popup("✅ Done! Worker ko coins mil gaye." if approve else "❌ Reject kar diya.")
        await mark(q, "\n\n✅ <b>Approved</b>" if approve else "\n\n❌ <b>Rejected</b>")
        if approve:
            await util.notify(ctx.bot, s["worker_id"],
                              f"✅ Bot work approved! <b>+{s['reward']}</b> coins balance me add ho gaye.")
        else:
            await util.notify(
                ctx.bot, s["worker_id"],
                f"❌ Bot work #{sid} reject hua. Agar tumne kaam sahi kiya hai to report kar sakte ho "
                f"({config.BW_REPORT_HOURS}h ke andar).",
                reply_markup=M([[B("🚩 Report", callback_data=f"bws_rep:{sid}")]]))
        return

    if act == "bws_rep":
        r = await db.bw_report(sid, uid, "Worker ne reject ke baad report kiya")
        if not r:
            return await popup("Ye report nahi ho sakta (already reported ya time khatam).")
        await popup("🚩 Report bhej di gayi. Admin check karke decision lega.")
        try:
            await q.edit_message_reply_markup(None)
        except TelegramError:
            pass
        return await send_report(ctx.bot, sid)

    if act in ("bwa_pay", "bwa_no"):
        if uid not in config.ADMIN_IDS:
            return await popup("Not allowed")
        pay = act == "bwa_pay"
        s = await db.bw_admin(sid, pay)
        if not s:
            return await popup("Already processed")
        await popup("✅ Worker ko pay kar diya" if pay else "❌ Reject uphold, poster ko refund mila")
        await mark(q, "\n\n✅ <b>Worker paid</b>" if pay else "\n\n❌ <b>Reject upheld</b>")
        if pay:
            await util.notify(ctx.bot, s["worker_id"], f"✅ Report approve hui. <b>+{s['reward']}</b> coins mil gaye.")
            await util.notify(ctx.bot, s["owner_id"],
                              f"ℹ️ Bot work #{s['bw_id']} ki submission #{sid} admin ne approve ki.")
        else:
            await util.notify(ctx.bot, s["worker_id"], f"❌ Admin ne submission #{sid} ka reject sahi mana.")
            await util.notify(ctx.bot, s["owner_id"],
                              f"ℹ️ Submission #{sid} reject upheld. {s['reward']} coins wapas mile.")


async def job(ctx):
    await db.bw_auto_report(config.BW_REVIEW_HOURS)
    for r in await db.bw_unsent_reports():  # naye + pichle jinka alert fail hua tha
        await send_report(ctx.bot, r["id"])
    await db.bw_close_expired(config.BW_REPORT_HOURS)
