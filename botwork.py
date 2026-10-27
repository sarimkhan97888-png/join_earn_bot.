"""Bot Work: poster ka Done/Reject (Telegram message buttons), reject par Report, admin decision, background job.
Baaki saari UI Mini App me hai (api.py)."""
import html
import logging
import time

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M
from telegram.error import TelegramError

import config
import i18n
import db
import extras
import util

log = logging.getLogger("botwork")
h = html.escape


REASONS = {
    "1": "Galat screenshot diya",
    "2": "Screenshot fake / edited lag raha hai",
    "3": "Kaam poora nahi hua",
    "4": "Refer link galat hai",
    "5": "Device verification fail / result galat",
}


def reason_kb(sid, lang="hn"):
    rows = [[B(f"❌ {i18n.tr(t, lang)}", callback_data=f"bws_r{k}:{sid}")] for k, t in REASONS.items()]
    rows.append([B(i18n.tr("✍️ Apna reason likho", lang), callback_data=f"bws_rx:{sid}")])
    rows.append([B(i18n.tr("⬅️ Wapas", lang), callback_data=f"bws_bk:{sid}")])
    return M(rows)


def main_kb(sid):
    return M([[B("✅ Done", callback_data=f"bws_ok:{sid}"), B("❌ Reject", callback_data=f"bws_no:{sid}")]])


async def reject_with_reason(bot, sid, owner, reason):
    """Reject + reason save + worker ko reason ke saath DM. Return sub row ya None (already processed)."""
    s = await db.bw_review(sid, owner, False, reason)
    if not s:
        return None
    extras.feed(f"❌ Bot work submission #{sid} rejected: {h(reason)[:80]} (worker <code>{s['worker_id']}</code>)")
    retry = s["attempt"] < config.BW_MAX_ATTEMPTS
    wl = await i18n.lang_of(s["worker_id"])
    txt = (f"❌ Bot work #{sid} reject hua: <b>{h(s['title'])}</b>\n📝 <b>Reason:</b> {h(i18n.tr(reason, wl))}\n\n")
    if retry:
        txt += (f"🔁 Tumhare paas <b>ek aur mauka</b> hai. Tasks me ye bot work dobara kholo aur sahi screenshot do "
                f"({config.BW_REPORT_HOURS}h ke andar). Dobara reject hua to ye task tumhare liye <b>lock</b> ho jayega.\n"
                f"Agar lagta hai poster ne galat reject kiya to Report karo (Report karne par retry nahi milega).")
    else:
        txt += (f"🔒 Ye task ab tumhare liye <b>lock</b> hai (2 try ho gaye).\n"
                f"Agar tumne kaam sahi kiya tha to {config.BW_REPORT_HOURS}h ke andar Report karo.")
    await util.notify(bot, s["worker_id"], txt, reply_markup=M([[B(i18n.tr("🚩 Report", wl), callback_data=f"bws_rep:{sid}")]]))
    return s


async def on_text(update, ctx):
    """Poster ne 'Apna reason likho' dabaya tha: uska agla text reason ban jata hai."""
    pend = ctx.user_data.get("bw_reason")
    if not pend or time.time() - pend["ts"] > 600:
        ctx.user_data.pop("bw_reason", None)
        return
    reason = (update.message.text or "").strip()
    if len(reason) < 3:
        return await update.message.reply_text(await i18n.tr_for(update.effective_user.id, "Reason thoda detail me likho (kam se kam 3 akshar)."))
    ctx.user_data.pop("bw_reason", None)
    s = await reject_with_reason(ctx.bot, pend["sid"], update.effective_user.id, reason[:200])
    if not s:
        return await update.message.reply_text(await i18n.tr_for(update.effective_user.id, "Already processed ya ye task tumhara nahi hai."))
    await update.message.reply_text(await i18n.tr_for(update.effective_user.id, "✅ Reject ho gaya, worker ko reason bhej diya."))
    try:
        await ctx.bot.edit_message_caption(pend["chat"], pend["mid"], caption=pend["cap"] + f"\n\n❌ <b>Rejected</b>: {h(reason[:200])}",
                                           parse_mode="HTML", reply_markup=None)
    except TelegramError:
        pass


