import asyncio
import logging
import re
import secrets

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M, MenuButtonWebApp, Update, WebAppInfo
from telegram.error import TelegramError
from telegram.ext import CallbackQueryHandler, ChatMemberHandler, CommandHandler, filters

import botwork
import config
import db
import gateway
import util

log = logging.getLogger("bot")


def app_kb():
    return M([[B("🚀 Open App", web_app=WebAppInfo(url=f"{config.BASE_URL}/app"))]])


async def post_init(app):
    try:
        await app.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Open App", web_app=WebAppInfo(url=f"{config.BASE_URL}/app")))
    except TelegramError:
        log.warning("menu button set nahi hua")


async def start(update: Update, ctx):
    await db.ensure_user(update.effective_user)
    await update.message.reply_text(
        "👋 <b>Welcome!</b>\nChannels join karo, coins kamao aur UPI me withdraw karo 💰\n\nNeeche button se app kholo 👇",
        parse_mode="HTML", reply_markup=app_kb())


# ---------------- admin: gift code ----------------
async def gift_cmd(update: Update, ctx):
    if update.effective_user.id not in config.ADMIN_IDS:
        return
    a = ctx.args
    if len(a) < 2 or not a[0].isdigit() or not a[1].isdigit() or int(a[0]) < 1 or int(a[1]) < 1:
        return await update.message.reply_text(
            "Usage: /gift <coins> <kitne log use kar sakte> [CODE]\nExample: /gift 500 100  ya  /gift 500 100 DIWALI")
    code = a[2].upper() if len(a) > 2 else secrets.token_hex(4).upper()
    if not re.fullmatch(r"[A-Z0-9]{4,20}", code):
        return await update.message.reply_text("Code 4-20 letters/numbers ka hona chahiye.")
    if not await db.gift_create(code, int(a[0]), int(a[1])):
        return await update.message.reply_text("Ye code pehle se hai. Dusra code chuno.")
    await update.message.reply_text(
        f"🎁 Gift code ban gaya\nCode: <code>{code}</code>\nCoins: {a[0]} per user\nLimit: {a[1]} users", parse_mode="HTML")


# ---------------- admin: withdraw approve/reject ----------------
async def on_admin_wd(update: Update, ctx):
    q = update.callback_query
    if q.from_user.id not in config.ADMIN_IDS:
        return await q.answer("Not allowed", show_alert=True)
    act, wid = q.data.split(":")
    wid = int(wid)
    if act == "adm_no":
        w = await db.wd_move(wid, "pending", "rejected")
        if not w:
            return await q.answer("Already processed", show_alert=True)
        await db.wd_refund(w)
        await q.answer("Rejected & refunded", show_alert=True)
        await util.notify(ctx.bot, w["user_id"], f"❌ Withdraw #{wid} reject hua, coins wapas mil gaye.")
    else:
        w = await db.wd_move(wid, "pending", "processing")
        if not w:
            return await q.answer("Already processed", show_alert=True)
        done = True
        if config.AUTO_PAYOUT:
            try:
                done = await gateway.payout(w["upi"], float(w["amount_inr"]), f"WD{wid}")
            except Exception:
                log.exception("payout failed")
                done = False
        if not done:
            await db.wd_move(wid, "processing", "pending")
            return await q.answer("❌ Payout fail hua. Dobara try karo.", show_alert=True)
        await db.wd_move(wid, "processing", "paid")
        await q.answer("✅ Approved" + ("" if config.AUTO_PAYOUT else " — UPI par manually pay kar do"),
                       show_alert=True)
        await util.notify(ctx.bot, w["user_id"],
                          f"✅ Withdraw #{wid} paid: ₹{float(w['amount_inr']):.2f} → {w['upi']} (10% tax kat ke)")
    try:
        await q.edit_message_reply_markup(None)
    except TelegramError:
        pass


# ---------------- chat member events ----------------
async def on_chat_member(update: Update, ctx):
    cm = update.chat_member
    uid = cm.new_chat_member.user.id
    cid = cm.chat.id
    was, now = util.in_chat(cm.old_chat_member), util.in_chat(cm.new_chat_member)
    if now and not was:
        await db.record_join(cid, uid)
        if await db.unblock(cid, uid):
            await util.notify(ctx.bot, uid, "✅ Rejoin ho gaya. Agar koi aur channel leave kiya hai to unhe bhi rejoin karo.")
    elif was and not now:
        for r in await db.revoke_by_chat(cid, uid):
            await util.notify(ctx.bot, uid, f"🚫 Tumne channel leave kiya. {r['reward']} coins cut ho gaye aur tasks "
                                            f"block hain jab tak dobara join na karo.")


# ---------------- background jobs ----------------
async def job_release(ctx):
    rows = await db.pool.fetch("SELECT * FROM completions WHERE status='hold' AND release_at<=now() LIMIT 200")
    for r in rows:
        st = await util.member_status(ctx.bot, r["chat_id"], r["user_id"])
        if st is None:
            continue
        if st:
            if await db.release(r["id"]):
                await util.notify(ctx.bot, r["user_id"], f"✅ {r['reward']} coins released! Ab withdraw kar sakte ho.")
        elif await db.revoke(r["id"]):
            await util.notify(ctx.bot, r["user_id"], "🚫 Channel leave kiya, coins cut. Rejoin karo.")
        await asyncio.sleep(0.05)


async def job_recheck(ctx):
    rows = await db.pool.fetch(
        """SELECT id, chat_id, user_id FROM completions WHERE status IN ('hold','ok')
           AND created_at > now() - interval '30 days' ORDER BY last_checked LIMIT 100""")
    for r in rows:
        st = await util.member_status(ctx.bot, r["chat_id"], r["user_id"])
        await db.pool.execute("UPDATE completions SET last_checked=now() WHERE id=$1", r["id"])
        if st is False and await db.revoke(r["id"]):
            await util.notify(ctx.bot, r["user_id"], "🚫 Tumne channel leave kiya. Coins cut ho gaye, tasks block hain "
                                                     "jab tak rejoin na karo.")
        await asyncio.sleep(0.05)


async def on_error(update, ctx):
    log.error("Unhandled error", exc_info=ctx.error)


def register(app):
    app.add_handler(CommandHandler("start", start, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("gift", gift_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CallbackQueryHandler(on_admin_wd, pattern=r"^adm_"))
    app.add_handler(CallbackQueryHandler(botwork.on_cb, pattern=r"^(bws_|bwa_)"))
    app.add_handler(ChatMemberHandler(on_chat_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_error_handler(on_error)
    app.job_queue.run_repeating(job_release, interval=300, first=60)
    app.job_queue.run_repeating(job_recheck, interval=600, first=120)
    app.job_queue.run_repeating(botwork.job, interval=900, first=180)