async def mark(q, suffix):
    try:
        await q.edit_message_caption((q.message.caption_html or "") + suffix, parse_mode="HTML", reply_markup=None)
    except TelegramError as e:
        log.warning("bw mark caption edit failed: %s", e)
        try:  # caption edit na chale to kam se kam buttons hata do
            await q.edit_message_reply_markup(reply_markup=None)
        except TelegramError:
            pass


async def send_report(bot, sid):
    s = await db.bw_sub(sid)
    if not s:
        return
    cap = (f"🚩 <b>Bot Work Report</b> #{sid}\nTask: {h(s['title'])} (#{s['bw_id']})\n"
           f"Poster: <code>{s['owner_id']}</code>\nWorker: <code>{s['worker_id']}</code>\n"
           f"Reward: {s['reward']} coins\nRefer link: {h(s['ref_link'])}\nWorker ka report: {h(s['reason'] or '-')}\nPoster ka reject reason: {h(s['reject_reason'] or '-')}")
    kb = M([[B("✅ Pay worker", callback_data=f"bwa_pay:{sid}"), B("❌ Uphold reject", callback_data=f"bwa_no:{sid}")]])
    sent = False
    for a in config.ADMIN_IDS:
        try:
            if s["photo2_id"]:
                await bot.send_photo(a, s["photo2_id"], caption=f"🔐 Device verification screenshot (submission #{sid})")
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

    ul = await i18n.lang_of(uid)

    async def popup(text):
        await q.answer(i18n.tr(text, ul), show_alert=True)

    async def stale(sid, uid):
        """Button dabane par kaam nahi hua: sahi wajah batao, aur agar submission pehle hi ho chuki hai to purane buttons hata do."""
        s0 = await db.bw_sub(sid)
        if s0 and s0["owner_id"] != uid:
            return await popup("Ye task tumhara nahi hai (sirf task ka owner Done/Reject kar sakta hai).")
        names = {"approved": "✅ Approved", "rejected": "❌ Rejected", "reported": "🚩 Reported", "closed": "🔒 Closed"}
        st = names.get(s0["status"]) if s0 else None
        if st:
            await mark(q, f"\n\n{st}")  # buttons hata do
        await popup("Ye submission pehle hi process ho chuki hai.")

    if act == "bws_ok":
        s = await db.bw_review(sid, uid, True)
        if not s:
            return await stale(sid, uid)
        extras.feed(f"✅ Bot work submission #{sid} approved by owner (worker <code>{s['worker_id']}</code>, +{s['reward']})")
        await popup("✅ Done! Worker ko coins mil gaye.")
        await mark(q, "\n\n✅ <b>Approved</b>")
        await util.notify(ctx.bot, s["worker_id"],
                          f"✅ Bot work approved! <b>+{s['reward']}</b> coins balance me add ho gaye.")
        st = db.pop_streak(s["worker_id"])
        if st:
            await util.notify(ctx.bot, s["worker_id"], f"🔥 <b>Streak Day {st[0]} complete!</b> +{st[1]} coins.")
        return

    if act in ("bws_no", "bws_bk", "bws_rx") or act in {f"bws_r{k}" for k in REASONS}:
        s = await db.bw_sub(sid)
        if not s or s["owner_id"] != uid or s["status"] != "pending":
            return await stale(sid, uid)
        if act == "bws_no":  # reject se pehle reason poochho
            await q.answer(i18n.tr("Reason chuno: worker ko ye dikhega", ul))
            try:
                await q.edit_message_reply_markup(reason_kb(sid, ul))
            except TelegramError:
                pass
            return
        if act == "bws_bk":
            await q.answer()
            try:
                await q.edit_message_reply_markup(main_kb(sid))
            except TelegramError:
                pass
            return
        if act == "bws_rx":
            ctx.user_data["bw_reason"] = {"sid": sid, "ts": time.time(), "chat": q.message.chat_id,
                                          "mid": q.message.message_id, "cap": q.message.caption_html or ""}
            await q.answer()
            await util.notify(ctx.bot, uid, "✍️ Reject ka reason ab likh ke bhejo (worker ko yahi dikhega, max 200 akshar).")
            return
        reason = REASONS[act[5:]]
        s2 = await reject_with_reason(ctx.bot, sid, uid, reason)
        if not s2:
            return await popup("Already processed ya tum is task ke owner nahi ho.")
        await popup("❌ Reject kar diya, worker ko reason bhej diya.")
        await mark(q, f"\n\n❌ <b>Rejected</b>: {h(reason)}")
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
